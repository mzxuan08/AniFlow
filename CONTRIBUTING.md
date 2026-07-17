# Contributing

Issues and pull requests are welcome. Before changing behavior, please open an issue describing the use case and expected result.

## Development setup

```bash
python -m pip install -e ".[dev]"
python -m pytest
python -m ruff check .
```

Keep changes focused and include a regression test for bug fixes or new matching, storage, downloader, and Web behavior. Do not add generated data, downloaded media, tracker credentials, server addresses, or private RSS links to commits.

## Pull requests

- Explain what changed and why.
- List the commands used to verify the change.
- Note any database, deployment, or compatibility impact.
- Keep unrelated formatting and refactoring out of the same pull request.
