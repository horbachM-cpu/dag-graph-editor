"""
Undo/Redo command classes for DAG Graph Editor.

All modifications to the graph should go through these commands
to enable proper undo/redo functionality.
"""

from __future__ import annotations

import json
from typing import Dict, Optional, Tuple, TYPE_CHECKING

from PySide6.QtCore import QPointF
from PySide6.QtGui import QUndoCommand
from PySide6.QtWidgets import QMessageBox

from .model import GraphModel, NodeData

if TYPE_CHECKING:
    from .views import GraphView


class MoveNodesCommand(QUndoCommand):
    """Command for moving nodes to new positions."""
    
    def __init__(self, model: GraphModel, old: Dict[str, QPointF], 
                 new: Dict[str, QPointF], view: 'GraphView'):
        super().__init__("Move Nodes")
        self.model = model
        self.old = {k: (v.x(), v.y()) for k, v in old.items()}
        self.new = {k: (v.x(), v.y()) if isinstance(v, QPointF) else (v[0], v[1]) for k, v in new.items()}
        self.view = view

    def redo(self):
        self.model.move_nodes(self.new)
        self.view.sync_items_from_model()

    def undo(self):
        self.model.move_nodes(self.old)
        self.view.sync_items_from_model()


class AddNodeCommand(QUndoCommand):
    """Command for adding a new node."""
    
    def __init__(self, model: GraphModel, parent_id: Optional[str], 
                 pos: QPointF, view: 'GraphView'):
        super().__init__("Add Node")
        self.model = model
        self.parent_id = parent_id
        self.pos = pos
        self.view = view
        self.node_id: Optional[str] = None

    def redo(self):
        if not self.node_id:
            n = self.model.add_node("Node", self.parent_id, self.pos)
            self.node_id = n.id
        else:
            # Recreate node (if undo deleted it)
            node = NodeData(id=self.node_id, label="Node", parentId=self.parent_id)
            node.layout.x = self.pos.x()
            node.layout.y = self.pos.y()
            self.model.doc.nodes[self.node_id] = node
            self.model.changed.emit()
        self.view.sync_items_from_model()

    def undo(self):
        if self.node_id and self.node_id in self.model.doc.nodes:
            del self.model.doc.nodes[self.node_id]
            self.model.changed.emit()
        self.view.sync_items_from_model()


class DeleteNodeCommand(QUndoCommand):
    """Command for deleting a node."""
    
    def __init__(self, model: GraphModel, node_id: str, view: 'GraphView'):
        super().__init__("Delete Node")
        self.model = model
        self.node_id = node_id
        self.view = view
        self.snapshot = None

    def _take_snapshot(self):
        self.snapshot = json.dumps(self.model.to_json())

    def _restore_snapshot(self):
        if self.snapshot:
            self.model.from_json(json.loads(self.snapshot))

    def redo(self):
        self._take_snapshot()
        self.model.delete_node(self.node_id)
        if self.model.doc.settings.pm.enabled:
            self.model.compute_cpm()
        self.view.sync_items_from_model()

    def undo(self):
        self._restore_snapshot()
        if self.model.doc.settings.pm.enabled:
            self.model.compute_cpm()
        self.view.sync_items_from_model()


class ReparentCommand(QUndoCommand):
    """Command for reparenting a node."""
    
    def __init__(self, model: GraphModel, child_id: str, 
                 new_parent_id: Optional[str], view: 'GraphView'):
        super().__init__("Reparent")
        self.model = model
        self.child_id = child_id
        self.new_parent_id = new_parent_id
        self.view = view
        self.snapshot_before = None
        self.snapshot_after = None

    def redo(self):
        if self.snapshot_after:
            self.model.from_json(json.loads(self.snapshot_after))
        else:
            self.snapshot_before = json.dumps(self.model.to_json())
            self.model.reparent_variant_a(self.child_id, self.new_parent_id)
            self.snapshot_after = json.dumps(self.model.to_json())
        if self.model.doc.settings.pm.enabled:
            try:
                self.model.compute_cpm()
            except Exception:
                pass
        self.view.sync_items_from_model()

    def undo(self):
        if self.snapshot_before:
            self.model.from_json(json.loads(self.snapshot_before))
            if self.model.doc.settings.pm.enabled:
                try:
                    self.model.compute_cpm()
                except Exception:
                    pass
            self.view.sync_items_from_model()


class EditNodeCommand(QUndoCommand):
    """Command for editing node attributes."""
    
    def __init__(self, model: GraphModel, node_id: str, new_attrs: dict, view: 'GraphView'):
        super().__init__("Edit Node")
        self.model = model
        self.node_id = node_id
        self.new_attrs = new_attrs
        self.view = view
        self.old_snapshot = None

    def redo(self):
        if self.old_snapshot is None:
            self.old_snapshot = json.dumps(self.model.to_json())
        self.model.set_node_attrs(self.node_id, **self.new_attrs)
        if self.model.doc.settings.pm.enabled:
            self.model.compute_cpm()
        self.view.sync_items_from_model()

    def undo(self):
        if self.old_snapshot:
            self.model.from_json(json.loads(self.old_snapshot))
            if self.model.doc.settings.pm.enabled:
                self.model.compute_cpm()
            self.view.sync_items_from_model()


