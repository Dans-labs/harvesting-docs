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
uv run oai-pmh identifiers https://demo.dataverse.org/oai
uv run oai-pmh records https://demo.dataverse.org/oai --output-dir ./records
```

### Dataverse export CLI

Example usage: 
```bash
uv run dv-export-api --help
uv run dv-export-api https://demo.dataverse.org -p doi:10.7910/DVN/TJCLKP
uv run dv-export-api https://demo.dataverse.org -f pids.txt -e dataverse_json
```

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

