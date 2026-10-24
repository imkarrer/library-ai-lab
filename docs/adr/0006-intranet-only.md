# An Install reaches only resources on the school intranet

The assistant connects only to services on the school's own network: its model endpoint, its
Catalog, nothing on the internet. No cloud model provider is configured anywhere, so there is
no accidental fallback path, and the model endpoint is any OpenAI-compatible server the school
runs. This is what turns "what happens to our students' data?" into a question a firewall rule
answers.
