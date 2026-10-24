# Our own thin UI instead of Open WebUI or LibreChat

Card sign-in, the Live view, and the Flag queue fight the account-and-roles model of
off-the-shelf chat front ends, and Open WebUI forbids rebranding above 50 users a month. We
build a small server-rendered UI in the same Python process as the API.

## Considered Options

- **Open WebUI**: strongest RAG and RBAC out of the box, but its auth model assumes accounts and
  its license limits white-labelling.
- **LibreChat**: MIT, but brings MongoDB and Meilisearch to every Install.
