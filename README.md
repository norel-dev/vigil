# Vigil

Vigil is a simple and modular data platform designed to abstractly accomodate any query engine and blob store.

The main goal is to have a single platform for viewing tabular and blob data, with easy tools
to quickly search and manipulate the data using external tools.


## Running
When developing/testing locally, you can run the `docker-compose.yaml` file.
It will run all services and bootstrap some tables to start working with.
The console is served at http://localhost:8080 (set `FRONTEND_PORT` to change it); sign in with the
bootstrap administrator's key, `BOOTSTRAP_API_KEY` (default `dpk_local_docker_compose_development_key`).
