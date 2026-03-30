import os


ENV_ALIASES: dict[str, tuple[str, ...]] = {
    # Canonical app names first, VM/infrastructure aliases after.
    "RABBIT_HOST": ("RABBIT_HOST", "RABBITMQKASSA_HOST"),
    "RABBIT_PORT": ("RABBIT_PORT", "RABBITMQKASSA_PORT"),
    "RABBIT_USER": ("RABBIT_USER", "RABBITMQKASSA_USER"),
    "RABBIT_PASS": ("RABBIT_PASS", "RABBITMQKASSA_PASS"),
    "RABBIT_VHOST": ("RABBIT_VHOST", "RABBITMQKASSA_VHOST"),
    "RABBIT_AUTO_SETUP_TOPOLOGY": ("RABBIT_AUTO_SETUP_TOPOLOGY", "RABBITMQKASSA_AUTO_SETUP_TOPOLOGY"),
}


def get_env(name: str, default: str | None = None) -> str | None:
    """Return env value for canonical name, with optional alias fallback."""
    keys = ENV_ALIASES.get(name, (name,))
    for key in keys:
        value = os.environ.get(key)
        if value is not None and value.strip():
            return value
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
