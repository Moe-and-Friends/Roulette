from config import settings

from . import local


def generate_mute_time() -> int:
    return local.generate_mute_time()
