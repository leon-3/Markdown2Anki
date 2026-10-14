"""``m2a`` entry point: the Typer app, global options, and the exit-code handling around it."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import List, Optional

import typer

try:
    from typer._click import exceptions as click_exceptions  # typer >= 0.24 ships its own copy of click
except ImportError:  # older typer depends on the click package
    from click import exceptions as click_exceptions

from . import __version__, ui
from .commands import init, inspect, sync, templates, unflag
from .commands._shared import GlobalOptions
from .config import CONFIG_FILE_NAME, user_config_path

app = typer.Typer(help="Convert Obsidian flashcard notes into Anki cards.", no_args_is_help=True,
                  add_completion=False, rich_markup_mode="rich", pretty_exceptions_enable=False)


def _version(value: bool) -> None:
    if value:
        typer.echo(f"m2a {__version__}")
        raise typer.Exit()


@app.callback()
def main_options(
    ctx: typer.Context,
    config: Optional[Path] = typer.Option(None, "-c", "--config",
                                          help=f"Path to {CONFIG_FILE_NAME} (default: search upwards, then "
                                               f"{user_config_path()})."),
    vault: Optional[Path] = typer.Option(None, "--vault", help="Override the vault directory from the config."),
    trace: bool = typer.Option(False, "--trace", help="Log each phase to stderr (also: M2A_TRACE=1)."),
    version: bool = typer.Option(False, "--version", callback=_version, is_eager=True, help="Show the version."),
) -> None:
    ctx.obj = GlobalOptions(config=config, vault=vault)
    if trace:
        ui.enable_trace()
    ui.trace(f"start: command={ctx.invoked_subcommand} cwd={Path.cwd()}")


app.command("init", help="Create the config interactively (refuses to overwrite an existing one).")(init.run)
app.command("config", help="Show which config is in use and its contents.")(inspect.config)
app.command("check", help="Parse every note and report problems; changes nothing.")(inspect.check)
app.command("status", help="Per course: cards total / added / pending.")(inspect.status)
app.command("sync", help="Export pending cards and mark them as added.")(sync.run)
app.command("unflag", help="Remove ADDED flags so cards are exported again as new cards.")(unflag.run)
app.command("templates", help="Compare the local card templates with the note types in Anki and push them "
                              "(AnkiConnect).")(templates.run)


def main(argv: Optional[List[str]] = None) -> int:
    """Run the app and translate everything into an exit code (used by the ``m2a`` script and the tests)."""
    try:
        sys.stdout.reconfigure(line_buffering=True)  # show output promptly even through a pipe
    except (AttributeError, ValueError):
        pass
    try:
        result = app(args=argv, prog_name="m2a", standalone_mode=False)
        return result if isinstance(result, int) else 0
    except typer.Exit as exc:
        return exc.exit_code
    except click_exceptions.UsageError as exc:
        exc.show()
        return 0 if isinstance(exc, getattr(click_exceptions, "NoArgsIsHelpError", ())) else 2
    except (FileNotFoundError, ValueError) as exc:
        ui.error(str(exc))
        return 2
    except KeyboardInterrupt:
        ui.console.print()
        ui.console.print("[dim]aborted - nothing written[/]")
        return 130


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
