"""Harvesting package entry points."""

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path


def _load_cli_module(filename: str, module_name: str):
    module_path = Path(__file__).with_name(filename)
    spec = spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Unable to load CLI from {module_path}")

    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> None:
    """Run the OAI-PMH CLI via the package entry point."""
    cli_module = _load_cli_module("oai-pmh-cli.py", "harvesting_oai_pmh_cli")
    cli_module.main()


def main_dv_export_api() -> None:
    """Run the Dataverse export CLI via the package entry point."""
    cli_module = _load_cli_module("dv-export-api-cli.py", "harvesting_dv_export_api_cli")
    cli_module.main()


__all__ = ["main", "main_dv_export_api"]
