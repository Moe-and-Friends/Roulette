
from dynaconf import Dynaconf

settings = Dynaconf(
    envvar_prefix="ROULETTE",
    environments=True,
    settings_files=[
        'settings.toml',
        '.secrets.toml',
        'settings.yml',
        '.secrets.yml'
    ],
)

# `envvar_prefix` = export envvars with `export ROULETTE_FOO=bar`.
# `settings_files` = Load these files in the order.
