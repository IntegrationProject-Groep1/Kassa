import os
import logging


logger = logging.getLogger(__name__)


ENV_ALIASES: dict[str, tuple[str, ...]] = {
    # Canonical app names first, VM/infrastructure aliases after.
    "RABBIT_HOST": ("RABBIT_HOST", "RABBITMQKASSA_HOST"),
    "RABBIT_PORT": ("RABBIT_PORT", "RABBITMQKASSA_PORT"),
    "RABBIT_USER": ("RABBIT_USER", "RABBITMQKASSA_USER"),
    "RABBIT_PASS": ("RABBIT_PASS", "RABBITMQKASSA_PASS"),
    "RABBIT_VHOST": ("RABBIT_VHOST", "RABBITMQKASSA_VHOST"),
    "RABBIT_AUTO_SETUP_TOPOLOGY": ("RABBIT_AUTO_SETUP_TOPOLOGY", "RABBITMQKASSA_AUTO_SETUP_TOPOLOGY"),
}

_WARNED_ALIAS_CONFLICTS: set[str] = set()


def get_env(name: str, default: str | None = None) -> str | None:
    """Return canonical env value with alias fallback and whitespace trimming."""
    keys = ENV_ALIASES.get(name, (name,))
    seen_values: dict[str, str] = {}
    for key in keys:
        value = os.environ.get(key)
        if value is not None and value.strip():
            trimmed = value.strip()
            seen_values[key] = trimmed

    if len(set(seen_values.values())) > 1 and name not in _WARNED_ALIAS_CONFLICTS:
        _WARNED_ALIAS_CONFLICTS.add(name)
        details = ", ".join(f"{k}={v}" for k, v in seen_values.items())
        logger.warning(
            "Conflicting environment aliases for %s detected; using precedence order %s. Values: %s",
            name,
            keys,
            details,
        )

    for key in keys:
        if key in seen_values:
            return seen_values[key]

    return default


def parse_rabbit_port(default: int = 5672) -> int:
    value = get_env("RABBIT_PORT")
    try:
        return int(value) if value else default
    except ValueError:
        return default


def require_env(*names: str) -> dict[str, str]:
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
