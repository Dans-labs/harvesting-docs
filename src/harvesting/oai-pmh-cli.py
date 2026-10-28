"""Command-line interface for the OAI-PMH harvesting client."""

import argparse
import datetime
import importlib.util
import xml.etree.ElementTree as ET
import os
import sys
from contextlib import contextmanager
from pathlib import Path

import requests
from rich.console import Console
from rich.markup import escape
from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn

try:
    from rich_argparse import RichHelpFormatter
except ImportError:
    RichHelpFormatter = argparse.HelpFormatter


def _load_oai_module():
    module_path = Path(__file__).with_name("oai-pmh.py")
    spec = importlib.util.spec_from_file_location("oai_pmh", module_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Unable to load OAI-PMH client from {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


oai_module = _load_oai_module()
OAIError = oai_module.OAIError
retrieve_identifiers = oai_module.retrieve_identifiers
retrieve_records = oai_module.retrieve_records
OAI_NAMESPACE = oai_module.OAI_NAMESPACE
OAI_DC_NAMESPACE = oai_module.OAI_DC_NAMESPACE
DC_NAMESPACE = oai_module.DC_NAMESPACE
XSI_NAMESPACE = oai_module.XSI_NAMESPACE

ET.register_namespace("oai", OAI_NAMESPACE)
ET.register_namespace("oai_dc", OAI_DC_NAMESPACE)
ET.register_namespace("dc", DC_NAMESPACE)
ET.register_namespace("xsi", XSI_NAMESPACE)

console = Console()


class RichArgumentParser(argparse.ArgumentParser):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("formatter_class", RichHelpFormatter)
        super().__init__(*args, **kwargs)


@contextmanager
def progress_bar(description, unit):
    """Yield a callback that advances a progress bar by one item."""
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        TextColumn(f"[cyan]{{task.completed}} {unit}"),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task(description, total=None)
        yield lambda _item: progress.update(task, advance=1)


def cli_retrieve_identifiers(url, from_date=None, output_file=None, show_identifiers=False, quiet=False, oai_set=None, metadata_prefix='oai_dc'):
    """Retrieve identifiers to a file, standard output, or both."""
    if output_file is None and not show_identifiers:
        raise ValueError("--show-identifiers is required when output_file is omitted.")

    options = dict(output_file=output_file, from_date=from_date, oai_set=oai_set, metadata_prefix=metadata_prefix)
    if quiet:
        return retrieve_identifiers(url, **options)
    if show_identifiers:
        return retrieve_identifiers(url, on_identifier=print, **options)

    console.print(f"Harvesting identifiers from [cyan]{url}[/cyan]")
    with progress_bar("Writing OAI-PMH identifiers", "identifiers") as advance:
        identifier_count = retrieve_identifiers(url, on_identifier=advance, **options)
    console.print(
        f"[green]Completed.[/green] Wrote {identifier_count} identifiers to "
        f"[cyan]{output_file}[/cyan]"
    )
    return identifier_count


def cli_retrieve_records(url, output_dir, metadata_prefix='oai_dc', from_date=None, oai_set=None):
    with progress_bar("Writing OAI-PMH records", "records") as advance:
        return retrieve_records(
            url, output_dir, metadata_prefix=metadata_prefix, from_date=from_date, oai_set=oai_set,
            on_record=advance,
        )


OAI_DATE_FORMATS = ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%SZ")


def oai_date(value):
    """Argparse type for the two OAI-PMH date granularities."""
    for date_format in OAI_DATE_FORMATS:
        try:
            datetime.datetime.strptime(value, date_format)
            return value
        except ValueError:
            pass
    raise argparse.ArgumentTypeError("use YYYY-MM-DD or YYYY-MM-DDThh:mm:ssZ")


def add_from_date_argument(parser):
    parser.add_argument(
        "--from",
        dest="from_date",
        type=oai_date,
        help="Only harvest records changed since this date (YYYY-MM-DD or YYYY-MM-DDThh:mm:ssZ)",
    )


def add_set_argument(parser):
    parser.add_argument(
        "--set",
        dest="oai_set",
        help="Restrict harvesting to an OAI-PMH set (setSpec)",
    )


def add_metadata_prefix_argument(parser):
    parser.add_argument(
        "-m", "--metadata-prefix", default="oai_dc",
        help="OAI-PMH metadata prefix (default: oai_dc)",
    )


def run_identifiers(arguments, parser):
    if arguments.output_file is None and not arguments.show_identifiers:
        parser.error("output_file is required unless --show-identifiers is used")

    if arguments.output_file and os.path.exists(arguments.output_file):
        if not os.access(arguments.output_file, os.W_OK):
            parser.error(f"Output file {arguments.output_file} is not writable")
        if os.path.getsize(arguments.output_file) > 0 and not arguments.force:
            parser.error(
                f"Output file {arguments.output_file} is not empty; use --force to overwrite it"
            )

    cli_retrieve_identifiers(
        arguments.url,
        from_date=arguments.from_date,
        output_file=arguments.output_file,
        show_identifiers=arguments.show_identifiers,
        quiet=arguments.quiet,
        oai_set=arguments.oai_set,
        metadata_prefix=arguments.metadata_prefix,
    )


def run_records(arguments, parser):
    cli_retrieve_records(
        arguments.url,
        arguments.output_dir,
        metadata_prefix=arguments.metadata_prefix,
        from_date=arguments.from_date,
        oai_set=arguments.oai_set,
    )


def main():
    parser = RichArgumentParser(
        description="Retrieve identifiers or records from an OAI-PMH endpoint."
    )
    subparsers = parser.add_subparsers(
        dest="command", required=True, parser_class=RichArgumentParser
    )

    identifiers_parser = subparsers.add_parser(
        "identifiers",
        help="Retrieve OAI-PMH identifiers",
        description="Retrieve OAI-PMH identifiers and write them to a file or standard output.",
    )
    identifiers_parser.add_argument("url", help="Base URL of the OAI-PMH endpoint")
    identifiers_parser.add_argument(
        "-o", "--output-file",
        help="Optional file to receive one identifier per line",
    )
    output_options = identifiers_parser.add_mutually_exclusive_group()
    output_options.add_argument("-s", "--show-identifiers", action="store_true", help="Print each identifier")
    output_options.add_argument("-q", "--quiet", action="store_true", help="Suppress terminal output")
    identifiers_parser.add_argument(
        "-f", "--force",
        action="store_true",
        help="Overwrite an existing non-empty output file",
    )
    add_from_date_argument(identifiers_parser)
    add_set_argument(identifiers_parser)
    add_metadata_prefix_argument(identifiers_parser)

    records_parser = subparsers.add_parser(
        "records",
        help="Retrieve OAI-PMH records",
        description="Retrieve OAI-PMH records and write them as XML files.",
    )
    records_parser.add_argument("url", help="Base URL of the OAI-PMH endpoint")
    records_parser.add_argument(
        "-o", "--output-dir", required=True,
        help="Directory to receive one XML file per record",
    )
    add_metadata_prefix_argument(records_parser)
    add_from_date_argument(records_parser)
    add_set_argument(records_parser)

    arguments = parser.parse_args()
    try:
        if arguments.command == "identifiers":
            run_identifiers(arguments, identifiers_parser)
        elif arguments.command == "records":
            run_records(arguments, records_parser)
    except (OAIError, requests.RequestException) as error:
        console.print(f"[red]Error:[/red] {escape(str(error))}")
        sys.exit(1)


if __name__ == "__main__":
    main()