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

## Other tools

You can also browse the data with [MongoDB Compass](https://www.mongodb.com/products/tools/compass) at `mongodb://localhost:27017`, or with `mongosh` inside the container: `docker exec -it mongodb mongosh json_inspect`.

