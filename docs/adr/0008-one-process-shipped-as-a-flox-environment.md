# One Python process, shipped as a flox environment

The assistant is a single Python (FastAPI) process with SQLite storage, and an Install is a
flox environment whose services start it. A librarian should keep one thing running, not a
cluster, and flox is the point of the showcase. It is not a homelab tenant: homelab's tenant
list is closed, and llm-box serves only as a model endpoint during development. A macOS
installer and configurator is the last thing built, not the first.
