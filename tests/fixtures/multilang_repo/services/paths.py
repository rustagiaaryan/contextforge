def join_path(prefix: str, path: str) -> str:
    """Join two route fragments."""
    return f"{prefix.rstrip('/')}/{path.lstrip('/')}"
