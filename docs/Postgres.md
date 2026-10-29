# Postgres

Dataverse stores all its data in a [PostgreSQL](https://www.postgresql.org/) database. If you have direct access to it, you can in principle retrieve all information, including non-public content.

In practice the dataset metadata is hard to extract, because metadata fields are stored in a complex, generic structure that needs many table joins. Other information is much simpler to obtain, especially when everything you need is in one or two tables (for example identifiers, dates and ownership of objects).

> Use a read-only database user when querying. Never modify the Dataverse database directly, and keep in mind that unpublished and restricted content is visible here.

## Schema

The database has almost 150 tables and many relations. The Dataverse guides provide SchemaSpy diagrams of the schema, for example for 6.2: <https://guides.dataverse.org/en/6.2/schemaspy/index.html>. You can also generate one for your own version with [SchemaSpy](https://schemaspy.org/).

Table names are singular and the schema can change between Dataverse versions.

### Objects (dataverses, datasets and files)

- `dvobject`: base table for all objects, with identifiers, dates and the owner (parent) of each object
- `dataverse`: collections
- `dataset`: datasets
- `datafile`: files

### Users (depositors, authors)

- `authenticateduser`
- `authenticateduserlookup`
- `builtinuser`

## Common commands

Start a `psql` session, assuming the user is `dvnuser` and the database is `dvndb`:

```bash
psql -U dvnuser -W dvndb
```

List the databases, and the tables in the current database:

```psql
\l
\dt
```

Show the schema of a specific table, `dvobject` in this example:

```psql
\d dvobject
```

Show some table content, limited to a few rows:

```psql
SELECT * FROM dvobject LIMIT 10;
```

Count the objects per type:

```psql
SELECT dtype, count(*) FROM dvobject GROUP BY dtype;
```

Export a query result to CSV from within `psql`:

```psql
\copy (SELECT id, dtype, authority, identifier FROM dvobject LIMIT 100) TO 'objects.csv' CSV HEADER
```

## Useful queries from the Dataverse community

The Dataverse community maintains a [document with PostgreSQL queries](https://docs.google.com/document/d/1-Y_iUduSxdDNeK1yiGUxe7t-Md7Fy965jp4o4m1XEoE/edit#heading=h.avuoo5kf0mdt).

## Related

- [Overview](Overview.md)
- [Solr](Solr.md), simpler for quick, flattened metadata queries
