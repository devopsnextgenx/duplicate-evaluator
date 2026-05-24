# Duplicate Evaluator

Local LLM-powered media duplicate detection and management tool.

## Setup

```bash
pip install -e ".[dev]"
duplicate-evaluator
```

## Configuration

Edit `config.yml` to set your media path and LLM backend.

## Docker

Build and run the app in Docker with a target media folder override:

```bash
TARGET_PATH=/host/path/to/media docker compose up --build
```

The compose file mounts the host folder into the container at `/data/media` and sets `DUPEVAL_TARGET_PATH` accordingly. You can also override the server host or port by setting `DUPEVAL_HOST` and `DUPEVAL_PORT` in the environment.
