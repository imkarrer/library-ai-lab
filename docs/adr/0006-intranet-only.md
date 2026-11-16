# An Install reaches only resources on the school intranet

The assistant connects only to services on the school's own network: its model endpoint, its
Catalog, nothing on the internet. No cloud model provider is configured anywhere, so there is
no accidental fallback path, and the model endpoint is any OpenAI-compatible server the school
runs. This is what turns "what happens to our students' data?" into a question a firewall rule
answers.

## Exception: building the demo Catalog

One setup step may reach the internet: downloading Library of Congress MARC open-access
records to build the demo's SQLite Catalog. It runs once, before the demo, on the
presenter's machine, and is a separate command, never part of the running assistant. Once
the Catalog is built, the demo runs with networking off. The step is for demos only and ships
disabled in an Install's config; a school builds its Catalog from its own systems.

## Exception: fetching the models

One setup step may also reach the internet: fetching the model weights, once, before an
Install goes into use. Each file comes from the Ollama registry into the Nix store, where
its path is fixed by the digest pinned in `models/pins`, so a changed or truncated file
fails the fetch. The first `flox activate` does this for any file not yet in the store;
`scripts/fetch_models.sh` does it ahead of time, with progress, and can take files already
pulled into `~/.ollama`. Either way the download is Nix's, never the running assistant's or
the model servers'.

After setup nothing is missing, so nothing is fetched: the environment holds the files
against garbage collection, and Ollama serves them from the read-only store with
`OLLAMA_NO_CLOUD` set. A new model or version is a new pin and another setup fetch, never
an automatic pull. A school whose Install must never fetch even a missing file installs
`models/`'s default build instead, which can only refuse.
