# Exploring JSON Metadata

To explore the structure of harvested JSON metadata (e.g. the Dataverse JSON exports in `exports/`), the files can be loaded into MongoDB and queried there. The script is `src/exploring/json-metadata/json-to-mongo.py`.

## Setup

Install the optional `pymongo` dependency group and start MongoDB:

```bash
uv sync --group explore
cd src/exploring/json-metadata
docker compose up -d
```

The `docker-compose.yml` is optional: any MongoDB on `localhost:27017` without authentication will do, e.g. `docker run -d -p 127.0.0.1:27017:27017 mongo:8`. The compose file just runs `mongo:8` bound to localhost, with a named volume (`mongodb_data`) so data survives restarts.

!!! note
    The script connects to `mongodb://localhost:27017` without credentials. Do not enable `MONGO_INITDB_ROOT_USERNAME`/`PASSWORD` in the compose file unless you also add the credentials to `MONGO_URI` in the script.

## Usage

Run from the repository root (use `uv run --group explore` or activate `.venv` first, otherwise a different `python` without `pymongo` may be picked up):

```bash
# Load all .json / .jsonl files found recursively in a directory
uv run --group explore python src/exploring/json-metadata/json-to-mongo.py load exports

# Summarize top-level fields: name, BSON type, count
uv run --group explore python src/exploring/json-metadata/json-to-mongo.py inspect

# Query with a Mongo filter (prints up to 5 matches)
uv run --group explore python src/exploring/json-metadata/json-to-mongo.py find '{"identifier": "FK2/HJVOXL"}'
```

Documents go into database `json_inspect`, collection `docs`. Each document gets a `_source_file` field with its path relative to the loaded directory. Files that fail to parse and documents over the 16 MB limit are skipped and reported.

`load` does not clear the collection, so loading twice creates duplicates. To start over:

```bash
docker compose down -v   # removes the data volume
```

Stop the database (keeping data) with `docker compose down`.

## Notebook: authors and contributors

`src/exploring/json-metadata/authors_contributors.ipynb` queries the loaded Dataverse JSON with a MongoDB aggregation pipeline and builds a pandas DataFrame with one row per author or contributor (name, affiliation, identifier such as ORCID, source file). It then shows a few summaries, such as contributors by type, top affiliations and most frequent people.

To run it:

1. Start MongoDB and load the data as described above (the notebook reads `json_inspect.docs` and does not load anything itself).
2. Install the dependencies (`pymongo`, `pandas`, `ipykernel`) with `uv sync --group explore`.
3. Open the notebook in VS Code and select the `.venv` kernel (**Select Kernel** > **Python Environments** > `.venv`), then **Run All**. Or start Jupyter from the terminal:

    ```bash
    uv run --group explore --with jupyterlab jupyter lab src/exploring/json-metadata/authors_contributors.ipynb
    ```

The first code cell prints the number of documents in the collection; if it prints `0`, the data has not been loaded yet. The last cell writes `people.csv` to the `data/` directory in the repository root (git-ignored); it is optional and can be skipped.

The pipeline only looks at `datasetVersion.metadataBlocks.citation.fields`, so it expects Dataverse JSON exports (`dataverse_json`), not other formats.

## Notebook: co-worker network

`src/exploring/json-metadata/coworker_network.ipynb` builds a network of people who worked on the same dataset, using the `people.csv` produced by the authors and contributors notebook. It does not need MongoDB.

Two people are linked when they appear on the same dataset (the same `_source_file`); the link weight is the number of datasets they share. Two graphs are built:

- **Co-author graph**: both are authors of the dataset.
- **Collaboration graph**: both appear on the dataset as author or contributor.

The notebook prints network statistics (connected components, most connected people, strongest pairs), draws static plots with communities highlighted, can zoom in on a single person (`draw_ego("name fragment")`) and shows an interactive graph.

To run it:

1. Run `authors_contributors.ipynb` first, so that `data/people.csv` exists.
2. Install the dependencies (`networkx`, `matplotlib`, `pyvis`, `pandas`, `ipykernel`) with `uv sync --group explore`.
3. Open the notebook in VS Code, select the `.venv` kernel and **Run All**, or start JupyterLab as shown above with `coworker_network.ipynb` as the argument.

Output is written to `data/` (git-ignored):

| File | Content |
| --- | --- |
| `coworker_edges.csv` | One row per pair of people with the number of shared datasets |
| `coworkers.gexf` | The collaboration graph, for opening in [Gephi](https://gephi.org/) |
| `coworkers.html` | Interactive graph (also shown inline); loads its JavaScript from a CDN, so it needs internet access |

Notes:

- People are identified by their name (lowercased), so spelling variants of the same person are counted as different people.
- Datasets with more than `MAX_PEOPLE_PER_DATASET` (50) people are skipped, because the number of pairs grows quadratically.
- The static plots only show the strongest part of the network (`top_n`, `min_weight`); adjust these parameters in the `draw` calls to see more or less.

## Other tools

You can also browse the data with [MongoDB Compass](https://www.mongodb.com/products/tools/compass) at `mongodb://localhost:27017`, or with `mongosh` inside the container: `docker exec -it mongodb mongosh json_inspect`.

