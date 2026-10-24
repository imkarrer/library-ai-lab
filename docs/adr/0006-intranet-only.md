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
