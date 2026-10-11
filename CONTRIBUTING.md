# Contributing

- Keep `bank` zero-dependency (stdlib only).
- New ingest source → add a pattern to `DEFAULT_SOURCES` / `AGENT_SOURCES` in `src/skills_bank/cli.py` and a line in README.
- Run `bank validate` and `python -m py_compile src/skills_bank/*.py` before a PR.
- Don't commit ingested content (`skills/ext-*`, `_remote/`, `_assets/`) — `.gitignore` already blocks it.
