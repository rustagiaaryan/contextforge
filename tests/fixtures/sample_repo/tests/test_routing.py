from app.routing import Mount, dispatch


def test_mounted_prefix_is_preserved() -> None:
    assert dispatch(Mount("/api"), "/users") == "/api/users"
