"""
Panel components for DAG Graph Editor.

Contains InfoPanel and HelpWindow dialog.
"""

from __future__ import annotations

from typing import Optional, TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QColorDialog, QComboBox, QDialog, QFormLayout,
    QHBoxLayout, QLabel, QLineEdit, QPushButton, QSpinBox,
    QTextEdit, QVBoxLayout, QWidget
)
from PySide6.QtGui import QColor

from .constants import SHAPES
from .model import GraphModel, PMData

if TYPE_CHECKING:
    from .views import GraphView


class InfoPanel(QWidget):
    """Panel for viewing and editing node properties."""
    
    def __init__(self, model: GraphModel, view: 'GraphView'):
        super().__init__()
        self.model = model
        self.view = view
        self.current_id: Optional[str] = None
        self._editing = False
        self._pm_is_summary = False

        layout = QVBoxLayout(self)
        self.form = QFormLayout()

        self.id_lbl = QLabel("-")
        self.label_edit = QLineEdit()
        self.shape_combo = QComboBox()
        self.shape_combo.addItems(SHAPES)
        self.inherit_chk = QCheckBox("Inherit Color")
        self.color_btn = QPushButton("Choose Color...")
        self.color_lbl = QLabel("#-")

        # Description field
        self.text_edit = QTextEdit()
        self.text_edit.setPlaceholderText("Description / Notes...")
        self.text_edit.setFixedHeight(100)

        # Buttons
        self.btn_edit = QPushButton("Edit")
        self.btn_save = QPushButton("Save")
        self.btn_cancel = QPushButton("Cancel")
        self.btn_save.hide()
        self.btn_cancel.hide()

        self.form.addRow("ID:", self.id_lbl)
        self.form.addRow("Label:", self.label_edit)
        self.form.addRow("Shape:", self.shape_combo)
        self.form.addRow("", self.inherit_chk)
        hl = QHBoxLayout()
        hl.addWidget(self.color_btn)
        hl.addWidget(self.color_lbl)
        w = QWidget()
        w.setLayout(hl)
        self.form.addRow("Color:", w)
        self.form.addRow("Text:", self.text_edit)

        # PM fields (projektnode)
        self.pm_number = QLineEdit()
        self.pm_name = QLineEdit()
        self.pm_duration = QSpinBox()
        self.pm_duration.setRange(0, 100000)
        self.pm_duration.setValue(1)
        self.pm_faz = QLineEdit()
        self.pm_faz.setReadOnly(True)
        self.pm_fez = QLineEdit()
        self.pm_fez.setReadOnly(True)
        self.pm_saz = QLineEdit()
        self.pm_saz.setReadOnly(True)
        self.pm_sez = QLineEdit()
        self.pm_sez.setReadOnly(True)
        self.pm_gp = QLineEdit()
        self.pm_gp.setReadOnly(True)
        self.pm_fp = QLineEdit()
        self.pm_fp.setReadOnly(True)

        self.form.addRow("Activity Number:", self.pm_number)
        self.form.addRow("Activity Name:", self.pm_name)
        self.form.addRow("Duration (days):", self.pm_duration)
        self.form.addRow("ES/EF:", self.pm_faz)
        self.form.addRow("LS/LF:", self.pm_saz)
        self.form.addRow("TF/FF:", self.pm_gp)
        layout.addLayout(self.form)

        bl = QHBoxLayout()
        bl.addWidget(self.btn_edit)
        bl.addWidget(self.btn_save)
        bl.addWidget(self.btn_cancel)
        layout.addLayout(bl)
        layout.addStretch(1)

        self._set_editing(False)

        # Signals
        self.btn_edit.clicked.connect(self._on_edit)
        self.btn_save.clicked.connect(self._on_save)
        self.btn_cancel.clicked.connect(self._on_cancel)
        self.color_btn.clicked.connect(self._choose_color)
        self.shape_combo.currentTextChanged.connect(self._shape_changed)
        self.inherit_chk.toggled.connect(self._inherit_toggled)

    def _set_editing(self, on: bool):
        self._editing = on
        for w in (self.label_edit, self.shape_combo, self.inherit_chk, 
                  self.color_btn, self.text_edit, self.pm_number, 
                  self.pm_name, self.pm_duration):
            w.setEnabled(on)
        # If summary, duration stays read-only
        if on and self._pm_is_summary:
            try:
                self.pm_duration.setEnabled(False)
            except Exception:
                pass
        self.btn_edit.setVisible(not on)
        self.btn_save.setVisible(on)
        self.btn_cancel.setVisible(on)

    def show_node(self, node_id: Optional[str]):
        """Display a node's properties."""
        self.current_id = node_id
        if not node_id or node_id not in self.model.doc.nodes:
            self._set_editing(False)
            self.id_lbl.setText("-")
            self.label_edit.setText("")
            self.shape_combo.setCurrentText("circle")
            self.inherit_chk.setChecked(True)
            self.color_lbl.setText("#-")
            self.text_edit.setPlainText("")
            return
            
        n = self.model.doc.nodes[node_id]
        self.id_lbl.setText(n.id)
        self.label_edit.setText(n.label)
        self.shape_combo.setCurrentText(n.attrs.shape)
        self.inherit_chk.setChecked(n.attrs.inheritColor)
        self.color_lbl.setText(n.attrs.color or "#-")
        self.text_edit.setPlainText(n.attrs.data.get("text", ""))
        
        # PM fields
        if n.pm is None and n.attrs.shape == "projektnode":
            n.pm = PMData(name=n.label, duration=1)
        # summary detection
        has_children = len(self.view.window.model.children_of(n.id)) > 0
        self._pm_is_summary = bool(n.pm and (n.pm.isSummary or has_children))
        
        if n.pm:
            self.pm_number.setText(n.pm.number or "")
            self.pm_name.setText(n.pm.name or n.label)
            self.pm_duration.setValue(int(n.pm.duration))
            self.pm_faz.setText(f"{n.pm.FAZ} | EF {n.pm.FEZ}")
            self.pm_saz.setText(f"{n.pm.SAZ} | LF {n.pm.SEZ}")
            self.pm_gp.setText(f"TF {n.pm.GP} / FF {n.pm.FP}")
            try:
                self.pm_duration.setEnabled(not self._pm_is_summary)
            except Exception:
                pass
        else:
            for w in (self.pm_number, self.pm_name, self.pm_duration, 
                      self.pm_faz, self.pm_saz, self.pm_gp):
                if isinstance(w, QSpinBox):
                    w.setValue(1)
                else:
                    w.setText("")
        self._set_editing(False)

    def edit_node(self, node_id: str):
        """Enter edit mode for a node."""
        self.show_node(node_id)
        self._set_editing(True)

    def _on_edit(self):
        if self.current_id:
            self._set_editing(True)

    def _on_cancel(self):
        self.show_node(self.current_id)

    def _on_save(self):
        if not self.current_id:
            return
        from .commands import EditNodeCommand
        attrs = {
            "label": self.label_edit.text(),
            "shape": self.shape_combo.currentText(),
            "inherit": self.inherit_chk.isChecked(),
            "color": self.color_lbl.text() if self.color_lbl.text() and self.color_lbl.text() != "#-" else None,
        }
        # Merge text into data
        cur = dict(self.model.doc.nodes[self.current_id].attrs.data)
        cur["text"] = self.text_edit.toPlainText()
        attrs["data"] = cur
        # PM payload
        pm_payload = {
            "number": self.pm_number.text().strip() or None,
            "name": self.pm_name.text().strip() or self.label_edit.text().strip(),
            "duration": int(self.pm_duration.value()),
        }
        attrs["pm"] = pm_payload
        cmd = EditNodeCommand(self.model, self.current_id, attrs, self.view)
        self.view.undo_stack.push(cmd)
        self._set_editing(False)

    def _choose_color(self):
        c = QColorDialog.getColor(QColor(120, 170, 255), self, "Choose Color")
        if c.isValid():
            self.color_lbl.setText(c.name())

    def _shape_changed(self, _):
        pass  # handled on save

    def _inherit_toggled(self, _):
        pass  # handled on save


