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
    """Trim whitespace and remove matching wrapping quotes from an env-var string.

    Docker Compose and shell scripts sometimes pass values with surrounding
    quotes, e.g. ``RABBIT_HOST="rabbitmq"`` becomes ``"rabbitmq"`` in the
    environment.  This function strips those quotes so callers always receive
    the bare value.  Only symmetric single- or double-quote pairs are removed;
    unbalanced quotes are left untouched.
    """
    if value is None:
        return None

    cleaned = value.strip()
    if len(cleaned) >= 2 and cleaned[0] == cleaned[-1] and cleaned[0] in {'"', "'"}:
        cleaned = cleaned[1:-1]
    return cleaned


def get_env(name: str, default: str | None = None) -> str | None:
    """Read a single environment variable, returning *default* if it is unset or blank.

    "Blank" means an empty string after whitespace and quote stripping (see
    ``_clean_env_value``).  This prevents callers from accidentally treating
    ``RABBIT_HOST=``  (empty assignment) as a valid hostname.
    """
    value = _clean_env_value(os.environ.get(name))
    if value is None or not value:
        return default
    return value


def parse_rabbit_port(default: int = 5672) -> int:
    """Read ``RABBIT_PORT`` from the environment and return it as an integer.

    Defaults to 5672 (the standard AMQP port) when the variable is absent or
    not a valid integer — this avoids a hard crash on misconfigured deployments
    and lets pika report a clearer connection error instead.
    """
    value = get_env("RABBIT_PORT")
    try:
        return int(value) if value else default
    except ValueError:
        return default


def require_env(*names: str) -> dict[str, str]:
    """Return a ``{name: value}`` dict for the requested environment variables.

    Raises ``ValueError`` listing ALL missing names at once (not just the first)
    so operators can fix their ``.env`` file in a single attempt rather than
    discovering missing variables one by one.

    Called at module import time by ``receiver.py`` and ``sender.py`` so the
    service fails fast with a clear message before attempting any network I/O.
    """
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
    """Parse a float from an XML element's text, falling back to *default* on any error.

    Handles three common "no value" cases without raising:
    - ``element`` is ``None`` (the XML tag was absent entirely)
    - ``element.text`` is ``None`` or empty (tag present but empty: ``<amount/>``)
    - ``element.text`` cannot be converted to float (malformed value)

    Used when reading ``<amount>`` and ``<current_balance>`` from incoming CRM
    messages where an absent tag means "zero" rather than an error.
    """
    if element is None or not element.text:
        return default
    try:
        return float(element.text.strip())
    except (ValueError, TypeError):
        return default
