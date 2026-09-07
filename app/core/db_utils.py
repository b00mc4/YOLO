def escape_like(value: str) -> str:
    if not value:
        return value
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
