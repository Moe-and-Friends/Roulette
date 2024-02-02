
_WEEKS_IN_MINUTES = 10080
_DAYS_IN_MINUTES = 1440
_HOURS_IN_MINUTES = 60
_MINUTES_IN_MINUTES = 1
_TIME_CONVERSION_INTERVALS = (
    ('weeks', _WEEKS_IN_MINUTES),
    ('days', _DAYS_IN_MINUTES),
    ('hours', _HOURS_IN_MINUTES),
    ('minutes', _MINUTES_IN_MINUTES)
)


def convert_interval_str_to_minutes(interval: str) -> int:
    # Strip out non-numeric characters
    time = int("".join(filter(str.isdigit, interval)))
    if interval.endswith("m"):
        return time * _MINUTES_IN_MINUTES  # Base case
    elif interval.endswith("h"):
        return time * _HOURS_IN_MINUTES
    elif interval.endswith("d"):
        return time * _DAYS_IN_MINUTES
    elif interval.endswith("w"):
        return time * _WEEKS_IN_MINUTES


# This method is black magic.
def convert_minutes_to_display_str(minutes: int, granularity=2) -> str:
    # Edge case: This function doesn't properly handle 0 minutes
    if minutes == 0:
        return "0 minutes"
    result = list()
    for name, count in _TIME_CONVERSION_INTERVALS:
        value = minutes // count
        if value:
            minutes -= value * count
            if value == 1:
                name = name.rstrip('s')
            result.append("{} {}".format(value, name))
    start, _, end = ', '.join(result[:granularity]).rpartition(',')
    return start + " and" + end if start else end

