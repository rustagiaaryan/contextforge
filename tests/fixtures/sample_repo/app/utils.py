def join_path(prefix: str, path: str) -> str:
    """Join two URL path fragments."""
    return f"{prefix.rstrip('/')}/{path.lstrip('/')}"
