import random
import sys

from ayumi import Ayumi
from config import settings
from datetime import datetime, timedelta, timezone
from discord import Intents, Message
from discord.ext.commands import Bot
from intervals import intervals
from intervals import time_display_converter as tdc

# TODO: Add support for Cogs/Extensions

DEFAULT_SAFE_MESSAGE_SELF = "You have a safe role, so you won't be muted :)"
DEFAULT_SAFE_MESSAGE_OTHER = "{safe_user_name} has a safe role, so they won't be muted :)"
DEFAULT_MUTE_MESSAGE_SELF = "Oh no, you've been muted for {mute_duration_display_str}!"
DEFAULT_MUTE_MESSAGE_OTHER = "Oh no, {muted_user_name} has been muted for {mute_duration_display_str}!"
DEFAULT_ADMIN_NO_ROLES_MESSAGE = "You do not have sufficient permissions to run this command."

intents = Intents.default()
intents.message_content = True  # Enable sending messages
intents.members = True
bot = Bot("nana", intents=intents)
# Optionally load the bot sharded, to support zero downtime.
bot.shard_id = settings.get("bot_shard_id", None)
bot.shard_count = settings.get("bot_shard_count", None)


@bot.event
async def on_ready():
    Ayumi.info("Bot is ready.")


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

    admin_roles = guild_settings.get("admin_roles", list())
    if admin_roles:
        Ayumi.debug("Loaded admin role IDs: {ids}".format(ids=", ".join([str(role) for role in admin_roles])))
    else:
        Ayumi.warning("No admin role IDs were loaded.")

    # When message content contains mentions of other users, this is interpreted as a request to execute the gacha
    # on all mentions' behalf. This requires administrator-level privileges.
    if message.mentions and set([role.id for role in message.author.roles]).isdisjoint(admin_roles):
        Ayumi.info("Message contains tags of other users, but user does not have an admin role, ignoring.")
        admin_no_role_messages = guild_settings.get("admin_no_role_messages", [DEFAULT_ADMIN_NO_ROLES_MESSAGE])
        admin_no_role_message_to_use = random.choice(admin_no_role_messages)
        await message.reply(
            admin_no_role_message_to_use.format(
                author_name=message.author.name
            )
        )
        return

    # Preload safe roles for future processing. If the message author is a safe role, then do not mute them.
    # However, they should still be informed of their theoretical mute duration.
    safe_roles = guild_settings.get("safe_roles", list())
    if safe_roles:
        Ayumi.debug("Loaded safe role IDs: {ids}".format(ids=", ".join([str(role) for role in safe_roles])))
    else:
        Ayumi.warning("No safe role IDs were loaded.")

    # Admin roles are implicitly also safe roles, so include them in the list.
    safe_roles.extend(admin_roles)
    Ayumi.debug("Extended safe roles to include admin role IDs: {ids}".format(
        ids=", ".join([str(role) for role in admin_roles])))

    # Select the intended action target for this message.
    # If author has mentioned other users, they are the target. Otherwise, the target defaults to the author.
    # Note: `dict.fromkeys()` is used to remove duplicate tags.
    target_users = list(dict.fromkeys(message.mentions or [message.author]))

    # Special case, target_users also should ignore if the bot is targeting itself.
    if bot.user in target_users:
        Ayumi.warning("Message mentions include this bot, removing.")
        target_users.remove(bot.user)

    target_users = target_users[:5]  # Trim to only support up to 5 tags at most currently.

    # Because requests may take long, send a typing indicator so the author knows processing is occuring.
    async with message.channel.typing():

        # Start processing an action for each target_user (either the message author, or all tagged in the message).
        for target_user in target_users:
            mute_duration = intervals.generate_mute_time()  # Mute duration is in minutes (as int)

            mute_duration_display_str = tdc.convert_minutes_to_display_str(mute_duration)
            Ayumi.info(
                "Generated mute time: {mute_time} ({mute_time_in_minutes} minutes).".format(
                    mute_time=mute_duration_display_str,
                    mute_time_in_minutes=mute_duration))

            target_is_self = (target_user == message.author)
            Ayumi.debug(f"Target for mute is self: {target_is_self}")

            # TODO: Log which role on the author is safe.
            if not set([role.id for role in target_user.roles]).isdisjoint(safe_roles):
                Ayumi.info("Message {message_id} for user {author_name} has a safe role, ignoring.".format(
                    message_id=message.id,
                    author_name=target_user.name))

                safe_messages = guild_settings.get("safe_messages_self", [DEFAULT_SAFE_MESSAGE_SELF]) \
                    if target_is_self else guild_settings.get("safe_messages_other", [DEFAULT_SAFE_MESSAGE_OTHER])
                safe_message_to_use = random.choice(safe_messages)
                await message.reply(safe_message_to_use.format(
                    safe_user_name=target_user.display_name,
                    mute_duration_display_str=mute_duration_display_str))
                continue

            # Calculate the time that the user will be unblocked.
            current_time = datetime.now(timezone.utc)  # UTC time
            Ayumi.debug("The current time is: {current_time}".format(current_time=current_time.strftime("[UTC] %c")))

            mute_duration_as_delta = timedelta(minutes=mute_duration)

            # TODO: Temporary block due to the Discord timeout being limited to 28 days.
            if mute_duration_as_delta > timedelta(days=28):
                mute_duration_as_delta = timedelta(days=28)
                Ayumi.warning(
                    "WARNING: Generated a mute time above 28 days, trimming to 28 days. Check your configuration!")

            unmute_time = current_time + mute_duration_as_delta
            Ayumi.debug("The user will be unmuted at: {unmute_time}".format(unmute_time=unmute_time.strftime("[UTC] %c")))

            await target_user.timeout(mute_duration_as_delta, reason="Timed out via Gacha for {duration}.".format(
                duration=mute_duration_display_str))
            Ayumi.info(
                "Timed out user ({user_name}, {user_display_name}) until {unmute_time}".format(
                    user_name=target_user.name,
                    user_display_name=target_user.display_name,
                    unmute_time=unmute_time.strftime("[UTC] %c")
                ))

            mute_messages = guild_settings.get("mute_messages_self", [DEFAULT_MUTE_MESSAGE_SELF]) \
                if target_is_self else guild_settings.get("mute_messages_other", [DEFAULT_MUTE_MESSAGE_OTHER])
            mute_message_to_use = random.choice(mute_messages)
            await message.reply(
                mute_message_to_use.format(
                    muted_user_name=target_user.display_name,
                    mute_duration_display_str=mute_duration_display_str))


def main():
    bot.run(token=settings.get("bot_token"))


# Press the green button in the gutter to run the script.
if __name__ == '__main__':
    main()

# See PyCharm help at https://www.jetbrains.com/help/pycharm/
