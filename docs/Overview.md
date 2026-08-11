# Metadata Harvesting &amp; APIs - Overview

## Introduction

The logical choice for Harvesting one of our Datastations would be to use the [OAI-PMH](OAI-PMH.md) protocol, because it was designed for that purpose. 
However, if you need all the publicly available metadata of the datasets, the [metadata export API](ExportAPI.md) is a better fit. The `dataverse_json` format contains the most metadata, but is has no schema and is tied to the internal structure, this potentially can have breaking changes over version updates. 

While the Dataverse OAI does advocate it supports the `dataverse_json` format, this wil only produce the landing pages and not the actual JSON, because it is an XML based response. 

There are mainly two use cases:
1. You want everything on your own system and will do your filtering there. 
2. You only need a specific part of the metadata and possibly only of a (filtered) collection of datasets. 


## How to get everything

Use [OAI-PMH](OAI-PMH.md) to get the identifiers or landing pages, it should be possible to retrieve the metadata for each dataset in a next step using the [Export API](ExportAPI.md). 
So a two step process: 
1. Get the identifiers or landing pages of the datasets. 
2. retrieve the metadata of each dataset using these identifiers


## How to get a selection

If the collection you want is already specified by an OAI set, you could use that to retrieve the identifiers and possible also the metadata you want. The metadata is then restricted by what OAI supports. 

The [Search API](SearchAPI.md) would be a good way to try first, because it allows to filter on the datasets and also (to some extend) specify the metadata you want. 


## Get into the system; if all fails and you have access

TODO [Solr](Solr.md) or [Postgres](Postgres.md)...


## Links to the other docs

  - [OAI-PMH](docs/OAI-PMH.md)
  - [Export API](docs/ExportAPI.md)
  - [Search API](docs/SearchAPI.md)
  - [Solr](docs/Solr.md)
  - [Postgres](docs/Postgres.md)

