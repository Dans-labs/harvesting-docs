# OAI-PMH

The [Open Archives Initiative Protocol for Metadata Harvesting](https://www.openarchives.org/OAI/openarchivesprotocol.html) (OAI-PMH) is a standard protocol for harvesting metadata from repositories. Dataverse supports it, usually at `<base url>/oai`, for example `https://demo.dataverse.org/oai`.

Requests are plain HTTP GET requests with a `verb` parameter, and the response is XML. Only published, non-restricted metadata is available, in the formats the installation enables (typically `oai_dc` and `oai_datacite`; see `ListMetadataFormats`).

The Dataverse `dataverse_json` export format is listed by some installations, but through OAI-PMH it only yields landing pages, not the JSON itself. Use the [Export API](ExportAPI.md) for that.

## Much used verbs

| Verb | Purpose | Example |
| --- | --- | --- |
| `Identify` | Information about the repository (name, earliest datestamp, date granularity) | `?verb=Identify` |
| `ListMetadataFormats` | The metadata formats (`metadataPrefix`) the server offers | `?verb=ListMetadataFormats` |
| `ListSets` | The sets (collections) you can restrict a harvest to | `?verb=ListSets` |
| `ListIdentifiers` | Only the record headers (identifier, datestamp, set), no metadata | `?verb=ListIdentifiers&metadataPrefix=oai_dc` |
| `ListRecords` | Headers and metadata of all matching records | `?verb=ListRecords&metadataPrefix=oai_datacite` |
| `GetRecord` | One record by identifier | `?verb=GetRecord&identifier=doi:10.5072/FK2/HJVOXL&metadataPrefix=oai_datacite` |

`ListIdentifiers` and `ListRecords` accept these optional arguments:

- `metadataPrefix` (required): the metadata format, for example `oai_dc` or `oai_datacite`
- `set`: only records in this set (`setSpec`)
- `from` and `until`: only records created, changed or deleted in this period, as `YYYY-MM-DD` or `YYYY-MM-DDThh:mm:ssZ` (the granularity is reported by `Identify`)

### Examples with curl

```bash
BASE=https://demo.dataverse.org/oai

curl "$BASE?verb=Identify"
curl "$BASE?verb=ListMetadataFormats"
curl "$BASE?verb=ListSets"

# first page of identifiers in a set, changed since a date
curl -G "$BASE" \
  --data-urlencode 'verb=ListIdentifiers' \
  --data-urlencode 'metadataPrefix=oai_datacite' \
  --data-urlencode 'set=controlTestSet' \
  --data-urlencode 'from=2026-01-01'

# a single record
curl -G "$BASE" \
  --data-urlencode 'verb=GetRecord' \
  --data-urlencode 'identifier=doi:10.5072/FK2/HJVOXL' \
  --data-urlencode 'metadataPrefix=oai_datacite'
```

## Resumption tokens

A server returns long lists in pages. If more results are available, the response ends with a `<resumptionToken>` element. To get the next page, send a new request with only `verb` and `resumptionToken`; all other arguments are not allowed in that request. The last page has an empty token.

```bash
curl -G "$BASE" \
  --data-urlencode 'verb=ListIdentifiers' \
  --data-urlencode 'resumptionToken=<token from the previous response>'
```

Tokens can expire, so process the pages promptly.

## Errors

Errors are reported inside a `200 OK` response as `<error code="...">` elements. Common codes are `badArgument`, `badResumptionToken`, `cannotDisseminateFormat` (unknown `metadataPrefix`), `idDoesNotExist` and `noSetHierarchy`. The code `noRecordsMatch` is not a failure; it means the selection is empty.

## Deleted records

Records that were removed can show up with `status="deleted"` in their header, and have no metadata. The client in this repository skips them, so if you keep a local copy, deleted records are not removed from it automatically.

## Incremental harvesting

Harvest regularly with the `from` argument set to (a bit before) the time of your previous harvest. You then only receive new, changed and deleted records, which keeps your local copy complete without downloading everything each time.

## Using the code in this repository

The client is in [src/harvesting/oai-pmh.py](../src/harvesting/oai-pmh.py) and the command-line interface in [src/harvesting/oai-pmh-cli.py](../src/harvesting/oai-pmh-cli.py). See the [README](../README.md) for installation with `uv`.

### Command line

```bash
# the identifiers of all datasets, written to a file
uv run oai-pmh identifiers https://demo.dataverse.org/oai -o ./data/pids.txt

# print identifiers instead of writing them
uv run oai-pmh identifiers https://demo.dataverse.org/oai --show-identifiers

# one XML file per record, for a set and since a date
uv run oai-pmh records https://demo.dataverse.org/oai -o ./records \
  -m oai_datacite --set controlTestSet --from 2026-01-01
```

The identifiers file can be used as input for the [Export API](ExportAPI.md) client (`uv run dv-export-api -f ./data/pids.txt`), which gives the two step process described in the [Overview](Overview.md). The [records](../records) directory contains example output.

### Python

`OAIClient` has a method for each verb. The `iter_*` methods follow resumption tokens for you and yield items page by page, so memory use stays low for large harvests:

The file name contains a hyphen, so it cannot be imported with a plain `import`; load it by path, as the CLI and the tests do:

```python
import importlib.util

spec = importlib.util.spec_from_file_location("oai_pmh", "src/harvesting/oai-pmh.py")
oai_pmh = importlib.util.module_from_spec(spec)
spec.loader.exec_module(oai_pmh)

client = oai_pmh.OAIClient("https://demo.dataverse.org/oai")

client.identify()               # Identify
client.list_metadata_formats()  # ListMetadataFormats
client.list_sets()              # ListSets

for identifier in client.iter_identifiers(metadata_prefix="oai_datacite", oai_set="controlTestSet"):
    print(identifier)

record = client.get_record("doi:10.5072/FK2/HJVOXL", metadata_prefix="oai_datacite")
```

The client sets a request timeout, retries throttled or temporarily failing responses (HTTP 429, 502, 503, 504) and raises `OAIError` for OAI-PMH error codes. The tests are in [tests/test_oai_pmh.py](../tests/test_oai_pmh.py).

## Links

- [OAI-PMH specification](https://www.openarchives.org/OAI/openarchivesprotocol.html)
- [Dataverse guide on OAI-PMH](https://guides.dataverse.org/en/latest/admin/harvestserver.html)
- [Overview](Overview.md)
