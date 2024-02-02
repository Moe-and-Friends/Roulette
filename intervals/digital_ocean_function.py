import requests

from ayumi import Ayumi
from config import settings
from cerberus import Validator

"""
TODO: Determine whether to integrate or remove extra keys.

Currently, only the `duration_mins` key will actually be used.
"""
_RESPONSE_SCHEMA = {
    'action': {
        'type': 'dict',
        'required': True,
        'schema': {
            'timeout': {
                'type': 'dict',
                'required': True,
                'schema': {
                    'duration_display_str': {'type': 'string'},
                    'duration_mins': {'type': 'integer', 'min': 1},
                    'lower_bound_display_str': {'type': 'string'},
                    'lower_bound_mins': {'type': 'integer', 'min': 1},
                    'upper_bound_display_str': {'type': 'string'},
                    'upper_bound_mins': {'type': 'integer', 'min': 1}
                }
            },
            # Note: This is a literal key called "type".
            'type': {
                'type': 'string',
                'allowed': ['TIMEOUT'],
                'required': True
            }
        }
    }
}

_WHISK_AUTH_TOKEN_HEADER = "X-Require-Whisk-Auth"

_validator = Validator(_RESPONSE_SCHEMA, allow_unknown=True, require_all=True)


def generate_mute_time() -> int:
    # Load parent settings
    all_interval_settings = settings.get("intervals") or dict()
    digitalocean_interval_settings = all_interval_settings.get("digitalocean", dict())
    # Load interval settings used for this module
    interval_settings = digitalocean_interval_settings.get("function", dict())

    url = interval_settings.get("url")
    if not url:
        raise ValueError("DigitalOcean Function interval module is active, but no URL is set.")

    headers = dict()
    if auth_token := interval_settings.get("auth_token"):
        Ayumi.debug("DigitalOcean Function auth token exists, added to headers.")
        headers[_WHISK_AUTH_TOKEN_HEADER] = auth_token

    # Explicitly default to `None` to signify there is no timeout by default.
    timeout = interval_settings.get("timeout", None)
    Ayumi.debug("DigitalOcean Function request timeout set to: {timeout}".format(
        timeout=str(timeout)
    ))

    # If the request times out, it should be caught by the parent module.
    res = requests.get(url, headers=headers, timeout=timeout)

    if res.status_code != 200:
        raise RuntimeError("DigitalOcean Function returned code {code}.".format(
            code=str(res.status_code)
        ))

    res_data = res.json()

    # Validate the response
    if not _validator.validate(res_data):
        raise ValueError("DigitalOcean Function did not return a valid response.")

    # Values are guaranteed to exist by Cerberus.
    Ayumi.debug("Received a mute time of {duration} from the function.".format(
        duration=res_data['action']['timeout']['duration_display_str']
    ))
    return res_data['action']['timeout']['duration_mins']
