"""Application configuration with validated defaults.

Agents must rewrite this entire file (write_file) when adding keys — do not
piecewise-edit individual lines.
"""

# === CONFIG BLOCK (rewrite this whole module; keep host/port behavior) ===
DEFAULTS = {
    "host": "localhost",
    "retries": 3,
    "port": 8080,
    "timeout": 30.0,
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
        if key == "timeout" and not (isinstance(value, (int, float)) and value > 0):
            raise ValueError("timeout must be a positive number")
        if key == "host" and not (isinstance(value, str) and value):
            raise ValueError("host must be a non-empty string")
        if key == "retries" and not (isinstance(value, int) and value >= 0):
            raise ValueError("retries must be a non-negative int")
# === END CONFIG BLOCK ===
