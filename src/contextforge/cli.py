"""ContextForge command-line entry point."""

from typing import Annotated

import typer

from contextforge import __version__

app = typer.Typer(help="Compile task-specific repository context for coding agents.")


def version_callback(value: bool) -> None:
    """Print the installed version and exit."""
    if value:
        typer.echo(f"contextforge {__version__}")
        raise typer.Exit


@app.callback()
def main(
    version: Annotated[
        bool | None,
        typer.Option("--version", callback=version_callback, is_eager=True, help="Show version."),
    ] = None,
) -> None:
    """ContextForge command group."""


if __name__ == "__main__":
    app()
