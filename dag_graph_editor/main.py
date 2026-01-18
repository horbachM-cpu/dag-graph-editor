"""
Main window and application entry point for DAG Graph Editor.
"""

from __future__ import annotations

import json
import logging
import sys
from typing import Optional, Tuple

from PySide6.QtCore import Qt, QTimer, QPointF, QEvent
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QApplication, QComboBox, QDialog, QDialogButtonBox, QDockWidget,
    QFileDialog, QFormLayout, QMainWindow, QMessageBox, QPlainTextEdit,
    QPushButton, QSpinBox, QToolBar, QHBoxLayout, QVBoxLayout, QWidget
)

from .model import GraphModel
from .views import GraphView, MiniMap
from .panels import InfoPanel, HelpWindow
from .items import NodeItem
from .commands import (
    AddNodeCommand, DeleteNodeCommand, ReparentCommand, 
    AutoLayoutCommand, AddPMDepCommand
)

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("dag_editor")


class MainWindow(QMainWindow):
    """Main application window."""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("DAG Graph Editor")
        self.resize(1200, 800)

        self.model = GraphModel()
        self.view = GraphView(self.model, self)
        self.setCentralWidget(self.view)

        # Minimap
        self.minimap = MiniMap(self.view)
        self.minimap_dock = QDockWidget("Minimap")
        self.minimap_dock.setWidget(self.minimap)
        self.addDockWidget(Qt.BottomDockWidgetArea, self.minimap_dock)

        # Info Panel
        self.info_panel = InfoPanel(self.model, self.view)
        self.info_dock = QDockWidget("Info")
        self.info_dock.setWidget(self.info_panel)
        self.addDockWidget(Qt.RightDockWidgetArea, self.info_dock)

        # Custom Info Dock (JSON editor)
        ciw = QWidget()
        cil = QVBoxLayout(ciw)
        self.custom_info_edit = QPlainTextEdit()
        self.custom_info_edit.setPlaceholderText("Edit node 'data' as JSON here...")
        cil.addWidget(self.custom_info_edit)
        ci_buttons = QHBoxLayout()
        self.custom_info_apply_btn = QPushButton("Apply")
        self.custom_info_reload_btn = QPushButton("Reload")
        ci_buttons.addWidget(self.custom_info_apply_btn)
        ci_buttons.addWidget(self.custom_info_reload_btn)
        cil.addLayout(ci_buttons)
        self.custom_info_dock = QDockWidget("Custom Data")
        self.custom_info_dock.setWidget(ciw)
        self.addDockWidget(Qt.RightDockWidgetArea, self.custom_info_dock)
        self.custom_info_apply_btn.clicked.connect(self.custom_info_apply)
        self.custom_info_reload_btn.clicked.connect(self.custom_info_reload)

        # Menu bar: Help
        mb = self.menuBar()
        m_help = mb.addMenu("Help")
        self.act_show_help = QAction("Show Help", self)
        self.act_show_help.triggered.connect(self.show_help)
        m_help.addAction(self.act_show_help)

        # Toolbar
        self.toolbar = QToolBar("Tools")
        self.addToolBar(Qt.TopToolBarArea, self.toolbar)
        self._build_toolbar()

        # Status
        self.statusBar().showMessage("Ready")

        # Selection polling timer
        self._sel_timer = QTimer(self)
        self._sel_timer.timeout.connect(self._update_selected_in_panel)
        self._sel_timer.start(300)

        # Reparent state
        self._reparent_mode = False
        self._reparent_child: Optional[str] = None
        # PM link state
        self._pm_link_mode = False
        self._pm_link_src: Optional[str] = None

        # Apply settings to UI
        self._apply_settings_to_ui()

        # Seed sample content
        self._seed_sample()

        # Keep minimap viewport overlay updated
        try:
            self.view.horizontalScrollBar().valueChanged.connect(lambda _: self.minimap.viewport().update())
            self.view.verticalScrollBar().valueChanged.connect(lambda _: self.minimap.viewport().update())
        except Exception:
            pass

        # Help window holder
        self._help_window: Optional[HelpWindow] = None

    def _build_toolbar(self):
        """Build the main toolbar."""
        def btn(text: str, slot):
            a = QAction(text, self)
            a.triggered.connect(slot)
            self.toolbar.addAction(a)
            return a

        self.act_new_node = btn("New Node", self.add_node)
        self.act_delete_node = btn("Delete Node", self.delete_selected)
        self.toolbar.addSeparator()
        self.act_reparent = btn("Re-Parent Mode", self.begin_reparent_mode)
        self.toolbar.addSeparator()
        self.act_undo = btn("Undo", self.view.undo_stack.undo)
        self.act_redo = btn("Redo", self.view.undo_stack.redo)
        self.toolbar.addSeparator()
        self.act_auto_layout = btn("Auto-Layout", self.auto_layout)
        self.toolbar.addSeparator()
        self.act_zoom_in = btn("Zoom +", self.view.zoom_in)
        self.act_zoom_out = btn("Zoom -", self.view.zoom_out)
        self.act_fit = btn("Fit to View", self.view.fit_to_view)
        self.toolbar.addSeparator()
        self.act_save = btn("Save Graph", self.save_graph)
        self.act_load = btn("Load Graph", self.load_graph)
        self.act_export = btn("Export PNG", self.export_png)
        self.toolbar.addSeparator()
        # PM mode toggles
        self.act_pm_toggle = btn("PM Mode On/Off", self.toggle_pm_mode)
        self.act_pm_buffers = btn("Show PM Buffers", self.toggle_pm_buffers)
        self.act_pm_link = btn("Link Activities (PM)", self.begin_pm_link_mode)
        self.act_pm_cpm = btn("Calculate Critical Path", self.action_compute_cpm)
        self.toolbar.addSeparator()
        self.act_toggle_minimap = btn("Minimap On/Off", self.toggle_minimap)
        self.act_toggle_acyclic = btn("Acyclic Check On/Off", self.toggle_acyclic)
        self.act_toggle_inherit = btn("Color Inheritance On/Off", self.toggle_inheritance)
        self.toolbar.addSeparator()
        self.act_toggle_arrows = btn("Arrows On/Off", self.toggle_arrows)
        self.toolbar.addSeparator()
        self.act_toggle_info = btn("Info Panel On/Off", self.toggle_info)
        self.toolbar.addSeparator()
        self.act_grad_light = btn("Set Gradient Default", self.set_default_gradient)

    def _update_selected_in_panel(self):
        """Update info panel based on selection."""
        if getattr(self.info_panel, "_editing", False):
            return
        sel = [it for it in self.view.scene_.selectedItems() if isinstance(it, NodeItem)]
        if sel:
            nid = sel[0].node_id
            self.info_panel.show_node(nid)
            if not self.custom_info_edit.hasFocus():
                self._update_custom_info_for_node(nid)
        else:
            self.info_panel.show_node(None)
            if not self.custom_info_edit.hasFocus():
                self._update_custom_info_for_node(None)

    def _apply_settings_to_ui(self):
        """Apply model settings to UI state."""
        self.minimap_dock.setVisible(self.model.doc.settings.ui.showMinimap)
        self._update_minimap_fit()
        self.view.scene_.update()

    def toggle_pm_mode(self):
        """Toggle Project Management mode."""
        s = self.model.doc.settings
        s.pm.enabled = not s.pm.enabled
        self.statusBar().showMessage(f"PM Mode: {'on' if s.pm.enabled else 'off'}", 2000)
        if s.pm.enabled:
            try:
                self.model.compute_cpm()
            except Exception:
                pass
        self.view._rebuild_edges()
        self.view.scene_.update()

    def toggle_pm_buffers(self):
        """Toggle PM buffer display."""
        s = self.model.doc.settings
        s.pm.showBuffers = not s.pm.showBuffers
        self.view.scene_.update()

    def _update_minimap_fit(self):
        if self.minimap.isVisible():
            self.minimap.fit_to_scene()

    def show_help(self):
        """Show help dialog."""
        if self._help_window is None:
            self._help_window = HelpWindow(self)
        self._help_window.show()
        self._help_window.raise_()
        self._help_window.activateWindow()

    def toggle_minimap(self):
        """Toggle minimap visibility."""
        s = self.model.doc.settings
        s.ui.showMinimap = not s.ui.showMinimap
        self._apply_settings_to_ui()

    def toggle_info(self):
        """Toggle info panel visibility."""
        self.info_dock.setVisible(not self.info_dock.isVisible())

    def toggle_acyclic(self):
        """Toggle acyclic validation."""
        s = self.model.doc.settings
        s.validation.enforceAcyclic = not s.validation.enforceAcyclic
        self.statusBar().showMessage(f"Acyclic check: {'on' if s.validation.enforceAcyclic else 'off'}", 2000)

    def toggle_inheritance(self):
        """Toggle color inheritance."""
        s = self.model.doc.settings
        s.styling.enableColorInheritance = not s.styling.enableColorInheritance
        self.view.scene_.update()

    def toggle_arrows(self):
        """Toggle edge arrows."""
        s = self.model.doc.settings
        s.edges.decorationsEnabled = not s.edges.decorationsEnabled
        self.view._rebuild_edges()
        self.view.scene_.update()

    def set_default_gradient(self):
        """Reset gradient to default values."""
        s = self.model.doc.settings.styling
        s.inheritanceLuminanceStep = -8
        s.inheritanceSaturationStep = -3
        self.view.scene_.update()

    def item_for_node(self, node_id: str) -> Optional[NodeItem]:
        """Get the NodeItem for a node ID."""
        return self.view.item_for_node(node_id)

    def add_node(self):
        """Add a new node at the center of the view."""
        pos = self.view.mapToScene(self.view.viewport().rect().center())
        parent_id = None
        sel = [it for it in self.view.scene_.selectedItems() if isinstance(it, NodeItem)]
        if sel:
            parent_id = sel[0].node_id
        cmd = AddNodeCommand(self.model, parent_id, pos, self.view)
        self.view.undo_stack.push(cmd)

    def delete_selected(self):
        """Delete the selected node."""
        sel = [it for it in self.view.scene_.selectedItems() if isinstance(it, NodeItem)]
        if not sel:
            QMessageBox.information(self, "Delete", "Please select a node first.")
            return
        self.delete_node(sel[0].node_id)

    def delete_node(self, node_id: str):
        """Delete a node with confirmation."""
        ret = QMessageBox.question(
            self,
            "Delete",
            "Really delete this node?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if ret != QMessageBox.Yes:
            return
        cmd = DeleteNodeCommand(self.model, node_id, self.view)
        self.view.undo_stack.push(cmd)

    def begin_reparent_mode(self):
        """Enter reparent mode."""
        self._reparent_mode = True
        self._reparent_child = None
        self.statusBar().showMessage("Re-Parent: First click child, then click new parent.")
        log.info("reparent_mode begin")
        self.view.viewport().installEventFilter(self)

    def end_reparent_mode(self):
        """Exit reparent mode."""
        if self._reparent_mode:
            self._reparent_mode = False
            self._reparent_child = None
            self.statusBar().showMessage("Re-Parent completed", 2000)
            log.info("reparent_mode end")
            self.view.viewport().removeEventFilter(self)

    def begin_pm_link_mode(self):
        """Enter PM link creation mode."""
        self._pm_link_mode = True
        self._pm_link_src = None
        self.statusBar().showMessage("PM-Link: First click source, then target.")
        try:
            self.view.viewport().installEventFilter(self)
        except Exception:
            pass

    def end_pm_link_mode(self):
        """Exit PM link creation mode."""
        if self._pm_link_mode:
            self._pm_link_mode = False
            self._pm_link_src = None
            self.statusBar().showMessage("PM-Link completed", 2000)
            try:
                self.view.viewport().removeEventFilter(self)
            except Exception:
                pass

    def _prompt_pm_link(self) -> Optional[Tuple[str, int]]:
        """Prompt user for PM link type and lag."""
        dlg = QDialog(self)
        dlg.setWindowTitle("PM Dependency")
        lay = QFormLayout(dlg)
        type_combo = QComboBox(dlg)
        type_combo.addItems(["FS", "SS", "FF", "SF"])
        lag_spin = QSpinBox(dlg)
        lag_spin.setRange(-100000, 100000)
        lag_spin.setValue(0)
        lay.addRow("Type:", type_combo)
        lay.addRow("Lag (days):", lag_spin)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, parent=dlg)
        lay.addWidget(bb)
        bb.accepted.connect(dlg.accept)
        bb.rejected.connect(dlg.reject)
        if dlg.exec() == QDialog.Accepted:
            return type_combo.currentText(), int(lag_spin.value())
        return None

    def action_compute_cpm(self):
        """Compute critical path method."""
        ok, err = self.model.compute_cpm()
        if not ok and err:
            QMessageBox.warning(self, "CPM", err)
        self.view.sync_items_from_model()

    def eventFilter(self, obj, event):
        """Handle reparent mode clicks."""
        if obj is self.view.viewport() and self._reparent_mode:
            if event.type() == QEvent.MouseButtonPress and event.button() == Qt.LeftButton:
                try:
                    sp = event.position().toPoint()
                except Exception:
                    sp = event.pos()
                scene_p = self.view.mapToScene(sp)
                items = self.view.scene_.items(scene_p)
                node_item = next((it for it in items if isinstance(it, NodeItem)), None)
                if node_item:
                    if not self._reparent_child:
                        self._reparent_child = node_item.node_id
                        self.statusBar().showMessage("Re-Parent: Now click the new parent...")
                        log.info("reparent pick child=%s", self._reparent_child)
                    else:
                        new_parent = node_item.node_id
                        child = self._reparent_child
                        if self.model.doc.settings.validation.enforceAcyclic and not self.model.is_acyclic_if_reparent(child, new_parent):
                            QMessageBox.warning(self, "Re-Parent", "Would create cycle - aborted.")
                            self.end_reparent_mode()
                            return True
                        cmd = ReparentCommand(self.model, child, new_parent, self.view)
                        self.view.undo_stack.push(cmd)
                        log.info("reparent commit child=%s new_parent=%s", child, new_parent)
                        self.end_reparent_mode()
                        return True
                else:
                    # Click on empty -> treat as root parent
                    if self._reparent_child:
                        cmd = ReparentCommand(self.model, self._reparent_child, None, self.view)
                        self.view.undo_stack.push(cmd)
                        log.info("reparent commit child=%s new_parent=None", self._reparent_child)
                        self.end_reparent_mode()
                        return True
        return super().eventFilter(obj, event)

    def auto_layout(self):
        """Perform auto-layout."""
        cmd = AutoLayoutCommand(self.model, self.view)
        self.view.undo_stack.push(cmd)
        self._update_minimap_fit()

    def export_png(self):
        """Export graph to PNG."""
        path, _ = QFileDialog.getSaveFileName(self, "Export PNG", "graph.png", "PNG (*.png)")
        if not path:
            return
        self.view.export_png(path)

    def save_graph(self):
        """Save graph to JSON file."""
        path, _ = QFileDialog.getSaveFileName(self, "Save Graph", "graph.json", "JSON (*.json)")
        if not path:
            return
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.model.to_json(), f, ensure_ascii=False, indent=2)
        self.statusBar().showMessage("Saved.", 2000)

    def load_graph(self):
        """Load graph from JSON file."""
        path, _ = QFileDialog.getOpenFileName(self, "Load Graph", "", "JSON (*.json)")
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.model.from_json(data)
            if self.model.doc.settings.pm.enabled:
                try:
                    self.model.compute_cpm()
                except Exception:
                    pass
            self.view.sync_items_from_model()
            self._apply_settings_to_ui()
            self._update_minimap_fit()
            self.statusBar().showMessage("Loaded.", 2000)
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def _update_custom_info_for_node(self, node_id: Optional[str]):
        if not node_id or node_id not in self.model.doc.nodes:
            self.custom_info_edit.setPlainText("")
            return
        n = self.model.doc.nodes[node_id]
        try:
            self.custom_info_edit.setPlainText(json.dumps(n.attrs.data, ensure_ascii=False, indent=2))
        except Exception:
            self.custom_info_edit.setPlainText(str(n.attrs.data))

    def custom_info_apply(self):
        """Apply custom JSON data to current node."""
        from .commands import EditNodeCommand
        node_id = self.info_panel.current_id
        if not node_id or node_id not in self.model.doc.nodes:
            return
        try:
            new_data = json.loads(self.custom_info_edit.toPlainText() or "{}")
        except Exception as e:
            QMessageBox.critical(self, "JSON Error", f"Invalid JSON:\n{e}")
            return
        cmd = EditNodeCommand(self.model, node_id, {"data": new_data}, self.view)
        self.view.undo_stack.push(cmd)

    def custom_info_reload(self):
        """Reload custom JSON data from current node."""
        self._update_custom_info_for_node(self.info_panel.current_id)

    def _seed_sample(self):
        """Create sample nodes."""
        a = self.model.add_node("Root", None, QPointF(0, 0))
        b = self.model.add_node("Child A", a.id, QPointF(0, 120))
        c = self.model.add_node("Child B", b.id, QPointF(0, 240))
        self.view.sync_items_from_model()
        self.view.fit_to_view()


def main():
    """Application entry point."""
    app = QApplication(sys.argv)
    w = MainWindow()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
