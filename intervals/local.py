import random

from ayumi import Ayumi
from config import settings
from .time_display_converter import convert_interval_str_to_minutes, convert_minutes_to_display_str

# A default interval to fall back to, if the user has not set any.
_DEFAULT_INTERVAL = {
    "bound": {
        "lower": "1m",
        "upper": "5m"
    },
    "weight": 100
}


def generate_mute_time() -> int:
    # Load the list of intervals used to determine mutes.
    interval_settings = settings.get("intervals") or dict()
    intervals = interval_settings.get("local", list())
    Ayumi.debug("Loaded {count} intervals.".format(count=int(len(intervals))))

    if not intervals:
        intervals = [_DEFAULT_INTERVAL]
        Ayumi.warning("No local interval settings were set or found - using default fallback.")

    # First, select an interval to load
    # Create the bounds tuples and their respective weights
    bounds = [interval["bound"] for interval in intervals]
    weights = [int(interval["weight"]) for interval in intervals]
    interval = random.choices(bounds, weights=weights, k=1)[0]

    # From the interval, randomly select a time.
    # The interval is a Tuple[lower_bound: str, upper_bound: str]
    lower_bound = convert_interval_str_to_minutes(interval["lower"])
    upper_bound = convert_interval_str_to_minutes(interval["upper"])

    mute_duration = random.randint(lower_bound, upper_bound)
    Ayumi.debug(
        "Selected mute duration: ({mute_duration}) from lower bound: ({lower_bound}) and upper bound: ({upper_bound}).".format(
            mute_duration=convert_minutes_to_display_str(mute_duration),
            lower_bound=convert_minutes_to_display_str(lower_bound),
            upper_bound=convert_minutes_to_display_str(upper_bound)))

    return mute_duration
