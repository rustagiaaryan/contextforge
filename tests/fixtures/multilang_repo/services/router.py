from services.paths import join_path


class Mount:
    def __init__(self, prefix: str) -> None:
        self.prefix = prefix

    def resolve(self, path: str) -> str:
        return join_path(self.prefix, path)
