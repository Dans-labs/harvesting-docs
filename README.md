# harvesting-docs
Metadata Harvesting &amp; APIs

The information here is aimed at researchers, developers, and data scientists who want to retrieve (meta)data from the DANS archival systems.
Instead of retrieving information about a single dataset, it is often more useful for data-mining purposes to retrieve information about a large set of datasets.
Harvesting, or bulk extraction, is a machine-readable method that is better suited to this than using the user interface directly or scraping it.

The [DANS](https://dans.knaw.nl/en/) archival systems are implemented using the [Dataverse](https://dataverse.org/) repository software. This repository system supports [OAI-PMH](https://www.openarchives.org/pmh/) harvesting and has several APIs that can be used to extract metadata.
Internally, the system uses [Apache Solr](https://solr.apache.org/) for the search index and [PostgreSQL](https://www.postgresql.org/) for the database (which holds all metadata). For people who can access those internals, mostly technicians who do the maintenance, it is also possible to use those directly.


## [Read the docs...](docs/Overview.md)

## Prerequisites

Before running the harvesting tools, you need:

- Python 3.11 or newer
- uv installed on your system
- network access to the target Dataverse instance
- an understanding of the OAI-PMH and Dataverse API endpoints you want to query

Useful references:

- Python: <https://www.python.org/>
- uv: <https://docs.astral.sh/uv/>
- OAI-PMH specification: <https://www.openarchives.org/pmh/>
- Dataverse API Guide: <https://guides.dataverse.org/en/latest/api/index.html>

## Running the Python tools with uv

From the repository root, install the project environment and run the CLIs through uv:

```bash
uv sync
```

### OAI-PMH CLI

Example usage: 

```bash
uv run oai-pmh --help
uv run oai-pmh identifiers https://demo.dataverse.org/oai --output-file ids.txt
uv run oai-pmh identifiers https://demo.dataverse.org/oai --show-identifiers
uv run oai-pmh records https://demo.dataverse.org/oai --output-dir ./records
```

Both commands accept these options:

| Option | Description |
| --- | --- |
| `-m`, `--metadata-prefix` | Metadata format to harvest (default: `oai_dc`) |
| `--set` | Only harvest the given OAI-PMH set (setSpec) |
| `--from` | Only harvest records changed since this date, as `YYYY-MM-DD` or `YYYY-MM-DDThh:mm:ssZ` (the server must support that granularity) |

`identifiers` writes one identifier per line to `--output-file`, prints them with `--show-identifiers`, or does both. `--quiet` suppresses terminal output, and `--force` overwrites a non-empty output file. Deleted records are skipped.

Example, harvesting one set in a given format since a date:

```bash
uv run oai-pmh records https://demo.dataverse.org/oai -o ./records -m oai_datacite --set controlTestSet --from 2026-01-01
```

Example getting the identifiers only

```bash
uv run oai-pmh identifiers https://demo.dataverse.org/oai -o ./data/pids.txt -m oai_datacite --set controlTestSet --from 2026-01-01
```

Requests time out after 60 seconds, and throttled or temporarily failing responses (HTTP 429, 502, 503, 504) are retried up to 3 times. OAI-PMH errors, such as an unknown set, are reported as an error message with exit code 1.


### Dataverse export CLI

Example usage: 
```bash
uv run dv-export-api --help
uv run dv-export-api https://demo.dataverse.org -p doi:10.7910/DVN/TJCLKP
uv run dv-export-api https://demo.dataverse.org -f ./data/pids.txt -e dataverse_json
uv run dv-export-api https://demo.dataverse.org -f ./data/pids.txt --parent-dir ./exports
```

Metadata is written to a `metadata_<host>` directory, created in the current directory or in `--parent-dir` if given.

When exporting a PID file, `--delay` adds a randomized pause between requests (default `0`, no pause; `1` is roughly 0.1-1 s per request).

Add `--skip-existing` to resume an interrupted export: datasets that already have an exported file in the output directory are not requested again. By default an existing file counts whatever its extension (`.json`, `.xml` or `.txt`), since the extension is only known once the server responds. Give an extension as value to count only files with that extension, for example `--skip-existing=json` (the `=` form, or putting the URL first, keeps the value from being mistaken for the URL). Files are written atomically, so an interrupted run never leaves a truncated export behind.

For more details on the harvesting concepts and available APIs, see [docs/Overview.md](docs/Overview.md).

## Useful External Links

### Organizations

- DANS: <https://dans.knaw.nl/en/>

### Software

- Dataverse: <https://dataverse.org/>
- Dataverse API Guide: <https://guides.dataverse.org/en/latest/api/index.html>
- Apache Solr: <https://solr.apache.org/>
- PostgreSQL: <https://www.postgresql.org/>

### Protocols

- OAI-PMH: <https://www.openarchives.org/pmh/>

## Notes for developers

### Tests

```bash
uv run pytest
```

### Building the code

The package uses the `uv_build` backend. Build the source distribution and wheel into `dist/`:

```bash
uv build
```

### Documentation site

The documentation in [docs/](docs/) is published with [MkDocs](https://www.mkdocs.org/) and the [Material theme](https://squidfunk.github.io/mkdocs-material/); the configuration is in `mkdocs.yml`. The dependencies are in the `docs` dependency group.

Preview the site locally at <http://127.0.0.1:8000> (it reloads when files change):

```bash
uv run --only-group docs mkdocs serve
```

Build the site into `site/` and fail on broken links, as the CI does:

```bash
uv run --only-group docs mkdocs build --strict
```

The GitHub Actions workflow `.github/workflows/docs.yml` builds and deploys the site to GitHub Pages when changes to the docs are pushed to `master`. The repository's Pages source must be set to **GitHub Actions**.

When adding a page, put it in `docs/` and add it to the `nav` section of `mkdocs.yml`. Link to files outside `docs/` (source code, tests) with full GitHub URLs, because relative links to them break on the site.

