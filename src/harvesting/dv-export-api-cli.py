"""Command-line interface for the Dataverse metadata export client."""

import argparse
import importlib.util
import logging
import math
import os
import platform
import signal
import sys
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlparse

import requests
from rich.console import Console
from rich.markup import escape
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.prompt import Prompt
from rich.table import Table


def _load_export_module():
    module_path = Path(__file__).with_name("dv-export-api.py")
    spec = importlib.util.spec_from_file_location("dv_export_api", module_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Unable to load Dataverse client from {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


export_module = _load_export_module()
export_dataset_metadata_for_pid = export_module.export_dataset_metadata_for_pid
export_dataset_metadata_for_pids = export_module.export_dataset_metadata_for_pids
count_pids = export_module.count_pids
get_save_dir_or_file_name = export_module.get_save_dir_or_file_name
EXPORT_EXTENSIONS = export_module.EXPORT_EXTENSIONS

LOG_FILE = "dv-export-api.log"
logger = logging.getLogger(__name__)
console = Console()
error_console = Console(stderr=True)


def _configure_logging():
    # delay=True: the log file is only created when something is actually logged.
    logging.basicConfig(
        handlers=[logging.FileHandler(LOG_FILE, delay=True)],
        level=logging.ERROR,
        format="%(asctime)s %(levelname)s %(message)s",
    )


_pause_requested = False


def _request_pause(signum, frame):
    global _pause_requested
    _pause_requested = True


IS_WINDOWS = platform.system() == "Windows"
PAUSE_KEY_LABEL = "Ctrl-C" if IS_WINDOWS else "Ctrl-Z"


@contextmanager
def pause_on_signal():
    """Route the pause key to the pause flag, only while an interactive export runs."""
    signum = signal.SIGINT if IS_WINDOWS else signal.SIGTSTP
    previous = signal.signal(signum, _request_pause)
    try:
        yield
    finally:
        signal.signal(signum, previous)


def check_for_pause(progress) -> bool:
    """Call periodically from the work loop. Returns True if the user chose to stop."""
    global _pause_requested
    if not _pause_requested:
        return False
    _pause_requested = False

    progress.stop()
    choice = Prompt.ask(
        "\n[bold yellow]Paused[/]. Resume or stop?",
        choices=["resume", "stop"],
        default="resume",
        console=console,
    )
    if choice == "stop":
        console.print("[bold orange1]Stopped[/bold orange1] by user.")
        return True

    progress.start()
    return False


DEFAULT_DELAY = export_module.DEFAULT_DELAY


def delay_scale(value):
    """Argparse type for --delay: a finite number >= 0."""
    try:
        scale = float(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"invalid number: {value!r}") from None
    if not math.isfinite(scale) or scale < 0:
        raise argparse.ArgumentTypeError("must be a finite number >= 0")
    return scale


def skip_extension(value):
    """Argparse type for the optional value of --skip-existing: a known export extension."""
    extension = value.lstrip(".").lower()
    if extension not in EXPORT_EXTENSIONS:
        raise argparse.ArgumentTypeError(f"{value!r} is not one of: {', '.join(EXPORT_EXTENSIONS)}")
    return extension


def cli_export_dataset_metadata_for_pids(url, pid_file, exporter, dirname, delay=DEFAULT_DELAY, skip_existing=False):
    """Export with a progress display; return a list of (pid, error) for the PIDs that failed."""
    total = count_pids(pid_file)
    summary = Table(title="Dataset Metadata Export", show_header=False)
    summary.add_column(style="bold cyan")
    summary.add_column()
    summary.add_row("PID file", pid_file)
    summary.add_row("Repository", url)
    summary.add_row("Exporter", exporter)
    summary.add_row("Output directory", dirname)
    summary.add_row("PIDs to process", str(total))
    if skip_existing:
        only = f".{skip_existing} files only" if isinstance(skip_existing, str) else "yes"
        summary.add_row("Skip existing", only)
    console.print(summary)

    proceed = Prompt.ask(
        "Proceed with export?",
        choices=["y", "n"],
        default="y",
        console=console,
    )
    if proceed.lower() != "y":
        console.print("[bold red]Export aborted by user.[/bold red]")
        return []

    console.print("[bold green]Starting export...[/bold green]")
    console.print(
        Panel(
            f"Press [bold]{PAUSE_KEY_LABEL}[/bold] (once!) at any time to pause. \n"
            "The current export finishes before the pause prompt appears. \n"
            "Note that it can take a while for the pause prompt to appear. ",
            title=":information: Pause controls",
            title_align="left",
            border_style="cyan",
        )
    )
    with pause_on_signal(), Progress(
        SpinnerColumn(),
        *Progress.get_default_columns(),
        TextColumn("[progress.total]{task.total} total duration"),
        TimeElapsedColumn(),
    ) as progress:
        task = progress.add_task("Exporting dataset metadata", total=total)
        stopped = False
        skipped = 0

        def before_pid(dataset_pid):
            nonlocal stopped
            stopped = check_for_pause(progress)
            if not stopped:
                progress.update(task, description=f"Exporting {escape(dataset_pid)}")
            return stopped

        def on_skip(dataset_pid):
            nonlocal skipped
            skipped += 1

        def after_pid(dataset_pid, error):
            if error:
                logger.error("Failed to export dataset PID %s", dataset_pid, exc_info=error)
                console.print(
                    f"\n[bold red]Error exporting {escape(dataset_pid)}: {escape(str(error))}[/bold red]"
                )
            progress.update(task, advance=1)

        failures = export_dataset_metadata_for_pids(
            url, pid_file, exporter, dirname, quiet=True,
            before_pid=before_pid, after_pid=after_pid, delay=delay,
            skip_existing=skip_existing, on_skip=on_skip,
        )
        if stopped:
            return failures
        progress.update(task, description=f"Processed all {total} PIDs")

    if skipped:
        console.print(f"Skipped {skipped} of {total} PIDs that were already exported.")
    if failures:
        console.print(
            f"[bold red]Done, but {len(failures)} of {total} PIDs failed.[/bold red] "
            f"See {LOG_FILE} for details."
        )
    else:
        console.print("[bold green]Done.[/bold green]")
    return failures


def main():
    parser = argparse.ArgumentParser(
        description="Retrieve metadata from a Dataverse repository."
    )
    parser.add_argument("url", help="Dataverse URL; the repository that hosts the datasets")
    parser.add_argument(
        "-e", "--exporter", help="Metadata exporter to use", default="dataverse_json"
    )
    input_options = parser.add_mutually_exclusive_group(required=True)
    input_options.add_argument("-p", "--pid", help="Persistent ID of the dataset")
    input_options.add_argument(
        "-f", "--pid-file", "--pid_file", dest="pid_file",
        help="File containing persistent IDs of datasets, one per line"
    )
    parser.add_argument(
        "-d", "--parent-dir", default=".",
        help="Directory in which the metadata_<host> output directory is created (default: current directory)"
    )
    parser.add_argument(
        "--delay", type=delay_scale, default=DEFAULT_DELAY,
        help="Scale of the randomized pause between requests when exporting a PID file; "
             "1 is roughly 0.1-1 s, 0 disables the pause (default: %(default)s)"
    )
    parser.add_argument(
        "--skip-existing", nargs="?", const=True, default=False, type=skip_extension, metavar="EXT",
        help="Skip datasets that already have an exported file in the output directory, "
             "for resuming an interrupted export. Give an extension (json, xml or txt) to count "
             "only files with that extension; write it as --skip-existing=EXT or put the URL first"
    )
    parser.add_argument(
        "-q", "--quiet", default=False, action="store_true",
        help="Suppress terminal output"
    )
    args = parser.parse_args()
    _configure_logging()

    parsed_url = urlparse(args.url)
    if parsed_url.scheme not in ("http", "https") or not parsed_url.netloc:
        parser.error("url must start with http:// or https:// and include a host")

    url = args.url
    dataset_pid = args.pid
    pid_file = args.pid_file
    exporter = args.exporter
    dirname = os.path.join(args.parent_dir, f"metadata_{get_save_dir_or_file_name(parsed_url.netloc)}")

    try:
        if pid_file:
            if args.quiet:
                failures = export_dataset_metadata_for_pids(
                    url, pid_file, exporter, dirname, quiet=True, delay=args.delay,
                    skip_existing=args.skip_existing,
                )
                for failed_pid, error in failures:
                    logger.error("Failed to export dataset PID %s: %s", failed_pid, error)
            else:
                failures = cli_export_dataset_metadata_for_pids(
                    url, pid_file, exporter, dirname, delay=args.delay, skip_existing=args.skip_existing
                )
            if failures:
                sys.exit(1)
        else:
            export_dataset_metadata_for_pid(
                url, dataset_pid, exporter, dirname, quiet=args.quiet, skip_existing=args.skip_existing
            )
    except (requests.RequestException, OSError) as error:
        error_console.print(f"[red]Error:[/red] {escape(str(error))}")
        sys.exit(1)


if __name__ == "__main__":
    main()