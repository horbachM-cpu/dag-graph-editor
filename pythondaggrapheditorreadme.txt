# Python DAG Graph Editor (PySide6) – MVP

Ein leichtgewichtiges, anpassbares Tool zum Erstellen und Bearbeiten von **gerichteten Bäumen/DAGs**.  
Entstanden als Hilfstool für Game-Design / Quest-Planung – gedacht als moderne, minimalistische Alternative zu alten UML-Tools wie ArgoUML.  

---

## ✨ Features

- **Graph-Struktur**
  - Directed Acyclic Graph (ein Parent, beliebig viele Children).
  - Re-Parenting per Button (Variante A: Child + seine bisherigen Children werden direkt beim neuen Parent angehängt).
  - Undo/Redo (History-Tiefe konfigurierbar).

- **Nodes**
  - Shapes: `circle`, `rect`, `rounded-rect`, `diamond`, `hexagon`, `triangle`.
  - Farben: Vererbung vom Parent (mit Abstufung), Override möglich.
  - Extra Textfeld („Beschreibung“) im Info-Panel.
  - Frei editierbare JSON-Daten im separaten „Custom Info“-Dock.

- **UI**
  - Klick → Info-Panel (Bearbeiten via Button).
  - Rechtsklick-Menü: Bearbeiten, Löschen, Re-Parent starten.
  - Drag & Drop → nur Layout (Shift = verschiebt Subtree mit Children).
  - Zoom & Pan (Buttons + Mausrad).
  - Mini-Map (abschaltbar).
  - Toolbar-Buttons für alle Aktionen (keine Shortcuts).
  - PNG-Export mit transparentem Hintergrund.

- **Dateien**
  - Speichern/Laden im JSON-Format (inkl. Settings, Layout, Daten).
  - Importiert/Exportiert 1:1 die gesamte Szene.

---

## 🚀 Installation

```bash
git clone https://github.com/<DEIN-USERNAME>/dag-graph-editor.git
cd dag-graph-editor
pip install PySide6 networkx
