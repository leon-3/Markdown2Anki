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
from .commands import deleted, init, inspect, sync, unflag
from .commands._shared import GlobalOptions
from .config import CONFIG_FILE_NAME, user_config_path

app = typer.Typer(
    help="Convert Obsidian flashcard notes into Anki cards via AnkiConnect or standalone .apkg packages.",
    no_args_is_help=True,
    add_completion=False,
    rich_markup_mode="rich",
    pretty_exceptions_enable=False,
)


def _version(value: bool) -> None:
    if value:
        typer.echo(f"m2a {__version__}")
        raise typer.Exit()


@app.callback()
def main_options(
    ctx: typer.Context,
    config: Path | None = typer.Option(
        None, "-c", "--config",
        help=f"Path to {CONFIG_FILE_NAME} (default: search upwards, then {user_config_path()}).",
    ),
    vault: Path | None = typer.Option(None, "--vault", help="Override the vault directory from the config."),
    trace: bool = typer.Option(False, "--trace", help="Log execution phases to stderr (also enabled via M2A_TRACE=1)."),
    version: bool = typer.Option(False, "--version", callback=_version, is_eager=True, help="Show the version and exit."),
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
    epilog="""[bold cyan]Examples:[/]\n  [dim]$[/] [bold]m2a status[/]                     Overview of all courses and health check\n  [dim]$[/] [bold]m2a status -v[/]                  Detailed card list and diagnostics\n  [dim]$[/] [bold]m2a status --course "CS101"[/]    Filter by course name or tag\n  [dim]$[/] [bold]m2a status -f "Notes/W01.md"[/]   Inspect a single markdown note\n""",
)(inspect.status)

app.command(
    "sync",
    rich_help_panel="Core Workflow",
    help="Export new or updated cards to Anki and flag them in the vault.",
    epilog="""[bold cyan]Examples:[/]\n  [dim]$[/] [bold]m2a sync -n[/]                    Dry run: preview cards to export without changes\n  [dim]$[/] [bold]m2a sync[/]                       Export new cards to Anki and write ADDED flags\n  [dim]$[/] [bold]m2a sync -u[/]                    Export new cards and update modified existing cards\n  [dim]$[/] [bold]m2a sync -u -v[/]                 Update cards with detailed card table\n  [dim]$[/] [bold]m2a sync --course "CS101"[/]     Sync cards from a specific course\n  [dim]$[/] [bold]m2a sync -f "Notes/W01.md"[/]    Sync only cards from a specific note file\n  [dim]$[/] [bold]m2a sync --target apkg -o out.apkg[/]  Export offline .apkg package\n""",
)(sync.run)

# Setup & Configuration
app.command(
    "init",
    rich_help_panel="Setup & Configuration",
    help="Interactive wizard to create m2a.toml.",
    epilog="""[bold cyan]Examples:[/]\n  [dim]$[/] [bold]m2a init[/]                       Interactive setup wizard (creates ~/.config/m2a/m2a.toml)\n  [dim]$[/] [bold]m2a init --here[/]                Create local ./m2a.toml in current directory\n  [dim]$[/] [bold]m2a init --vault ~/Notes -y[/]    Non-interactive setup with defaults\n""",
)(init.run)

app.command(
    "config",
    rich_help_panel="Setup & Configuration",
    help="Inspect, validate, or edit the active configuration.",
    epilog="""[bold cyan]Examples:[/]\n  [dim]$[/] [bold]m2a config[/]                     Display active configuration and AnkiConnect status\n  [dim]$[/] [bold]m2a config --validate[/]          Check configuration semantics and verify Anki connection\n  [dim]$[/] [bold]m2a config --path[/]              Show path to active m2a.toml\n  [dim]$[/] [bold]m2a config --raw[/]               Print raw TOML configuration file\n  [dim]$[/] [bold]m2a config --edit[/]              Open active config in $EDITOR\n""",
)(inspect.config)

# Maintenance & Cleanup
app.command(
    "deleted",
    rich_help_panel="Maintenance & Cleanup",
    help="Detect and resolve deleted cards and drift between Obsidian vault and Anki.",
    epilog="""[bold cyan]Examples:[/]\n  [dim]$[/] [bold]m2a deleted[/]                    Detect drift (cards removed from vault or deleted in Anki)\n  [dim]$[/] [bold]m2a deleted --suspend -n[/]       Dry run: preview which orphaned cards would be suspended\n  [dim]$[/] [bold]m2a deleted --suspend[/]          Suspend removed vault cards in Anki (preserves review history)\n  [dim]$[/] [bold]m2a deleted --delete[/]           Permanently delete orphaned notes from Anki\n  [dim]$[/] [bold]m2a deleted --mark-deleted[/]     Mark cards missing in Anki as DELETED in vault notes\n  [dim]$[/] [bold]m2a deleted --recreate[/]         Re-export cards missing in Anki back into Anki\n""",
)(deleted.run)

app.command(
    "unflag",
    rich_help_panel="Maintenance & Cleanup",
    help="Remove ADDED/DELETED flags so cards are exported again as new.",
    epilog="""[bold cyan]Examples:[/]\n  [dim]$[/] [bold]m2a unflag -n[/]                  Dry run: preview which flags would be removed\n  [dim]$[/] [bold]m2a unflag[/]                     Remove ADDED and DELETED flags from all vault cards\n  [dim]$[/] [bold]m2a unflag -f "Notes/W01.md"[/]  Remove flags only from a specific note file\n  [dim]$[/] [bold]m2a unflag --course "CS101"[/]   Remove flags only for a specific course\n  [dim]$[/] [bold]m2a unflag --legacy[/]            Remove only legacy 'ADDED: ' flags (without ID)\n""",
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
