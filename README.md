# DAG Graph Editor

![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)
![PySide6](https://img.shields.io/badge/PySide6-6.5+-green.svg)
![License](https://img.shields.io/badge/License-MIT-yellow.svg)
![AI-Assisted](https://img.shields.io/badge/AI--Assisted-GPT--5%20%2B%20Claude%20Opus%204.5-purple.svg)

A powerful, visual **Directed Acyclic Graph (DAG)** editor built with Python and PySide6. Originally designed for game design and quest planning, it serves as a modern, minimalist alternative to legacy UML tools.

![DAG Graph Editor Screenshot](screenshots/main_interface.png)

## ✨ Features

### Graph Structure
- **DAG Enforcement**: Single parent per node, unlimited children
- **Re-Parenting**: Drag-and-drop node hierarchy restructuring
- **Undo/Redo**: Full history with configurable depth
- **Cycle Detection**: Automatic validation to maintain DAG properties

### Node Customization
- **Multiple Shapes**: Circle, Rectangle, Rounded-Rect, Diamond, Hexagon, Triangle, Project Node
- **Color Inheritance**: Parent-child color gradients with override capability
- **Custom Data**: JSON-based arbitrary data storage per node
- **Rich Text**: Description field for detailed node documentation

### Project Management Mode
- **Critical Path Method (CPM)**: Full implementation with:
  - ES/EF (Earliest Start/End)
  - LS/LF (Latest Start/End)
  - TF/FF (Total/Free Float)
- **Dependency Types**: FS, SS, FF, SF with lag support
- **Critical Path Highlighting**: Visual emphasis on critical activities
- **WBS Roll-up**: Automatic summary calculation for parent nodes

### User Interface
- **Interactive Canvas**: Pan, zoom, and drag nodes freely
- **Minimap**: Overview navigation for large graphs
- **Context Menus**: Right-click actions for quick editing
- **Dockable Panels**: Info panel and custom data editor

### Import/Export
- **JSON Format**: Full graph serialization including layout and settings
- **PNG Export**: Transparent background image export

## 🚀 Installation

```bash
# Clone the repository
git clone https://github.com/horbachM-cpu/dag-graph-editor.git
cd dag-graph-editor

# Install dependencies
pip install -r requirements.txt

# Run the application
python dag_graph_editor.py
```

## 📦 Requirements

- Python 3.10+
- PySide6 >= 6.5.0
- NetworkX >= 3.0 (for auto-layout)

## 🎮 Usage

### Basic Operations
1. **Add Node**: Click "New Node" in the toolbar
2. **Edit Node**: Right-click on a node → "Edit..."
3. **Delete Node**: Select node → "Delete Node" 
4. **Re-Parent**: Click "Re-Parent Mode" → Select child → Select new parent

### Project Management Mode
1. Enable PM mode via toolbar toggle
2. Create nodes (automatically become project nodes)
3. Link activities: "Link Activities (PM)" → Select source → Select target → Choose type/lag
4. Calculate critical path: "Calculate Critical Path"

### Navigation
- **Zoom**: Mouse wheel or +/- buttons
- **Pan**: Click and drag on empty canvas
- **Fit View**: "Fit to View" button

## 📁 Project Structure

```
dag-graph-editor/
├── dag_graph_editor/
│   ├── __init__.py
│   ├── main.py           # Application entry point
│   ├── model.py          # Data model and graph logic
│   ├── views.py          # GraphView and scene handling
│   ├── items.py          # NodeItem and EdgeItem graphics
│   ├── panels.py         # InfoPanel and dialogs
│   ├── commands.py       # Undo/Redo command classes
│   └── constants.py      # Shared constants
├── examples/
│   ├── sample_graph.json
│   └── project_management_demo.json
├── screenshots/
├── requirements.txt
├── LICENSE
└── README.md
```

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🤖 Built with AI

This project showcases modern AI-assisted development:

- **Initial Design & Architecture**: Created with [GPT-5 Thinking](https://openai.com) 🧠
- **Code Review & Refactoring**: Polished with [Claude Opus 4.5](https://anthropic.com) in [Antigravity IDE](https://github.com/anthropics/antigravity) ✨

> *"AI programming is not just cool — it's the future of software development."*

## 🙏 Acknowledgments

- Built with [PySide6](https://wiki.qt.io/Qt_for_Python) (Qt for Python)
- Graph algorithms powered by [NetworkX](https://networkx.org/)