class AutoLayoutCommand(QUndoCommand):
    """Command for auto-layout using networkx."""
    
    def __init__(self, model: GraphModel, view: 'GraphView'):
        super().__init__("Auto-Layout")
        self.model = model
        self.view = view
        self.before = None
        self.after = None

    def _compute_layout(self) -> Dict[str, Tuple[float, float]]:
        try:
            import networkx as nx
        except ImportError:
            QMessageBox.warning(self.view.window, "Auto-Layout", 
                              "networkx not installed. Please run: pip install networkx")
            return self._fallback_tree_layout()
            
        G = nx.DiGraph()
        for nid, n in self.model.doc.nodes.items():
            G.add_node(nid)
            if n.parentId:
                G.add_edge(n.parentId, nid)
                
        if len(G.nodes) == 0:
            return {}
            
        try:
            pos = nx.spring_layout(G, seed=42, k=None, iterations=50)
        except Exception:
            QMessageBox.warning(self.view.window, "Auto-Layout", 
                              "spring_layout requires NumPy. Using fallback layout.")
            return self._fallback_tree_layout()
            
        # Normalize & scale positions
        xs = [p[0] for p in pos.values()]
        ys = [p[1] for p in pos.values()]
        minx, maxx = min(xs), max(xs)
        miny, maxy = min(ys), max(ys)
        w = max(1e-5, maxx - minx)
        h = max(1e-5, maxy - miny)
        scale = 600
        return {nid: (scale * (x - minx) / w, scale * (y - miny) / h) for nid, (x, y) in pos.items()}

    def _fallback_tree_layout(self) -> Dict[str, Tuple[float, float]]:
        """Simple layered layout using parentId relationships."""
        nodes = list(self.model.doc.nodes.keys())
        if not nodes:
            return {}
            
        # Identify roots
        roots = [nid for nid in nodes 
                 if not self.model.doc.nodes[nid].parentId 
                 or self.model.doc.nodes[nid].parentId not in self.model.doc.nodes]
        if not roots:
            roots = [nodes[0]]
            
        depths: Dict[str, int] = {}
        for r in roots:
            if r in depths:
                continue
            depths[r] = 0
            q = [r]
            qi = 0
            while qi < len(q):
                u = q[qi]
                qi += 1
                for v in self.model.children_of(u):
                    if v in depths:
                        continue
                    depths[v] = depths[u] + 1
                    q.append(v)
                    
        # Assign remaining nodes
        for nid in nodes:
            depths.setdefault(nid, 0)
            
        # Group by depth
        layers: Dict[int, list] = {}
        for nid, d in depths.items():
            layers.setdefault(d, []).append(nid)
            
        # Positioning
        gap_x, gap_y = 180.0, 140.0
        out: Dict[str, Tuple[float, float]] = {}
        for d in sorted(layers.keys()):
            layer = sorted(layers[d])
            n = len(layer)
            for i, nid in enumerate(layer):
                x = (i - (n - 1) / 2.0) * gap_x
                y = d * gap_y
                out[nid] = (x, y)
        return out

    def redo(self):
        if self.after:
            self.model.move_nodes(self.after)
            self.view.sync_items_from_model()
            return
        self.before = {nid: (n.layout.x, n.layout.y) for nid, n in self.model.doc.nodes.items()}
        newpos = self._compute_layout()
        if not newpos:
            return
        self.model.move_nodes(newpos)
        self.after = newpos
        self.view.sync_items_from_model()

    def undo(self):
        if self.before:
            self.model.move_nodes(self.before)
            self.view.sync_items_from_model()


class AddPMDepCommand(QUndoCommand):
    """Command for adding a PM dependency."""
    
    def __init__(self, model: GraphModel, pred_id: str, succ_id: str, 
                 dep_type: str, lag: int, view: 'GraphView'):
        super().__init__("Add PM Link")
        self.model = model
        self.pred_id = pred_id
        self.succ_id = succ_id
        self.dep_type = dep_type
        self.lag = int(lag)
        self.view = view
        self.added = False

    def redo(self):
        ok = self.model.add_pm_dep(self.pred_id, self.succ_id, self.dep_type, self.lag)
        if not ok:
            try:
                QMessageBox.warning(self.view.window, "PM-Link", 
                                  "Link not created (cycle or duplicate).")
            except Exception:
                pass
            return
        self.added = True
        if self.model.doc.settings.pm.enabled:
            self.model.compute_cpm()
        self.view.sync_items_from_model()

    def undo(self):
        self.model.remove_pm_dep(self.succ_id, self.pred_id, self.dep_type, self.lag)
        if self.model.doc.settings.pm.enabled:
            self.model.compute_cpm()
        self.view.sync_items_from_model()
