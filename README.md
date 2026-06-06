# DAG Graph Editor

![Python](https://img.shields.io/badge/Python-3-blue.svg)
![PySide6](https://img.shields.io/badge/PySide6-6.5%2B-green.svg)
![NetworkX](https://img.shields.io/badge/NetworkX-3.0%2B-orange.svg)
![License](https://img.shields.io/badge/License-MIT-yellow.svg)

A powerful, modern desktop editor for directed acyclic graphs (DAGs), built with Python and PySide6.

It combines visual graph editing with JSON persistence, PNG export, automatic layout, and an optional project-management mode for dependency graphs and critical-path calculations. The editor is suitable for dependency-heavy planning workflows such as quest structures, task hierarchies, and project schedules.

![DAG Graph Editor Screenshot](screenshots/main_interface.png)

## Highlights

- Visual canvas for creating, moving, deleting, and re-parenting nodes
- Acyclic validation for hierarchy changes when enabled
- Undo and redo for edit operations
- Node shapes: `circle`, `rect`, `rounded-rect`, `diamond`, `hexagon`, `triangle`, and `projektnode`
- Per-node custom data stored as JSON
- JSON save/load for complete graph documents
- PNG export with transparent background
- Automatic layout via `networkx`
- Minimap, docked panels, context menus, and built-in help
- Optional project-management mode with `FS`, `SS`, `FF`, and `SF` dependencies, lag values, CPM fields, summary nodes, and critical-path highlighting

## Installation

Requirements:

- Python 3
- `PySide6`
- `networkx`

```bash
git clone https://github.com/horbachM-cpu/dag-graph-editor.git
cd dag-graph-editor
pip install -r requirements.txt
```

## Run

```bash
python dag_graph_editor.py
```

The application opens as a desktop window and starts with a small sample graph.

## Usage

### General Editing

- Create, move, and delete nodes on the canvas
- Select a node to edit label, shape, color, text, and custom JSON data in the side panels
- Use the node context menu or the toolbar for common edit actions
- Use `Re-Parent Mode` to assign a different parent while preserving DAG constraints
- Use the toolbar for undo, redo, auto-layout, zoom, save/load, export, and fit-to-view

### Files and Export

- `Save Graph` writes the current document to JSON
- `Load Graph` reads a saved JSON document
- `Export PNG` exports the current scene to a PNG file

### Project-Management Mode

- `PM Mode On/Off` enables PM-specific rendering and calculations
- New nodes created in PM mode use the `projektnode` shape
- `Link Activities (PM)` adds typed dependencies with lag values
- `Calculate Critical Path` updates CPM values and highlights critical activities
- Parent nodes can act as summary nodes based on their children

Example files are available in [`examples/sample_graph.json`](examples/sample_graph.json) and [`examples/project_management_demo.json`](examples/project_management_demo.json).

## Development

Run the minimal test suite with:

```bash
python -m unittest discover -s tests -v
```

## JSON Format

Saved documents are JSON objects with:

- document metadata
- graph settings
- node labels, shapes, colors, layout positions, and custom data
- optional project-management data and dependency definitions

## Repository Layout

- [`dag_graph_editor.py`](dag_graph_editor.py): application entry point
- [`dag_graph_editor/main.py`](dag_graph_editor/main.py): main window, toolbar actions, file operations
- [`dag_graph_editor/model.py`](dag_graph_editor/model.py): graph document model, JSON serialization, PM/CPM logic
- [`dag_graph_editor/views.py`](dag_graph_editor/views.py): graphics view, minimap, PNG export
- [`dag_graph_editor/items.py`](dag_graph_editor/items.py): node and edge rendering
- [`dag_graph_editor/panels.py`](dag_graph_editor/panels.py): dock widgets and help window
- [`dag_graph_editor/commands.py`](dag_graph_editor/commands.py): undo/redo commands
- [`examples/`](examples): example graph documents
- [`screenshots/`](screenshots): repository screenshots

## License

[MIT License](LICENSE)
