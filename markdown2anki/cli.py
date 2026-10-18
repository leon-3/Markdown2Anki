"""``m2a`` entry point: the Typer app, global options, and the exit-code handling around it."""
from __future__ import annotations

import sys
from pathlib import Path

import typer

try:
    from typer._click import exceptions as click_exceptions  # typer >= 0.24 ships its own copy of click
except ImportError:  # older typer depends on the click package
    from click import exceptions as click_exceptions

from . import __version__, ui
from .commands import init, inspect, orphans, sync, templates, unflag
from .commands._shared import GlobalOptions
from .config import CONFIG_FILE_NAME, user_config_path

app = typer.Typer(help="Convert Obsidian flashcard notes into Anki cards.", no_args_is_help=True,
                  add_completion=True, rich_markup_mode="rich", pretty_exceptions_enable=False)


def _version(value: bool) -> None:
    if value:
        typer.echo(f"m2a {__version__}")
        raise typer.Exit()


@app.callback()
def main_options(
    ctx: typer.Context,
    config: Path | None = typer.Option(None, "-c", "--config",
                                       help=f"Path to {CONFIG_FILE_NAME} (default: search upwards, then "
                                            f"{user_config_path()})."),
    vault: Path | None = typer.Option(None, "--vault", help="Override the vault directory from the config."),
    trace: bool = typer.Option(False, "--trace", help="Log each phase to stderr (also: M2A_TRACE=1)."),
    version: bool = typer.Option(False, "--version", callback=_version, is_eager=True, help="Show the version."),
) -> None:
    ctx.obj = GlobalOptions(config=config, vault=vault)
    if trace:
        ui.enable_trace()
    ui.trace(f"start: command={ctx.invoked_subcommand} cwd={Path.cwd()}")


# Core Workflow
app.command(
    "status",
    rich_help_panel="Core Workflow",
    help="Show cards overview per course and run vault health check.",
)(inspect.status)
app.command(
    "sync",
    rich_help_panel="Core Workflow",
    help="Export new or updated cards to Anki and flag them in the vault.",
)(sync.run)

# Setup & Configuration
app.command(
    "init",
    rich_help_panel="Setup & Configuration",
    help="Interactive wizard to create m2a.toml.",
)(init.run)
app.command(
    "config",
    rich_help_panel="Setup & Configuration",
    help="Inspect, validate, or edit the active configuration.",
)(inspect.config)
app.command(
    "templates",
    rich_help_panel="Setup & Configuration",
    help="Compare local card templates with Anki note types and push them.",
)(templates.run)

# Maintenance & Cleanup
app.command(
    "orphans",
    rich_help_panel="Maintenance & Cleanup",
    help="Detect and resolve drift between Obsidian vault and Anki.",
)(orphans.run)
app.command(
    "unflag",
    rich_help_panel="Maintenance & Cleanup",
    help="Remove ADDED/DELETED flags so cards are exported again as new.",
)(unflag.run)

# Backward-compatible hidden alias
app.command("check", hidden=True)(inspect.check)


def main(argv: list[str] | None = None) -> int:
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
    except BrokenPipeError:
        return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