class HelpWindow(QDialog):
    """Help dialog with usage instructions."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Help")
        self.resize(700, 600)
        lay = QVBoxLayout(self)
        txt = QTextEdit(self)
        txt.setReadOnly(True)
        txt.setPlainText(self._help_text())
        btn_close = QPushButton("Close", self)
        btn_close.clicked.connect(self.accept)
        lay.addWidget(txt)
        lay.addWidget(btn_close)

    def _help_text(self) -> str:
        return (
            "DAG Graph Editor - Help\n\n"
            "Overview\n"
            "- Toolbar: New Node, Re-Parent, Undo/Redo, Auto-Layout, Save/Load, PNG Export.\n"
            "- Info Panel (right): Label/Shape/Color/Text and PM fields for project nodes.\n"
            "- Minimap (bottom): Overview, can be toggled on/off.\n\n"
            "Project Management (PM)\n"
            "- PM Mode on/off: Toggles PM rendering and calculations.\n"
            "- Project Node: Header (Number-Name), Row1 ES|d|EF, Row2 LS|TF/FF|LF.\n"
            "- Link Activities (PM): Toolbar -> Source -> Target -> Choose Type/Lag; Edge label e.g. FS+2.\n"
            "- Calculate Critical Path: Updates ES/EF/LS/LF/TF/FF and highlighting.\n"
            "- Auto-Recalc: On changes (Duration, PM-Link, Re-Parent, Delete).\n\n"
            "Abbreviations\n"
            "- ES: Earliest Start\n"
            "- EF: Earliest Finish (= ES + d)\n"
            "- LS: Latest Start\n"
            "- LF: Latest Finish (= LS + d)\n"
            "- d: Duration (days)\n"
            "- TF: Total Float (= LS - ES)\n"
            "- FF: Free Float (depends on link type):\n"
            "      FS: min(ES_j) - (EF_i + Lag)\n"
            "      SS: min(ES_j) - (ES_i + Lag)\n"
            "      FF: min(EF_j) - (EF_i + Lag)\n"
            "      SF: min(EF_j) - (ES_i + Lag)\n\n"
            "PM Dependency Types\n"
            "- FS (Finish-Start)\n"
            "- SS (Start-Start)\n"
            "- FF (Finish-Finish)\n"
            "- SF (Start-Finish)\n"
            "- Lag: Time offset in days (negative = Lead allowed).\n\n"
            "Summary/WBS\n"
            "- Parent summarizes children: ES=min(ES children), EF=max(EF children), d=EF-ES.\n"
            "- Summary fields are computed; no own PM links needed.\n\n"
            "Usage Tips\n"
            "- New Node: In PM mode automatically creates Project Node.\n"
            "- Re-Parent: Click child, then new parent.\n"
            "- Right-click Node: Context menu (Edit/Delete).\n"
            "- Right-click PM Edge: Edit (Type/Lag) or Delete.\n\n"
            "Validation\n"
            "- Cycles are blocked when creating PM links.\n"
            "- Negative lags allowed; unit: days (no calendar).\n"
        )
