import sys

from ayumi import Ayumi
from config import settings
from requests.exceptions import Timeout as RequestTimeout

from . import digital_ocean_function, local

all_interval_settings = settings.get("intervals")
if not all_interval_settings:
    Ayumi.critical("Interval settings are missing. Please check your configuration, now exiting.")
    sys.exit(1)

_DIGITALOCEAN_FUNCTION_ENABLED = all_interval_settings.get("digitalocean", dict()).get("function", dict()).get(
    "enabled", False)
Ayumi.info("DigitalOcean Function Enabled: {}".format(str(_DIGITALOCEAN_FUNCTION_ENABLED)))


def generate_mute_time() -> int:
    if (_DIGITALOCEAN_FUNCTION_ENABLED):
        Ayumi.debug("Trying to load an interval from DigitalOcean Function.")
        try:
            return digital_ocean_function.generate_mute_time()
        except (RequestTimeout, RuntimeError, ValueError) as e:
            Ayumi.critical("DigitalOcean Function encountered an error: {}".format(e))

    # Local settings is guaranteed to return a value.
    Ayumi.debug("Loading interval from local settings.")
    return local.generate_mute_time()
