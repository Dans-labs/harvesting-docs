# Harvesting Dataverse Metadata

Notes and example code for harvesting metadata from [Dataverse](https://dataverse.org/) repositories, such as the DANS data stations.

Start with the [Overview](Overview.md), which explains which approach fits which use case:

- [OAI-PMH](OAI-PMH.md): harvest identifiers and records using the standard protocol
- [Export API](ExportAPI.md): get the complete metadata of a dataset, including `dataverse_json`
- [Search API](SearchAPI.md): get a filtered selection of datasets
- [Solr](Solr.md) and [Postgres](Postgres.md): query the system directly, if you have access

The command-line tools and Python clients are in the [GitHub repository](https://github.com/Dans-labs/harvesting-docs).
