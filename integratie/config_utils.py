import os


def parse_rabbit_port(default: int = 5672) -> int:
    value = os.environ.get("RABBIT_PORT")
    try:
        return int(value) if value else default
    except ValueError:
        return default


def require_env(*names: str) -> dict[str, str]:
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
