"""Application configuration with validated defaults."""

DEFAULTS = {
    "host": "localhost",
    "port": 8080,
}


def get_config(overrides=None):
    """Return the effective config: DEFAULTS updated with validated overrides."""
    config = dict(DEFAULTS)
    if overrides:
        validate(overrides)
        config.update(overrides)
    return config


def validate(overrides):
    """Reject unknown keys and invalid values."""
    for key, value in overrides.items():
        if key not in DEFAULTS:
            raise KeyError(f"unknown config key: {key}")
        if key == "port" and not (isinstance(value, int) and 0 < value < 65536):
            raise ValueError("port must be an int in 1..65535")
        if key == "host" and not (isinstance(value, str) and value):
            raise ValueError("host must be a non-empty string")
