"""Command-line interface for the Dataverse metadata export client."""

import argparse
import importlib.util
import logging
import os
import platform
import random
import signal
import time
from pathlib import Path

from rich.console import Console
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
DataverseExportClient = export_module.DataverseExportClient
export_dataset_metadata_for_pid = export_module.export_dataset_metadata_for_pid
export_dataset_metadata_for_pids = export_module.export_dataset_metadata_for_pids
count_pids = export_module.count_pids
get_save_dir_or_file_name = export_module.get_save_dir_or_file_name

logging.basicConfig(
    filename="dv-export-api.log",
    level=logging.ERROR,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)
console = Console()

_pause_requested = False


def _request_pause(signum, frame):
    global _pause_requested
    _pause_requested = True


if platform.system() == "Windows":
    PAUSE_KEY_LABEL = "Ctrl-C"
    signal.signal(signal.SIGINT, _request_pause)
else:
    PAUSE_KEY_LABEL = "Ctrl-Z"
    signal.signal(signal.SIGTSTP, _request_pause)


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


def nice_delay():
    delay = random.uniform(0.1, 0.3)
    delay += min(random.lognormvariate(0.1, 0.3), 1.0)
    delay *= 0.2
    time.sleep(delay)


def cli_export_dataset_metadata_for_pids(url, pid_file, exporter, dirname):
    total = count_pids(pid_file)
    summary = Table(title="Dataset Metadata Export", show_header=False)
    summary.add_column(style="bold cyan")
    summary.add_column()
    summary.add_row("PID file", pid_file)
    summary.add_row("Repository", url)
    summary.add_row("Exporter", exporter)
    summary.add_row("Output directory", dirname)
    summary.add_row("PIDs to process", str(total))
    console.print(summary)

    proceed = Prompt.ask(
        "Proceed with export?",
        choices=["y", "n"],
        default="y",
        console=console,
    )
    if proceed.lower() != "y":
        console.print("[bold red]Export aborted by user.[/bold red]")
        return

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
    with Progress(
        SpinnerColumn(),
        *Progress.get_default_columns(),
        TextColumn("[progress.total]{task.total} total duration"),
        TimeElapsedColumn(),
    ) as progress:
        task = progress.add_task("Exporting dataset metadata", total=total)
        client = DataverseExportClient(url)

        with open(pid_file, "r") as file_handle:
            for line in file_handle:
                if check_for_pause(progress):
                    return

                dataset_pid = line.strip()
                if not dataset_pid:
                    continue
                progress.update(task, description=f"Exporting {dataset_pid}")
                try:
                    client.export_dataset_metadata_for_pid(
                        dataset_pid, exporter, dirname, quiet=True
                    )
                except Exception as error:
                    logger.exception("Failed to export dataset PID %s", dataset_pid)
                    console.print(
                        f"\n[bold red]Error exporting {dataset_pid}: {error}[/bold red]"
                    )
                    continue
                progress.update(task, advance=1)
                if not progress.tasks[task].finished:
                    nice_delay()
        progress.update(task, description=f"Done exporting for all {total} PIDs")

    console.print("[bold green]Done.[/bold green]")


def main():
    parser = argparse.ArgumentParser(
        description="Retrieve metadata from a Dataverse repository."
    )
    parser.add_argument("url", help="Dataverse URL; the repository that hosts the datasets")
    parser.add_argument(
        "-e", "--exporter", help="Metadata exporter to use", default="dataverse_json"
    )
    output_options = parser.add_mutually_exclusive_group()
    output_options.add_argument("-p", "--pid", help="Persistent ID of the dataset")
    output_options.add_argument(
        "-f", "--pid-file", "--pid_file", dest="pid_file",
        help="File containing persistent IDs of datasets, one per line"
    )
    parser.add_argument(
        "-q", "--quiet", default=False, action="store_true",
        help="Suppress terminal output"
    )
    args = parser.parse_args()

    from urllib.parse import urlparse

    url = args.url
    dataset_pid = args.pid
    pid_file = args.pid_file
    exporter = args.exporter
    host = urlparse(url).netloc
    dirname = f"metadata_{get_save_dir_or_file_name(host)}"
    os.makedirs(dirname, exist_ok=True)

    if pid_file:
        if args.quiet:
            export_dataset_metadata_for_pids(url, pid_file, exporter, dirname, quiet=True)
        else:
            cli_export_dataset_metadata_for_pids(url, pid_file, exporter, dirname)
    elif dataset_pid:
        export_dataset_metadata_for_pid(url, dataset_pid, exporter, dirname, quiet=args.quiet)
    else:
        raise ValueError("Either --pid or --pid_file must be provided")


if __name__ == "__main__":
    main()