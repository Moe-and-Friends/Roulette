import random
import sys

import intervals

from ayumi import Ayumi
from config import settings
from datetime import datetime, timedelta, timezone
from discord import Forbidden, Intents, Message
from discord.ext import tasks
from discord.ext.commands import Bot
from queue import PriorityQueue

# TODO: Add support for Cogs/Extensions

DEFAULT_SAFE_MESSAGE = "You have a safe role, so you won't be muted :)"
DEFAULT_MUTE_MESSAGE = "Oh no, you've been muted for {mute_duration_display_str}!"

"""
A set that contains every user currently under a mute status.

This is a PriorityQueue holding elements of the following form:
< (unmute_time_ms, user_id, guild_id, role_id) >

Note: PriorityQueue is thread-safe; a thread lock does not need to be used.
"""
_muted_users = PriorityQueue(maxsize=0)

intents = Intents.default()
intents.message_content = True  # Enable sending messages
intents.members = True
bot = Bot("nana", intents=intents)


@tasks.loop(minutes=1.0)
async def batch_unmute_users():
    current_time = datetime.now(timezone.utc)
    Ayumi.debug("Now starting batch unmute job. The current time is: {time}.".format(time=current_time.strftime("%c")))

    while not _muted_users.empty():
        # Fetch the first element (i.e. the next closest job) from the queue. Note that this is always a pop.
        unmute_job = _muted_users.get(block=True)

        unmute_job_time = unmute_job[0]
        Ayumi.debug("Next unmute is scheduled at: {time}.".format(time=unmute_job_time.strftime("%c")))

        # If the unmute time on the job has not passed yet, then all tasks are at a future time.
        if current_time < unmute_job_time:
            Ayumi.debug("Job is in a future time. Now exiting the batch unmute job.")
            _muted_users.put(unmute_job)  # Return the job
            return

        unmute_job_user_id = unmute_job[1]
        Ayumi.debug(f"Job has user id: {unmute_job_user_id}")
        unmute_job_guild_id = unmute_job[2]
        Ayumi.debug(f"Job has guild id: {unmute_job_guild_id}")
        unmute_job_role_id = unmute_job[3]
        Ayumi.debug(f"Job has (unmute) role id: {unmute_job_role_id}")

        # Load the Guild object to perform the unmute.
        guild = bot.get_guild(unmute_job_guild_id)
        if not guild:
            Ayumi.debug("Was not able to load Guild from local cache, requesting from Gateway...")
            guild = await bot.fetch_guild(unmute_job_guild_id)
        Ayumi.debug("Loaded Guild (name: {name}, id: {id}).".format(
            name=guild.name,
            id=guild.id))

        # Load the User object from the Guild to perform the unmute.
        user = await guild.fetch_member(unmute_job_user_id)
        Ayumi.debug("Loaded Member (name: {name}, id: {id}).".format(
            name=user.name,
            id=user.id))

        # Load the Role object to remove from the User.
        mute_role = guild.get_role(unmute_job_role_id)
        if not mute_role:
            Ayumi.debug("Unable to load role from local Guild object, requesting from Gateway...")
            await guild.fetch_roles()
            mute_role = guild.get_role(unmute_job_role_id)
        Ayumi.debug("Loaded role ({role_name}, {role_id}).".format(
            role_name=mute_role.name,
            role_id=mute_role.id))

        # Perform the unmute.
        try:
            await user.remove_roles(mute_role, atomic=True)
            Ayumi.info("Successfully removed mute from {user_name} ({user_display_name}).".format(
                user_name=user.name,
                user_display_name=user.display_name))
        except Forbidden:
            Ayumi.critical("Bot does not appear to have permissions to remove roles. Now exiting...")
            await bot.close()
            sys.exit(1)

    Ayumi.debug("Queue is empty, exiting the batch unmute job.")
    return


@bot.event
async def on_ready():
    Ayumi.info("Bot is ready.")

    Ayumi.debug("Starting batch unmute job...")
    batch_unmute_users.start()
    Ayumi.info("Started batch unmute job.")


