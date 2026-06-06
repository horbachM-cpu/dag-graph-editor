# Contributing

## Local Setup

```bash
git clone https://github.com/horbachM-cpu/dag-graph-editor.git
cd dag-graph-editor
pip install -r requirements.txt
```

Start the application with:

```bash
python dag_graph_editor.py
```

## Tests

This repository currently includes a small automated test suite for the data model and JSON examples.

Run it with:

```bash
python -m unittest discover -s tests -v
```

If you change graph serialization, project-management logic, or example files, update or extend the tests in `tests/`.

## Pull Requests

- keep changes focused and easy to review
- update documentation when behavior or setup changes
- add or adjust tests when you change model behavior
- include a short summary of what changed and how it was checked

## Issues

When reporting a bug, include:

- the operating system
- Python version
- steps to reproduce the problem
- the expected result and the actual result
