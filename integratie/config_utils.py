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


def _clean_env_value(value: str | None) -> str | None:
    """Trim whitespace and remove matching wrapping quotes."""
    if value is None:
        return None

    cleaned = value.strip()
    if len(cleaned) >= 2 and cleaned[0] == cleaned[-1] and cleaned[0] in {'"', "'"}:
        cleaned = cleaned[1:-1]
    return cleaned


def get_env(name: str, default: str | None = None) -> str | None:
    """Read a single environment variable, returning default if it is unset or blank."""
    value = _clean_env_value(os.environ.get(name))
    if value is None or not value:
        return default
    return value


def parse_rabbit_port(default: int = 5672) -> int:
    """Read RABBIT_PORT from the environment and return it as an integer."""
    value = get_env("RABBIT_PORT")
    try:
        return int(value) if value else default
    except ValueError:
        return default


def require_env(*names: str) -> dict[str, str]:
    """Return a dict of the requested environment variables."""
    values: dict[str, str] = {}
    missing: list[str] = []

    for name in names:
        value = get_env(name)
        if value is None:
            missing.append(name)
        else:
            values[name] = value

    if missing:
        missing_csv = ", ".join(missing)
        raise ValueError(f"Required environment variables are missing: {missing_csv}")

    return values


def parse_xml_float(element, default: float = 0.0) -> float:
    """Consistently parse a float from an XML element's text, falling back to default on error."""
    if element is None or not element.text:
        return default
    try:
        return float(element.text.strip())
    except (ValueError, TypeError):
        return default
