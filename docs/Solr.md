# Solr

Dataverse uses [Apache Solr](https://solr.apache.org/) to index the metadata of the dataverses (collections), datasets and files it stores. 

If you have direct access to the Solr instance, you can query it without going through Dataverse. This is useful to quickly inspect metadata when you have not harvested everything.

**Advantages**
- Full control: you can use the complete Solr query API, there is no Dataverse in between.
- Fast, and supports paging, sorting, faceting and filtering.
- Can produce CSV output (`wt=csv`), which you can open in a spreadsheet application.

**Disadvantages**
- The result is flattened and not structured like the JSON from the [Export API](ExportAPI.md).
- Field names are internal to the Dataverse Solr schema and can change between versions.
- Normally only reachable from the server itself (or its internal network).

> Solr is not protected by Dataverse. The index can contain unpublished and restricted content, so never expose the Solr port publicly.

## References

- Dataverse guide: [Manually querying Solr](https://guides.dataverse.org/en/latest/admin/solr-search-index.html#manually-querying-solr)
- Solr documentation: [Query syntax and parsers](https://solr.apache.org/guide/solr/latest/query-guide/query-syntax-and-parsers.html)

## Examples

The examples assume Solr runs on `localhost:8983` with the default Dataverse core `collection1`.

### System information

Get general information, such as the Solr home directory:

```bash
curl "http://localhost:8983/solr/admin/info/system"
```

### Get a specific dataset

Quote the identifier and let curl URL-encode the query:

```bash
curl -G "http://localhost:8983/solr/collection1/select" \
  --data-urlencode 'q=identifier:"doi:10.80227/test-AMQC8Q"'
```

By inspecting the result you can see the field names, which tells you what kind of queries are possible.

### Search a field and limit the returned fields

Use `fl` to select the fields to return:

```bash
curl -G "http://localhost:8983/solr/collection1/select" \
  --data-urlencode 'q=authorName:admin' \
  --data-urlencode 'fl=dsPersistentId,authorName'
```

### Only datasets, with paging

Use a filter query (`fq`) to restrict the type, and `rows`/`start` for paging:

```bash
curl -G "http://localhost:8983/solr/collection1/select" \
  --data-urlencode 'q=*:*' \
  --data-urlencode 'fq=dvObjectType:datasets' \
  --data-urlencode 'fl=dsPersistentId,name' \
  --data-urlencode 'rows=100' \
  --data-urlencode 'start=0'
```

### CSV output

```bash
curl -G "http://localhost:8983/solr/collection1/select" \
  --data-urlencode 'q=dvObjectType:datasets' \
  --data-urlencode 'fl=dsPersistentId,name,authorName' \
  --data-urlencode 'rows=1000' \
  --data-urlencode 'wt=csv'
```

### Process JSON with jq

```bash
curl -sG "http://localhost:8983/solr/collection1/select" \
  --data-urlencode 'q=dvObjectType:datasets' \
  --data-urlencode 'fl=dsPersistentId' \
  --data-urlencode 'rows=1000' \
  | jq -r '.response.docs[].dsPersistentId'
```

## Tips

- Use `-G` with `--data-urlencode` so characters such as `:`, `"` and spaces are encoded correctly.
- Solr returns 10 rows by default; set `rows` explicitly and page with `start`.
- For large result sets, prefer cursor paging (`cursorMark` with a `sort` on the unique key) over a high `start`.
- Use `fq` for filters; they are cached and do not affect scoring.

## Related

- [Overview](Overview.md)
- [Search API](SearchAPI.md), the supported way to query the index through Dataverse
- [Postgres](Postgres.md)
