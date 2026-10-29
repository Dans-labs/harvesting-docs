# Search API

The Dataverse Search API is useful when you need a filtered selection of datasets
instead of the complete contents of an archive. The official documentation is in
the [Dataverse API Guide](https://guides.dataverse.org/en/latest/api/search.html).

The examples below use `https://dataverse.nl` as the Dataverse installation. Replace it with the URL of the installation you want to query.

**Note:** Later Dataverse versions enforce CORS restrictions, so client-side (browser JavaScript) queries to the Search API are mostly not possible. Make the requests from a server-side script instead.

## First query

The basic endpoint is:

```text
https://dataverse.nl/api/search?q=*
```

Open the URL in a browser or request it from the command line. The JSON response is
under `data`. A search can return datasets, files, and dataverses. Restrict it to
datasets with `type=dataset`:

```text
https://dataverse.nl/api/search?q=*&type=dataset
```

The response includes the matching items in `data.items` and the total number of
matches in `data.total_count`.

## Filtering and paging

Use `q` for the search expression. For example, this request returns the first ten
datasets in the `dccd` dataverse subtree:

```text
https://dataverse.nl/api/search?q=*&subtree=dccd&type=dataset&start=0&per_page=10
```

`start` is zero-based. `per_page` controls the page size. Repeat the request with a
larger `start` value to retrieve the next page. Dataverse limits how far a single
search can page, so do not assume that the Search API is suitable for extracting an
entire large archive. For bulk extraction, see [Export API](ExportAPI.md) and
[OAI-PMH](OAI-PMH.md).

Search expressions can use field names and Boolean operators. This example selects
datasets whose `dccd-longitude` value is within the full longitude range:

```text
https://dataverse.nl/api/search?q=dccd-longitude%3A%5B-180.0%20TO%20180.0%5D&subtree=dccd&type=dataset&start=0&per_page=10
```

The encoded query value is equivalent to:

```text
dccd-longitude:[-180.0 TO 180.0]
```

When constructing URLs in code, use a URL-encoding function instead of assembling
encoded values by hand. The [Solr notes](Solr.md) provide additional background on
the query syntax used by Dataverse.

## Returning metadata fields

Search results include citation metadata by default. Request additional metadata
blocks with `metadata_fields`. For example, `dccd:*` asks Dataverse.nl for fields
from the `dccd` metadata block:

```text
https://dataverse.nl/api/search?q=*&subtree=dccd&type=dataset&metadata_fields=dccd%3A%2A&start=0&per_page=10
```

To discover field names and their values, inspect a dataset export first. See the
[Export API](ExportAPI.md), or try this example:

```text
https://dataverse.nl/api/datasets/export?exporter=dataverse_json&persistentId=doi%3A10.34894%2FRPOYUA
```

The Dataverse web interface also offers JSON from a dataset's **Metadata** tab.

## Command-line and Python examples

`curl` and `jq` are convenient for inspecting responses or building shell scripts:

```bash
curl "https://dataverse.nl/api/search?q=*&type=dataset&per_page=10" | jq '.data.items'
```

The same request from Python uses the `requests` library:

```python
import requests

response = requests.get(
		"https://dataverse.nl/api/search",
		params={"q": "*", "type": "dataset", "per_page": 10},
		timeout=30,
)
response.raise_for_status()
results = response.json()["data"]["items"]
```

If a command-line request is blocked by a network or scraping policy, try the URL
in a browser. Browser-based JavaScript requests can instead be affected by CORS;
in that case, make the request from a server-side script or through a suitable
proxy.

## Metrics API

If the archive has a dataverse hierarchy, this is not easy to construct from search results. Luckely the metrics API has an endpoint to get this information.  
```text
https://dataverse.nl/api/info/metrics/tree
```

The [Metrics API](https://guides.dataverse.org/en/latest/api/metrics.html) provides
archive-level information without requiring you to analyse harvested metadata. For
example, it can provide download statistics. 

Dataverse.nl also exposes these metrics with charts at
<https://dataverse.nl/dataverse-metrics>.
