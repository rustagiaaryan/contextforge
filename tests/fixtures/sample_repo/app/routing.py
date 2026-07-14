"""Resolve requests through mounted applications."""

from app.utils import join_path


class Mount:
    """A route that delegates to a child application."""

    def __init__(self, prefix: str) -> None:
        self.prefix = prefix

    def resolve(self, path: str) -> str:
        """Build the delegated path."""
        return join_path(self.prefix, path)


def dispatch(mount: Mount, path: str) -> str:
    return mount.resolve(path)
