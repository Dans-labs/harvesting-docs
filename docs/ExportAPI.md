# Export Metadata API

The Dataverse metadata export API returns the metadata of a single published dataset in one of several formats. It is the best way to get all the public metadata of a dataset, especially in the `dataverse_json` format, which [OAI-PMH](OAI-PMH.md) cannot deliver (through OAI it only yields landing pages).

The official documentation is in the Dataverse guides:

- [API Guide: Native API, export metadata](https://guides.dataverse.org/en/latest/api/native-api.html#export-metadata-of-a-dataset-in-various-formats)
- [API Guide: overview of all APIs](https://guides.dataverse.org/en/latest/api/index.html)
- [User Guide: metadata export formats](https://guides.dataverse.org/en/latest/user/dataset-management.html#metadata-export-formats)

The guides for your Dataverse version are the authority on exporter names and behaviour; the exact set of formats can differ between versions and installations.

## Endpoint

```text
GET <base url>/api/datasets/export?exporter=<exporter>&persistentId=<pid>
```

- `exporter`: the export format, for example `dataverse_json`
- `persistentId`: the persistent identifier (PID) of the dataset, for example `doi:10.5072/FK2/HJVOXL`

Only published datasets can be exported. No API token is needed for public metadata, and drafts and restricted metadata are not available this way.

### Available exporters

Common exporters are `dataverse_json`, `ddi`, `oai_ddi`, `oai_dc`, `dcterms`, `Datacite`, `schema.org` and `OAI_ORE`. Ask the installation which ones it supports:

```bash
curl "https://demo.dataverse.org/api/info/exportFormats"
```

`dataverse_json` contains all metadata fields of a dataset, but it has no schema and is tied to the internal structure of Dataverse, so it can change between versions. The other formats are standardized, but contain less information.

## Examples with curl

```bash
BASE=https://demo.dataverse.org

# JSON export; -G with --data-urlencode takes care of the ':' and '/' in the PID
curl -G "$BASE/api/datasets/export" \
  --data-urlencode 'exporter=dataverse_json' \
  --data-urlencode 'persistentId=doi:10.5072/FK2/HJVOXL'

# pretty print and select a part with jq
curl -sG "$BASE/api/datasets/export" \
  --data-urlencode 'exporter=dataverse_json' \
  --data-urlencode 'persistentId=doi:10.5072/FK2/HJVOXL' \
  | jq '.datasetVersion.metadataBlocks.citation.fields[] | select(.typeName == "title")'

# an XML format
curl -G "$BASE/api/datasets/export" \
  --data-urlencode 'exporter=ddi' \
  --data-urlencode 'persistentId=doi:10.5072/FK2/HJVOXL'
```

A PID that does not exist or is not published gives an HTTP error (typically 404), not an empty result.

## Getting the dataset identifiers

You need the PIDs of the datasets first. Possible sources:

- [OAI-PMH](OAI-PMH.md) `ListIdentifiers`, this is the usual first step of the two step process described in the [Overview](Overview.md)
- the [Search API](SearchAPI.md), if you need a filtered selection
- [Solr](Solr.md) or [Postgres](Postgres.md), if you have access to the system

## Using the code in this repository

The client is in [src/harvesting/dv-export-api.py](../src/harvesting/dv-export-api.py) and the command-line interface in [src/harvesting/dv-export-api-cli.py](../src/harvesting/dv-export-api-cli.py). See the [README](../README.md) for installation with `uv`. The tests are in [tests/test_dv_export_api.py](../tests/test_dv_export_api.py).

### Command line

```bash
# one dataset
uv run dv-export-api https://demo.dataverse.org -p doi:10.7910/DVN/TJCLKP

# all datasets in a file with one PID per line, for example created with the OAI-PMH client
uv run dv-export-api https://demo.dataverse.org -f ./data/pids.txt -e dataverse_json

# choose where the output goes, pause between requests, and resume an interrupted export
uv run dv-export-api https://demo.dataverse.org -f ./data/pids.txt \
  --parent-dir ./exports --delay 1 --skip-existing
```

Files are written to a `metadata_<host>` directory, one file per dataset, named after the PID and exporter with `/` and `:` replaced by `_`, for example `exports/metadata_demo.dataverse.org/doi_10.5072_FK2_HJVOXL.dataverse_json.json`. The extension (`json`, `xml` or `txt`) follows the response of the server.

Failures for individual PIDs are logged to `dv-export-api.log`, and the exit code is 1 if any export failed. See the README for all options.

### Python

`DataverseExportClient` wraps the endpoint. The module file name contains a hyphen, so load it by path, as the CLI and the tests do:

```python
import importlib.util

spec = importlib.util.spec_from_file_location("dv_export_api", "src/harvesting/dv-export-api.py")
dv_export_api = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dv_export_api)

client = dv_export_api.DataverseExportClient("https://demo.dataverse.org")

metadata = client.export_dataset_metadata("doi:10.7910/DVN/TJCLKP", "dataverse_json")  # parsed JSON for JSON formats, text otherwise
client.export_dataset_metadata_for_pid("doi:10.7910/DVN/TJCLKP", "ddi", "./exports")  # write to a file
client.export_dataset_metadata_for_pids("./data/pids.txt", "dataverse_json", "./exports", delay=1, skip_existing=True)
```

Requests time out after 60 seconds, and throttled or temporarily failing responses (HTTP 429, 502, 503, 504) are retried up to 3 times. Use a delay when exporting many datasets, to avoid overloading the server.

## Links

- [Dataverse guides](https://guides.dataverse.org/en/latest/)
- [Dataverse API Guide](https://guides.dataverse.org/en/latest/api/index.html)
- [Overview](Overview.md)
- [OAI-PMH](OAI-PMH.md)
- [Search API](SearchAPI.md)