@bot.event
async def on_message(message: Message):
    # Ignore messages sent by other bots.
    if message.author.bot:
        Ayumi.debug("Ignoring message {message_id}, as it is from a bot.".format(message_id=message.id))
        return

    # Ignore content from unobserved channels/etc.
    observing_guild_ids = [int(guild_id) for guild_id in settings.get("guilds", dict()).keys()]
    if not observing_guild_ids:
        Ayumi.critical("There do not appear to be any guilds being observed, exiting.")
        sys.exit(1)
    Ayumi.debug("Loaded Guild IDs to observe: {guild_ids}".format(
        guild_ids=", ".join([str(guild_id) for guild_id in observing_guild_ids])))
    if message.guild.id not in observing_guild_ids:
        Ayumi.debug(
            "Ignoring message {message_id} from user {user_name}: Guild {guild_name} ({guild_id}) not being observed.".format(
                message_id=message.id,
                user_name=message.author.name,
                guild_id=message.guild.id,
                guild_name=message.guild.name))
        return

    # Load Settings for the current Guild
    guild_settings = settings.get("guilds").get(str(message.guild.id), dict())
    if not guild_settings:
        Ayumi.warning("No settings found for guild {guild_name} ({guild_id}), will not mute user.".format(
            guild_name=message.guild.name,
            guild_id=message.guild.id))
        return

    # Note: The Channel IDs should already be ints, but cast just to be safe.
    observing_channel_ids = [int(channel_id) for channel_id in guild_settings.get("channels", list())]
    if not observing_channel_ids:
        Ayumi.critical(
            "There do not appear any channels being observed for guild {guild_name} ({guild_id}), will not continue.".format(
                guild_name=message.guild.name,
                guild_id=message.guild.id))
    Ayumi.debug("Loaded Channel IDs to observe: {channel_ids}".format(
        channel_ids=", ".join([str(channel_id) for channel_id in observing_channel_ids])))
    if message.channel.id not in observing_channel_ids:
        Ayumi.debug(
            "Ignoring message {message_id} from user {author_name}: Channel {channel_name} ({channel_id}) in guild {guild_name} "
            " ({guild_id}) not being observed.".format(
                message_id=message.id,
                author_name=message.author.name,
                channel_id=message.channel.id,
                channel_name=message.channel.name,
                guild_id=message.guild.id,
                guild_name=message.guild.name))
        return

    Ayumi.debug("Received message in channel {channel_name}: \"{content}\"".format(
        channel_name=message.channel.name,
        content=message.content))

    # Load trigger words to check the message for.
    trigger_words = guild_settings.get("triggers")
    if not trigger_words:
        Ayumi.warning("Guild {guild_name} ({guild_id}) has no trigger words, will not continue.".format(
            guild_name=message.guild.name,
            guild_id=message.guild.id))
        return
    Ayumi.debug("Loaded trigger words: {trigger_words}".format(
        trigger_words=[", ".join(trigger_words)]
    ))

    # Only process messages that contain trigger words (e.g. the :gamerwhen: emoji)
    # TODO: Update this logging to output the actual trigger word(s) found.
    if not any(trigger in message.content for trigger in trigger_words):
        Ayumi.debug("Ignoring message: No trigger words found.")
        return
    else:
        Ayumi.info(
            "Received message {message_id} from user {author_name} ({author_display_name}): \"{message_content}\". Now starting mute...".format(
                message_id=message.id,
                author_name=message.author.name,
                author_display_name=message.author.display_name,
                message_content=message.content[:10]))

    mute_duration = intervals.generate_mute_time()  # Mute duration is in minutes (as int)
    Ayumi.info(
        "Generated mute time: {mute_time} ({mute_time_in_minutes} minutes).".format(
            mute_time=intervals.convert_minutes_to_display_str(mute_duration),
            mute_time_in_minutes=mute_duration))

    # If the message author is a safe role, then do not mute them.
    # However, they should still be informed of their theoretical mute duration.
    safe_roles = guild_settings.get("safe_roles", list())
    if safe_roles:
        Ayumi.debug("Loaded safe role IDs: {ids}".format(ids=", ".join([str(role) for role in safe_roles])))
    else:
        Ayumi.warning("No safe role IDs were loaded.")

    # TODO: Log which role on the author is safe.
    if not set([role.id for role in message.author.roles]).isdisjoint(safe_roles):
        Ayumi.info("Message {message_id} from user {author_name} has a safe role, ignoring.".format(
            message_id=message.id,
            author_name=message.author.name))

        safe_messages = guild_settings.get("safe_messages", [DEFAULT_SAFE_MESSAGE])
        safe_message_to_use = random.choice(safe_messages)
        await message.reply(
            safe_message_to_use.format(
                safe_user_name=message.author.display_name,
                mute_duration_display_str=intervals.convert_minutes_to_display_str(mute_duration)))
        return

    # Calculate the time that the user will be unblocked.
    current_time = datetime.now(timezone.utc)  # UTC time
    Ayumi.debug("The current time is: {current_time}".format(current_time=current_time.strftime("[UTC] %c")))

    mute_duration_as_delta = timedelta(minutes=mute_duration)
    unmute_time = current_time + mute_duration_as_delta
    Ayumi.debug("The user will be unmuted at: {unmute_time}".format(unmute_time=unmute_time.strftime("[UTC] %c")))

    # Mute the user by assigning the role.
    mute_role_id = guild_settings.get("mute_role", None)
    if not mute_role_id:
        Ayumi.warning("No mute role ID found for guild {guild_name} ({guild_id}), will not mute user.".format(
            guild_name=message.guild.name,
            guild_id=message.guild.id))

    Ayumi.debug("Loading role with id: ({role_id}) for the mute...".format(role_id=mute_role_id))
    role_to_add = message.guild.get_role(mute_role_id)
    if not role_to_add:
        Ayumi.debug("Unable to load role locally, loading all roles from Gateway and retrying...")
        await message.guild.fetch_roles()
        role_to_add = message.guild.get_role(mute_role_id)
    Ayumi.debug("Loaded role ({role_name}, {role_id}).".format(role_name=role_to_add.name, role_id=role_to_add.id))

    await message.author.add_roles(role_to_add, atomic=True)
    Ayumi.info(
        "Muted user ({user_name}, {user_display_name}) with role ({role_name}, {role_id}) until {unmute_time}.".format(
            user_name=message.author.name,
            user_display_name=message.author.display_name,
            role_name=role_to_add.name,
            role_id=role_to_add.id,
            unmute_time=unmute_time.strftime("[UTC] %c")))

    mute_messages = guild_settings.get("mute_messages", [DEFAULT_MUTE_MESSAGE])
    mute_message_to_use = random.choice(mute_messages)
    await message.reply(
        mute_message_to_use.format(
            muted_user_name=message.author.display_name,
            mute_duration_display_str=intervals.convert_minutes_to_display_str(mute_duration)))

    # Add the unmute_time as a record for the background task.
    # The message object itself could technically become stale. Store this by IDs instead.
    _muted_users.put((unmute_time, message.author.id, message.guild.id, mute_role_id))


def main():
    bot.run(token=settings.get("bot_token"))


# Press the green button in the gutter to run the script.
if __name__ == '__main__':
    main()

# See PyCharm help at https://www.jetbrains.com/help/pycharm/
