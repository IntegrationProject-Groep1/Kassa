"""
config_utils.py — Shared configuration helpers for the Kassa integration service.

Used by receiver.py, sender.py, and dev tools to read and validate environment
variables. Keeps the env-parsing logic in one place so no module duplicates it.

Public API:
    get_env(name, default)   — read one variable, return default if missing/blank
    require_env(*names)      — read multiple variables, raise on any missing one
    parse_rabbit_port()      — read RABBIT_PORT, fall back to 5672 on bad input
"""

import os


def get_env(name: str, default: str | None = None) -> str | None:
    """
    Read a single environment variable, returning `default` if it is unset or blank.

    This is the lightweight variant of require_env() — it never raises, so it
    is suitable for optional settings and tool scripts where a missing variable
    should fall back gracefully rather than abort.
    """
    value = os.environ.get(name)
    if value is None or not value.strip():
        return default
    return value


def parse_rabbit_port(default: int = 5672) -> int:
    """
    Read RABBIT_PORT from the environment and return it as an integer.

    Falls back to `default` (5672) if the variable is not set or contains
    a value that cannot be converted to an integer (e.g. an empty string
    or a typo like "amqp").
    """
    value = os.environ.get("RABBIT_PORT")
    try:
        return int(value) if value else default
    except ValueError:
        return default


def require_env(*names: str) -> dict[str, str]:
    """
    Return a dict of the requested environment variables.

    Raises ValueError listing every variable that is either unset or blank,
    so the caller gets one error with the full list rather than failing on
    the first missing variable.

    Example:
        cfg = require_env("ODOO_URL", "ODOO_DB", "ODOO_USER", "ODOO_PASS")
        uid = common.authenticate(cfg["ODOO_DB"], ...)
    """
    values: dict[str, str] = {}
    missing: list[str] = []

    for name in names:
        value = os.environ.get(name)
        if value is None or not value.strip():
            missing.append(name)
        else:
            values[name] = value

    if missing:
        missing_csv = ", ".join(missing)
        raise ValueError(f"Required environment variables are missing: {missing_csv}")

    return values
