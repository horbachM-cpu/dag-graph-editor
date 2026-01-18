#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Python DAG Graph Editor (PySide6) – MVP (patched)

Fixes & Additions in this build:
- **EventFilter**: uses QEvent.MouseButtonPress (Qt6) with robust position handling → Re-Parent, Delete, Edit work.
- **Delete dialog**: explicit buttons (Yes/No) to avoid enum/overload issues.
- **Info-Panel**: editing no longer gets overridden by selection timer; toolbar toggle "Info an/aus".
- **Text field**: extra multiline text in Info-Panel; saved in attrs.data["text"].
- **Custom Info Dock**: JSON editor for arbitrary node attrs.data with Apply/Reload.
- **DAG check**: corrected acyclicity test (new parent must **not** be descendant of child).
- **Logging**: basic logging for key actions (add/delete/reparent/move/edit/auto-layout).

Run:
  pip install PySide6 networkx
  python graph_tool.py
"""

from __future__ import annotations
import json
import math
import sys
import uuid
import logging
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Tuple, Set

from PySide6.QtCore import (
    Qt,
    QRectF,
    QPointF,
    QSize,
    QTimer,
    QObject,
    Signal,
    QEvent,  # for eventFilter
)
from PySide6.QtGui import (
    QAction,
    QBrush,
    QColor,
    QFont,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QPolygonF,
    QTransform,
    QUndoCommand,
    QUndoStack,
)
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDialog,
    QDockWidget,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGraphicsItem,
    QGraphicsPathItem,
    QGraphicsScene,
    QGraphicsView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QStyle,
    QToolBar,
    QVBoxLayout,
    QWidget,
    QTextEdit,
    QPlainTextEdit,
)

# --- Logging setup ---
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("dag_editor")

try:
    import networkx as nx
except Exception:  # noqa
    nx = None  # Auto-layout will show a warning

# -----------------------------
# Data Model
# -----------------------------

SHAPES = ["circle", "rect", "rounded-rect", "diamond", "hexagon", "triangle", "projektnode"]


def gen_id(prefix: str = "n") -> str:
    return f"{prefix}{uuid.uuid4().hex[:8]}"


@dataclass
class NodeAttrs:
    color: Optional[str] = None  # hex string like "#RRGGBB"
    inheritColor: bool = True
    shape: str = "circle"
    data: Dict[str, str] = field(default_factory=dict)


@dataclass
class NodeLayout:
    x: float = 0.0
    y: float = 0.0
    locked: bool = False


@dataclass
class NodeData:
    id: str
    label: str = "Node"
    parentId: Optional[str] = None
    attrs: NodeAttrs = field(default_factory=NodeAttrs)
    layout: NodeLayout = field(default_factory=NodeLayout)
    # Project Management fields
    pm: Optional[PMData] = None
    pmDeps: List[PMDep] = field(default_factory=list)


@dataclass
class SettingsValidation:
    enforceAcyclic: bool = True


@dataclass
class SettingsHistory:
    maxDepth: int = 100


@dataclass
class SettingsUI:
    showMinimap: bool = True


@dataclass
class SettingsStyling:
    enableColorInheritance: bool = True
    inheritanceLuminanceStep: int = -8  # percent points per depth level
    inheritanceSaturationStep: int = -3


@dataclass
class SettingsEdges:
    decorationsEnabled: bool = True  # arrows/labels optional (default on)


@dataclass
class SettingsPM:
    enabled: bool = False            # PM-Modus global an/aus
    showBuffers: bool = True         # Puffer in UI anzeigen


@dataclass
class GraphSettings:
    validation: SettingsValidation = field(default_factory=SettingsValidation)
    history: SettingsHistory = field(default_factory=SettingsHistory)
    ui: SettingsUI = field(default_factory=SettingsUI)
    styling: SettingsStyling = field(default_factory=SettingsStyling)
    edges: SettingsEdges = field(default_factory=SettingsEdges)
    pm: SettingsPM = field(default_factory=SettingsPM)


@dataclass
class PMDep:
    predId: str
    type: str = "FS"                 # FS, SS, FF, SF
    lag: int = 0                     # Tage, negativ = Lead erlaubt


@dataclass
class PMData:
    number: Optional[str] = None
    name: Optional[str] = None
    duration: int = 1                # d (Tage, ganzzahlig)
    FAZ: int = 0
    FEZ: int = 0
    SAZ: int = 0
    SEZ: int = 0
    GP: int = 0                      # Gesamtpuffer
    FP: int = 0                      # Freier Puffer (MVP: FS-basiert)
    isCritical: bool = False
    isSummary: bool = False          # WBS-Parent: Roll-up, d nicht editierbar


@dataclass
class GraphMeta:
    title: str = "Mein Graph"
    createdAt: Optional[str] = None


@dataclass
class GraphDocument:
    version: str = "1.0"
    meta: GraphMeta = field(default_factory=GraphMeta)
    nodes: Dict[str, NodeData] = field(default_factory=dict)
    settings: GraphSettings = field(default_factory=GraphSettings)


class GraphModel(QObject):
    changed = Signal()
    node_selected = Signal(str)

    def __init__(self):
        super().__init__()
        self.doc = GraphDocument()

    # ---------- Query helpers ----------
    def children_of(self, node_id: str) -> List[str]:
        return [n.id for n in self.doc.nodes.values() if n.parentId == node_id]

    def ancestors_of(self, node_id: str) -> Set[str]:
        res: Set[str] = set()
        cur = self.doc.nodes.get(node_id)
        while cur and cur.parentId:
            res.add(cur.parentId)
            cur = self.doc.nodes.get(cur.parentId)
        return res

    def descendants_of(self, node_id: str) -> Set[str]:
        res: Set[str] = set()
        stack = [node_id]
        while stack:
            nid = stack.pop()
            for c in self.children_of(nid):
                if c not in res:
                    res.add(c)
                    stack.append(c)
        res.discard(node_id)
        return res

    def is_acyclic_if_reparent(self, child_id: str, new_parent_id: Optional[str]) -> bool:
        if new_parent_id is None:
            return True
        if child_id == new_parent_id:
            return False
        # korrekt: neuer Parent darf KEIN Nachfahre des Childs sein
        return new_parent_id not in self.descendants_of(child_id)

    # ---------- Mutations ----------
    def add_node(self, label: str = "Node", parent_id: Optional[str] = None, pos: QPointF = QPointF(0, 0)) -> NodeData:
        new_id = gen_id()
        n = NodeData(id=new_id, label=label, parentId=parent_id)
        n.layout.x = pos.x()
        n.layout.y = pos.y()
        # Default shape: if PM mode is enabled, create a projektnode by default
        if self.doc.settings.pm.enabled:
            n.attrs.shape = "projektnode"
            # Initialize minimal PM payload
            n.pm = PMData(name=label, number=None, duration=1)
        # Fallback guard for invalid shapes
        if n.attrs.shape not in SHAPES:
            n.attrs.shape = "circle"
        self.doc.nodes[new_id] = n
        log.info("add_node id=%s parent=%s pos=(%.1f,%.1f)", new_id, parent_id, n.layout.x, n.layout.y)
        self.changed.emit()
        return n

    def delete_node(self, node_id: str):
        node = self.doc.nodes.get(node_id)
        if not node:
            return
        parent_id = node.parentId
        # reattach children to parent (or become roots if no parent)
        for cid in self.children_of(node_id):
            child = self.doc.nodes[cid]
            child.parentId = parent_id
        # remove PM dependencies that reference the deleted node as predecessor
        for n in self.doc.nodes.values():
            if getattr(n, 'pmDeps', None):
                n.pmDeps = [d for d in n.pmDeps if d.predId != node_id]
        del self.doc.nodes[node_id]
        log.info("delete_node id=%s (children -> %s)", node_id, parent_id)
        self.changed.emit()

    def reparent_variant_a(self, child_id: str, new_parent_id: Optional[str]):
        if child_id == new_parent_id:
            log.warning("reparent aborted: child==parent")
            return
        if self.doc.settings.validation.enforceAcyclic and not self.is_acyclic_if_reparent(child_id, new_parent_id):
            log.warning("reparent aborted: would create cycle child=%s new_parent=%s", child_id, new_parent_id)
            return
        child = self.doc.nodes.get(child_id)
        if not child:
            return
        # Grab current children of child
        current_children = self.children_of(child_id)
        # set child's new parent
        child.parentId = new_parent_id
        # move all previous children to new_parent as well
        for cid in current_children:
            self.doc.nodes[cid].parentId = new_parent_id
        log.info("reparent variant A: %s -> parent %s; moved %d children", child_id, new_parent_id, len(current_children))
        self.changed.emit()

    def set_node_attrs(self, node_id: str, *, label: Optional[str] = None, color: Optional[str] = None,
                        inherit: Optional[bool] = None, shape: Optional[str] = None, data: Optional[Dict[str, str]] = None,
                        pm: Optional[dict] = None):
        n = self.doc.nodes.get(node_id)
        if not n:
            return
        if label is not None:
            n.label = label
        if color is not None:
            n.attrs.color = color
        if inherit is not None:
            n.attrs.inheritColor = inherit
        if shape is not None and shape in SHAPES:
            n.attrs.shape = shape
            # Ensure PM data exists when switching to projektnode
            if n.attrs.shape == "projektnode" and n.pm is None:
                n.pm = PMData(name=n.label, number=None, duration=1)
        if data is not None:
            n.attrs.data = data
        if pm is not None:
            if n.pm is None:
                n.pm = PMData()
            # apply only known keys
            if "number" in pm:
                n.pm.number = str(pm.get("number") if pm.get("number") is not None else "")
            if "name" in pm:
                n.pm.name = str(pm.get("name") if pm.get("name") is not None else "")
            if "duration" in pm:
                try:
                    n.pm.duration = int(pm.get("duration", n.pm.duration))
                except Exception:
                    pass
            # computed fields may be set by a CPM engine later; keep update paths
            for k in ("FAZ","FEZ","SAZ","SEZ","GP","FP"):
                if k in pm:
                    try:
                        setattr(n.pm, k, int(pm[k]))
                    except Exception:
                        pass
            if "isCritical" in pm:
                n.pm.isCritical = bool(pm.get("isCritical"))
            if "isSummary" in pm:
                n.pm.isSummary = bool(pm.get("isSummary"))
        log.info("edit_node id=%s label=%s shape=%s inherit=%s color=%s data_keys=%s",
                 node_id, label, shape, inherit, color, list((data or {}).keys()))
        self.changed.emit()

    def move_nodes(self, positions: Dict[str, Tuple[float, float]]):
        for nid, (x, y) in positions.items():
            n = self.doc.nodes.get(nid)
            if n:
                n.layout.x = x
                n.layout.y = y
        log.info("move_nodes %d", len(positions))
        self.changed.emit()

    # ---------- PM Dependencies ----------
    def add_pm_dep(self, pred_id: str, succ_id: str, dep_type: str = "FS", lag: int = 0) -> bool:
        if pred_id not in self.doc.nodes or succ_id not in self.doc.nodes:
            return False
        # Prevent self-loop
        if pred_id == succ_id:
            return False
        succ = self.doc.nodes[succ_id]
        # Ensure PM containers exist on successor
        if succ.pm is None:
            succ.pm = PMData(name=succ.label, duration=1)
        dep_type = str(dep_type).upper()
        if dep_type not in ("FS", "SS", "FF", "SF"):
            dep_type = "FS"
        try:
            lag = int(lag)
        except Exception:
            lag = 0
        # Avoid duplicates (same pred/type/lag)
        for d in succ.pmDeps:
            if d.predId == pred_id and d.type == dep_type and d.lag == lag:
                return False
        # Cycle check: adding pred->succ must not create a cycle
        if self._pm_creates_cycle(pred_id, succ_id):
            return False
        succ.pmDeps.append(PMDep(predId=pred_id, type=dep_type, lag=lag))
        self.changed.emit()
        return True

    def remove_pm_dep(self, succ_id: str, pred_id: str, dep_type: Optional[str] = None, lag: Optional[int] = None):
        if succ_id not in self.doc.nodes:
            return
        succ = self.doc.nodes[succ_id]
        before = len(succ.pmDeps)
        def _match(d: PMDep) -> bool:
            if d.predId != pred_id:
                return False
            if dep_type is not None and str(d.type).upper() != str(dep_type).upper():
                return False
            if lag is not None and d.lag != lag:
                return False
            return True
        succ.pmDeps = [d for d in succ.pmDeps if not _match(d)]
        if len(succ.pmDeps) != before:
            self.changed.emit()

    # ---------- PM cycle detection ----------
    def _pm_creates_cycle(self, pred_id: str, succ_id: str) -> bool:
        # If there is already a path from succ_id back to pred_id through pmDeps, adding pred->succ creates a cycle
        return self._pm_reaches(succ_id, pred_id)

    def _pm_reaches(self, src_id: str, dst_id: str) -> bool:
        seen: Set[str] = set()
        stack: List[str] = [src_id]
        while stack:
            u = stack.pop()
            if u == dst_id:
                return True
            if u in seen:
                continue
            seen.add(u)
            node = self.doc.nodes.get(u)
            if not node:
                continue
            for d in getattr(node, 'pmDeps', []) or []:
                v = d.predId  # edge v -> u in storage; we want u's successors, so iterate reverse
            # To traverse successors from u, we need nodes where u appears as predId
            for nid, n in self.doc.nodes.items():
                for d in getattr(n, 'pmDeps', []) or []:
                    if d.predId == u:
                        stack.append(nid)
        return False

    # ---------- CPM Engine ----------
    def compute_cpm(self) -> Tuple[bool, Optional[str]]:
        # Prepare task set (exclude summaries)
        nodes = self.doc.nodes
        tasks: List[str] = []
        for nid, n in nodes.items():
            if n.attrs.shape == "projektnode" and n.pm is None:
                n.pm = PMData(name=n.label, duration=1)
            has_children = len(self.children_of(nid)) > 0
            if n.pm and not (n.pm.isSummary or has_children):
                tasks.append(nid)

        # Build adjacency with weights w(i->j) for ES constraints
        W: Dict[Tuple[str, str], int] = {}
        succs: Dict[str, List[str]] = {t: [] for t in tasks}
        preds_count: Dict[str, int] = {t: 0 for t in tasks}
        dur: Dict[str, int] = {t: max(0, int(nodes[t].pm.duration if nodes[t].pm else 0)) for t in tasks}

        def weight(dep: PMDep, dj: int, di: int) -> int:
            t = dep.type.upper()
            L = int(dep.lag)
            if t == "FS":
                return di + L
            if t == "SS":
                return L
            if t == "FF":
                return di + L - dj
            if t == "SF":
                return L - dj
            return di + L

        for j in tasks:
            n = nodes[j]
            for d in (n.pmDeps or []):
                i = d.predId
                if i not in tasks:
                    continue
                w = weight(d, dj=dur[j], di=dur[i])
                W[(i, j)] = w
                succs[i].append(j)
                preds_count[j] += 1

        # Topological order (Kahn)
        order: List[str] = []
        q = [t for t in tasks if preds_count.get(t, 0) == 0]
        while q:
            x = q.pop(0)
            order.append(x)
            for y in succs.get(x, []):
                preds_count[y] -= 1
                if preds_count[y] == 0:
                    q.append(y)
        if len(order) != len(tasks):
            # cycle detected
            return False, "Zyklus in PM-Verknüpfungen"

        # Forward pass
        ES: Dict[str, int] = {t: 0 for t in tasks}
        for i in order:
            for j in succs.get(i, []):
                w = W[(i, j)]
                ES[j] = max(ES[j], ES[i] + w)
        EF: Dict[str, int] = {t: ES[t] + dur[t] for t in tasks}
        T = max(EF.values(), default=0)

        # Backward pass
        LS: Dict[str, int] = {t: 10**9 for t in tasks}
        sinks = {t for t in tasks if len(succs.get(t, [])) == 0}
        for s in sinks:
            LS[s] = T - dur[s]
        for i in reversed(order):
            for j in succs.get(i, []):
                LS[i] = min(LS[i], LS[j] - W[(i, j)])
            if LS[i] == 10**9:
                LS[i] = T - dur[i]
        # Update nodes
        for t in tasks:
            pm = nodes[t].pm
            pm.FAZ = int(ES[t])
            pm.FEZ = int(EF[t])
            pm.SAZ = int(LS[t])
            pm.SEZ = int(LS[t] + dur[t])
            pm.GP = int(pm.SAZ - pm.FAZ)
            pm.isCritical = (pm.GP == 0)
        # Free float (generalized for FS/SS/FF/SF with lag)
        for i in tasks:
            cands: List[int] = []
            for j in tasks:
                # find deps where i is predecessor of j
                for d in (nodes[j].pmDeps or []):
                    if d.predId != i:
                        continue
                    t = d.type.upper()
                    L = int(d.lag)
                    ES_i, EF_i = nodes[i].pm.FAZ, nodes[i].pm.FEZ
                    ES_j, EF_j = nodes[j].pm.FAZ, nodes[j].pm.FEZ
                    if t == "FS":
                        cands.append(ES_j - (EF_i + L))
                    elif t == "SS":
                        cands.append(ES_j - (ES_i + L))
                    elif t == "FF":
                        cands.append(EF_j - (EF_i + L))
                    elif t == "SF":
                        cands.append(EF_j - (ES_i + L))
            if cands:
                nodes[i].pm.FP = int(max(0, min(cands)))
            else:
                nodes[i].pm.FP = nodes[i].pm.GP

        # Roll-up summaries
        changed = True
        guard = 0
        while changed and guard < 10:
            changed = False
            guard += 1
            for nid, n in nodes.items():
                ch = self.children_of(nid)
                if not ch:
                    continue
                pm = n.pm if n.pm else PMData(name=n.label, duration=1)
                es_vals = [nodes[c].pm.FAZ for c in ch if nodes.get(c) and nodes[c].pm]
                ef_vals = [nodes[c].pm.FEZ for c in ch if nodes.get(c) and nodes[c].pm]
                if not es_vals or not ef_vals:
                    continue
                es = min(es_vals)
                ef = max(ef_vals)
                if pm.FAZ != es or pm.FEZ != ef or pm.duration != (ef - es) or not pm.isSummary:
                    pm.FAZ = int(es)
                    pm.FEZ = int(ef)
                    pm.SAZ = int(es)
                    pm.SEZ = int(ef)
                    pm.duration = int(max(0, ef - es))
                    pm.GP = 0
                    pm.FP = 0
                    pm.isCritical = False
                    pm.isSummary = True
                    n.pm = pm
                    changed = True

        self.changed.emit()
        return True, None

    # ---------- Colors ----------
    def _qcolor_from_hex(self, hx: Optional[str], default: QColor = QColor(120, 170, 255)) -> QColor:
        if hx:
            c = QColor(hx)
            if c.isValid():
                return c
        return default

    def effective_color(self, node_id: str, _visited: Optional[Set[str]] = None) -> QColor:
        node = self.doc.nodes.get(node_id)
        if not node:
            return QColor(200, 200, 200)
        st = self.doc.settings.styling
        # direct color override
        if node.attrs.color:
            return self._qcolor_from_hex(node.attrs.color)
        # inheritance disabled globally or per-node OR no/invalid parent
        parent_id = node.parentId
        if (not st.enableColorInheritance
                or not node.attrs.inheritColor
                or not parent_id
                or parent_id not in self.doc.nodes
                or not self.doc.settings.validation.enforceAcyclic):
            return QColor(120, 170, 255)
        # guard against cycles during inheritance
        if _visited is None:
            _visited = set()
        if node_id in _visited:
            # cycle detected: fall back to base color to avoid recursion
            return QColor(120, 170, 255)
        _visited.add(node_id)
        # inherit from parent chain
        base = self.effective_color(parent_id, _visited)
        # apply gradient by depth step 1
        h, s, l, a = base.getHsl()
        s = max(0, min(255, int(s + (st.inheritanceSaturationStep / 100.0) * 255)))
        l = max(0, min(255, int(l + (st.inheritanceLuminanceStep / 100.0) * 255)))
        res = QColor()
        res.setHsl(h, s, l, a)
        return res

    # ---------- Serialization ----------
    def to_json(self) -> dict:
        def node_to_dict(n: NodeData) -> dict:
            out = {
                "id": n.id,
                "label": n.label,
                "parentId": n.parentId,
                "attrs": {
                    "color": n.attrs.color,
                    "inheritColor": n.attrs.inheritColor,
                    "shape": n.attrs.shape,
                    "data": n.attrs.data,
                },
                "layout": {"x": n.layout.x, "y": n.layout.y, "locked": n.layout.locked},
            }
            # PM fields (only include if present)
            if n.pm is not None:
                try:
                    out["pm"] = asdict(n.pm)
                except Exception:
                    pass
            if n.pmDeps:
                try:
                    out["pmDeps"] = [asdict(d) for d in n.pmDeps]
                except Exception:
                    pass
            return out

        data = {
            "version": self.doc.version,
            "meta": asdict(self.doc.meta),
            "settings": asdict(self.doc.settings),
            "nodes": [node_to_dict(n) for n in self.doc.nodes.values()],
        }
        return data

    def from_json(self, data: dict):
        try:
            self.doc = GraphDocument()
            self.doc.version = data.get("version", "1.0")
            meta = data.get("meta", {})
            self.doc.meta = GraphMeta(title=meta.get("title", "Mein Graph"), createdAt=meta.get("createdAt"))
            # settings
            s = data.get("settings", {})
            self.doc.settings = GraphSettings(
                validation=SettingsValidation(**s.get("validation", {})),
                history=SettingsHistory(**s.get("history", {})),
                ui=SettingsUI(**s.get("ui", {})),
                styling=SettingsStyling(**s.get("styling", {})),
                # tolerate missing or malformed edges settings
                edges=SettingsEdges(**(s.get("edges", {}) if isinstance(s.get("edges", {}), dict) else {})),
                pm=SettingsPM(**(s.get("pm", {}) if isinstance(s.get("pm", {}), dict) else {})),
            )
            # nodes
            self.doc.nodes.clear()
            for nd in data.get("nodes", []):
                nid = nd.get("id")
                if not nid:
                    continue
                # parentId compatibility: accept parentIds (list) or parentId (str)
                parent_id = nd.get("parentId")
                if parent_id is None:
                    pids = nd.get("parentIds")
                    if isinstance(pids, list) and pids:
                        parent_id = pids[0]
                # attrs (be tolerant to extra keys / wrong types)
                a_raw = nd.get("attrs", {}) or {}
                if not isinstance(a_raw, dict):
                    a_raw = {}
                color = a_raw.get("color")
                inherit = a_raw.get("inheritColor", True)
                shape = a_raw.get("shape", "circle")
                data_field = a_raw.get("data", {})
                if not isinstance(data_field, dict):
                    # try to coerce non-dict types into a dict for safety
                    data_field = {"value": str(data_field)}
                attrs = NodeAttrs(color=color, inheritColor=bool(inherit), shape=shape, data=data_field)
                # layout (coerce types)
                l_raw = nd.get("layout", {}) or {}
                if not isinstance(l_raw, dict):
                    l_raw = {}
                try:
                    lx = float(l_raw.get("x", 0.0) or 0.0)
                except Exception:
                    lx = 0.0
                try:
                    ly = float(l_raw.get("y", 0.0) or 0.0)
                except Exception:
                    ly = 0.0
                locked = bool(l_raw.get("locked", False))
                layout = NodeLayout(x=lx, y=ly, locked=locked)
                node = NodeData(id=nid, label=nd.get("label", "Node"), parentId=parent_id, attrs=attrs, layout=layout)
                # PM data (either under node.pm or legacy attrs.data.pm)
                pm_raw = nd.get("pm")
                if not isinstance(pm_raw, dict):
                    pm_raw = None
                if pm_raw is None and isinstance(attrs.data, dict):
                    maybe_pm = attrs.data.get("pm") if isinstance(attrs.data, dict) else None
                    if isinstance(maybe_pm, dict):
                        pm_raw = maybe_pm
                if isinstance(pm_raw, dict):
                    def _i(val, default=0):
                        try:
                            return int(val)
                        except Exception:
                            return default
                    node.pm = PMData(
                        number=pm_raw.get("number"),
                        name=pm_raw.get("name"),
                        duration=_i(pm_raw.get("duration", 1), 1),
                        FAZ=_i(pm_raw.get("FAZ", 0)),
                        FEZ=_i(pm_raw.get("FEZ", 0)),
                        SAZ=_i(pm_raw.get("SAZ", 0)),
                        SEZ=_i(pm_raw.get("SEZ", 0)),
                        GP=_i(pm_raw.get("GP", 0)),
                        FP=_i(pm_raw.get("FP", 0)),
                        isCritical=bool(pm_raw.get("isCritical", False)),
                        isSummary=bool(pm_raw.get("isSummary", False)),
                    )
                # PM dependencies
                deps_raw = nd.get("pmDeps")
                if not isinstance(deps_raw, list) and isinstance(pm_raw, dict):
                    deps_raw = pm_raw.get("deps")
                node.pmDeps = []
                if isinstance(deps_raw, list):
                    for d in deps_raw:
                        if not isinstance(d, dict):
                            continue
                        pred = d.get("predId") or d.get("pred") or d.get("source")
                        if not pred:
                            continue
                        t = str(d.get("type", "FS")).upper()
                        if t not in ("FS", "SS", "FF", "SF"):
                            t = "FS"
                        try:
                            lag = int(d.get("lag", 0))
                        except Exception:
                            lag = 0
                        node.pmDeps.append(PMDep(predId=str(pred), type=t, lag=lag))
                if node.attrs.shape not in SHAPES:
                    node.attrs.shape = "circle"
                self.doc.nodes[node.id] = node
            self.changed.emit()
            log.info("loaded graph: %d nodes", len(self.doc.nodes))
        except Exception as e:
            raise ValueError(f"Fehler beim Laden: {e}")


# -----------------------------
# Graphics Items
# -----------------------------

NODE_W = 110
NODE_H = 64


class EdgeItem(QGraphicsPathItem):
    def __init__(self, src: 'NodeItem', dst: 'NodeItem', decorations: bool = False,
                 is_pm: bool = False, pm_type: Optional[str] = None, pm_lag: int = 0,
                 pred_id: Optional[str] = None, succ_id: Optional[str] = None):
        super().__init__()
        self.setZValue(-1)
        self.src = src
        self.dst = dst
        self.decorations = decorations
        self.pen_normal = QPen(QColor(120, 120, 120), 1.5)
        # PM metadata
        self.is_pm = is_pm
        self.pm_type = (pm_type or "FS").upper() if is_pm else None
        self.pm_lag = int(pm_lag) if is_pm else 0
        self.pred_id = pred_id
        self.succ_id = succ_id
        # optional label
        from PySide6.QtWidgets import QGraphicsTextItem
        self.text_item = QGraphicsTextItem("", self)
        self.text_item.setDefaultTextColor(QColor(90, 90, 90))
        f = QFont("Arial", 8)
        self.text_item.setFont(f)
        self.update_path()

    def update_path(self):
        s = self.src.connection_pos_out()
        d = self.dst.connection_pos_in()
        path = QPainterPath(s)
        dx = (d.x() - s.x()) * 0.5
        c1 = QPointF(s.x() + dx, s.y())
        c2 = QPointF(d.x() - dx, d.y())
        path.cubicTo(c1, c2, d)
        self.setPath(path)
        self.setPen(self.pen_normal)
        # place label at midpoint for PM edges
        if self.is_pm:
            try:
                mid = self.path().pointAtPercent(0.5)
                sign = "+" if self.pm_lag > 0 else ("" if self.pm_lag == 0 else "-")
                lag_val = abs(int(self.pm_lag))
                label = f"{self.pm_type}{sign}{lag_val}" if self.pm_lag != 0 else f"{self.pm_type}"
                self.text_item.setPlainText(label)
                self.text_item.setPos(mid + QPointF(6, -6))
            except Exception:
                pass

    def paint(self, painter: QPainter, option, widget=None):
        super().paint(painter, option, widget)
        if self.decorations:
            # Draw simple arrow at target
            path = self.path()
            try:
                pos = path.pointAtPercent(0.98)
                prev = path.pointAtPercent(0.96)
            except Exception:
                return
            angle = math.degrees(math.atan2(pos.y() - prev.y(), pos.x() - prev.x()))
            painter.save()
            try:
                painter.translate(pos)
                painter.rotate(angle)
                painter.setBrush(QBrush(QColor(120, 120, 120)))
                poly = QPolygonF([
                    QPointF(0, 0), QPointF(-8, 3.5), QPointF(-8, -3.5)
                ])
                painter.drawPolygon(poly)
            finally:
                painter.restore()

    def contextMenuEvent(self, event):
        if not self.is_pm:
            return super().contextMenuEvent(event)
        from PySide6.QtWidgets import QMenu
        m = QMenu()
        act_edit = m.addAction("PM-Link bearbeiten…")
        act_del = m.addAction("PM-Link löschen")
        a = m.exec(event.screenPos())
        win = None
        try:
            win = self.scene().views()[0].window
        except Exception:
            pass
        if a == act_edit and win is not None:
            res = win._prompt_pm_link()
            if res is None:
                return
            t, lag = res
            # update model: remove old, add new
            win.model.remove_pm_dep(self.succ_id, self.pred_id, self.pm_type, self.pm_lag)
            win.model.add_pm_dep(self.pred_id, self.succ_id, t, int(lag))
            if win.model.doc.settings.pm.enabled:
                win.model.compute_cpm()
            win.view.sync_items_from_model()
        elif a == act_del and win is not None:
            win.model.remove_pm_dep(self.succ_id, self.pred_id, self.pm_type, self.pm_lag)
            if win.model.doc.settings.pm.enabled:
                win.model.compute_cpm()
            win.view.sync_items_from_model()


class NodeItem(QGraphicsItem):
    def __init__(self, model: GraphModel, node_id: str):
        super().__init__()
        self.model = model
        self.node_id = node_id
        self.setFlags(
            QGraphicsItem.ItemIsSelectable
            | QGraphicsItem.ItemIsMovable
            | QGraphicsItem.ItemSendsGeometryChanges
        )
        self.setAcceptHoverEvents(True)
        self.rect = QRectF(-NODE_W / 2, -NODE_H / 2, NODE_W, NODE_H)
        self._moving_with_children = False
        self.label_font = QFont("Arial", 10)

    # Connection points
    def connection_pos_in(self) -> QPointF:
        return self.mapToScene(QPointF(0, -NODE_H / 2))

    def connection_pos_out(self) -> QPointF:
        return self.mapToScene(QPointF(0, NODE_H / 2))

    def boundingRect(self) -> QRectF:
        return self.rect.adjusted(-8, -8, 8, 8)

    def shape(self) -> QPainterPath:
        return self._shape_path()

    # Drawing helpers for shapes
    def _shape_path(self) -> QPainterPath:
        n = self.model.doc.nodes[self.node_id]
        r = self.rect
        path = QPainterPath()
        s = n.attrs.shape
        if s == "circle":
            path.addEllipse(r)
        elif s == "rect":
            path.addRect(r)
        elif s == "rounded-rect":
            path.addRoundedRect(r, 10, 10)
        elif s == "diamond":
            path.moveTo(r.center().x(), r.top())
            path.lineTo(r.right(), r.center().y())
            path.lineTo(r.center().x(), r.bottom())
            path.lineTo(r.left(), r.center().y())
            path.closeSubpath()
        elif s == "hexagon":
            w, h = r.width(), r.height()
            cx, cy = r.center().x(), r.center().y()
            dx, dy = w / 2, h / 2
            points = [
                QPointF(cx - dx * 0.5, cy - dy),
                QPointF(cx + dx * 0.5, cy - dy),
                QPointF(cx + dx, cy),
                QPointF(cx + dx * 0.5, cy + dy),
                QPointF(cx - dx * 0.5, cy + dy),
                QPointF(cx - dx, cy),
            ]
            path.moveTo(points[0])
            for p in points[1:]:
                path.lineTo(p)
            path.closeSubpath()
        elif s == "triangle":
            path.moveTo(r.center().x(), r.top())
            path.lineTo(r.right(), r.bottom())
            path.lineTo(r.left(), r.bottom())
            path.closeSubpath()
        else:
            path.addRect(r)
        return path

    def paint(self, painter: QPainter, option, widget=None):
        n = self.model.doc.nodes[self.node_id]
        # fill color (effective with inheritance)
        color = self.model.effective_color(self.node_id)
        pen = QPen(QColor(60, 60, 60), 1.5)
        if self.isSelected():
            pen.setWidthF(2.5)
            pen.setColor(QColor(40, 120, 255))
        # Critical highlighting for projektnode in PM mode
        if n.attrs.shape == "projektnode" and n.pm and n.pm.isCritical:
            pen.setColor(QColor(200, 40, 40))
            pen.setWidthF(2.2)
        painter.setPen(pen)
        painter.setBrush(QBrush(color))
        painter.drawPath(self._shape_path())

        # Text rendering
        painter.setFont(self.label_font)
        painter.setPen(QPen(QColor(20, 20, 20)))
        br = self.rect
        if n.attrs.shape == "projektnode":
            # Header: number + name (or label fallback)
            header = ""
            if n.pm:
                if n.pm.number:
                    header = f"{n.pm.number} — {n.pm.name or n.label}"
                else:
                    header = n.pm.name or n.label
            else:
                header = n.label
            # Rows: FAZ|d|FEZ and SAZ|GP/FP|SEZ
            faz = n.pm.FAZ if n.pm else 0
            fez = n.pm.FEZ if n.pm else (faz + (n.pm.duration if n.pm else 1))
            saz = n.pm.SAZ if n.pm else 0
            sez = n.pm.SEZ if n.pm else saz + (n.pm.duration if n.pm else 1)
            dval = n.pm.duration if n.pm else 1
            gp = n.pm.GP if n.pm else 0
            fp = n.pm.FP if n.pm else 0
            row1 = f"FAZ {faz} | d {dval} | FEZ {fez}"
            if self.model.doc.settings.pm.showBuffers:
                row2 = f"SAZ {saz} | GP {gp}/FP {fp} | SEZ {sez}"
            else:
                row2 = f"SAZ {saz} | SEZ {sez}"
            # Draw lines with simple layout
            header_rect = QRectF(br.left()+6, br.top()+4, br.width()-12, br.height()/3)
            row1_rect = QRectF(br.left()+6, br.top()+22, br.width()-12, br.height()/3)
            row2_rect = QRectF(br.left()+6, br.top()+40, br.width()-12, br.height()/3)
            painter.drawText(header_rect, Qt.AlignLeft | Qt.TextSingleLine, header)
            painter.drawText(row1_rect, Qt.AlignLeft | Qt.TextSingleLine, row1)
            painter.drawText(row2_rect, Qt.AlignLeft | Qt.TextSingleLine, row2)
        else:
            # default: simple center label
            txt = n.label
            painter.drawText(br, Qt.AlignCenter | Qt.TextWordWrap, txt)

    # Movement & subtree drag
    def mousePressEvent(self, event):
        if event.button() == Qt.RightButton:
            try:
                sp = event.screenPos()
            except Exception:
                sp = event.scenePos()
            self._show_context_menu(sp)
            event.accept()
            return
        # PM link mode short-circuit: use clicks to create PM dependency
        if event.button() == Qt.LeftButton:
            try:
                win = self.scene().views()[0].window
            except Exception:
                win = None
            if win is not None and getattr(win, "_pm_link_mode", False):
                if not getattr(win, "_pm_link_src", None):
                    win._pm_link_src = self.node_id
                    win.statusBar().showMessage("PM-Link: Quelle gewählt. Jetzt Ziel anklicken…")
                    event.accept()
                    return
                else:
                    src = win._pm_link_src
                    dst = self.node_id
                    if src == dst:
                        QMessageBox.information(win, "PM-Link", "Quelle und Ziel dürfen nicht identisch sein.")
                        win.end_pm_link_mode()
                        event.accept()
                        return
                    res = win._prompt_pm_link()
                    if res is None:
                        win.end_pm_link_mode()
                        event.accept()
                        return
                    dep_type, lag = res
                    cmd = AddPMDepCommand(self.model, src, dst, dep_type, lag, self.scene().views()[0])
                    self.scene().views()[0].undo_stack.push(cmd)
                    win.end_pm_link_mode()
                    event.accept()
                    return
        if event.button() == Qt.LeftButton and (event.modifiers() & Qt.ShiftModifier):
            # Start moving with children
            self._moving_with_children = True
            self._orig_positions = self._collect_subtree_positions()
        else:
            self._moving_with_children = False
            self._orig_positions = {self.node_id: self.pos()}
        super().mousePressEvent(event)

    def _collect_subtree_positions(self) -> Dict[str, QPointF]:
        pos = {}
        stack = [self.node_id]
        seen: Set[str] = set()
        while stack:
            nid = stack.pop()
            if nid in seen:
                continue
            seen.add(nid)
            item = self.scene().views()[0].item_for_node(nid)
            if item:
                pos[nid] = item.pos()
            stack.extend(self.model.children_of(nid))
        return pos

    def mouseMoveEvent(self, event):
        if self._moving_with_children:
            delta = event.scenePos() - event.lastScenePos()
            # move self and all children items visually
            stack = [self.node_id]
            seen: Set[str] = set()
            while stack:
                nid = stack.pop()
                if nid in seen:
                    continue
                seen.add(nid)
                item = self.scene().views()[0].item_for_node(nid)
                if item and not self.model.doc.nodes[nid].layout.locked:
                    item.setPos(item.pos() + delta)
                stack.extend(self.model.children_of(nid))
            # update edges
            self.scene().views()[0].update_all_edges()
            event.accept()
            return
        super().mouseMoveEvent(event)
        self.scene().views()[0].update_all_edges()

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        view = self.scene().views()[0]
        # Batch move into undo command
        new_positions = {}
        if self._moving_with_children:
            for nid, oldp in self._orig_positions.items():
                item = view.item_for_node(nid)
                if item:
                    new_positions[nid] = item.pos()
        else:
            new_positions[self.node_id] = self.pos()
        if new_positions:
            view.push_move_command(self._orig_positions, new_positions)

    def _show_context_menu(self, screen_pos):
        m = QMenu()
        act_edit = m.addAction("Bearbeiten…")
        act_del = m.addAction("Löschen")
        m.addSeparator()
        act_reparent = m.addAction("Re-Parent starten")
        act = m.exec(screen_pos)
        if act == act_edit:
            self.scene().views()[0].window.info_panel.edit_node(self.node_id)
        elif act == act_del:
            self.scene().views()[0].window.delete_node(self.node_id)
        elif act == act_reparent:
            self.scene().views()[0].window.begin_reparent_mode()


# -----------------------------
# Scene/View & Undo Commands
# -----------------------------

class GraphScene(QGraphicsScene):
    def __init__(self, model: GraphModel):
        super().__init__()
        self.model = model


class MoveNodesCommand(QUndoCommand):
    def __init__(self, model: GraphModel, old: Dict[str, QPointF], new: Dict[str, QPointF], view: 'GraphView'):
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
    def __init__(self, model: GraphModel, parent_id: Optional[str], pos: QPointF, view: 'GraphView'):
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
    def __init__(self, model: GraphModel, node_id: str, view: 'GraphView'):
        super().__init__("Delete Node")
        self.model = model
        self.node_id = node_id
        self.view = view
        self.snapshot = None

    def _take_snapshot(self):
        # Store full doc to reconstruct (simple but robust)
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
    def __init__(self, model: GraphModel, child_id: str, new_parent_id: Optional[str], view: 'GraphView'):
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
    def __init__(self, model: GraphModel, view: 'GraphView'):
        super().__init__("Auto-Layout")
        self.model = model
        self.view = view
        self.before = None
        self.after = None

    def _compute_layout(self) -> Dict[str, Tuple[float, float]]:
        if nx is None:
            QMessageBox.warning(self.view.window, "Auto-Layout", "networkx nicht installiert. Bitte 'pip install networkx'.")
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
            # Likely missing numpy; use simple fallback
            QMessageBox.warning(self.view.window, "Auto-Layout", "spring_layout benoetigt NumPy. Fallback-Layout wird verwendet. Optional: pip install numpy")
            return self._fallback_tree_layout()
        # Normalize & scale positions
        xs = [p[0] for p in pos.values()]
        ys = [p[1] for p in pos.values()]
        minx, maxx = min(xs), max(xs)
        miny, maxy = min(ys), max(ys)
        w = max(1e-5, maxx - minx)
        h = max(1e-5, maxy - miny)
        scale = 600
        out = {}
        for nid, (x, y) in pos.items():
            out[nid] = (scale * (x - minx) / w, scale * (y - miny) / h)
        return out

    def _fallback_tree_layout(self) -> Dict[str, Tuple[float, float]]:
        # Simple layered layout using parentId relationships
        nodes = list(self.model.doc.nodes.keys())
        if not nodes:
            return {}
        # Identify roots (no parent or missing parent)
        roots = [nid for nid in nodes if not self.model.doc.nodes[nid].parentId or self.model.doc.nodes[nid].parentId not in self.model.doc.nodes]
        if not roots:
            roots = [nodes[0]]
        depths: Dict[str, int] = {}
        # BFS from roots
        for r in roots:
            if r in depths:
                continue
            depths[r] = 0
            q = [r]
            qi = 0
            while qi < len(q):
                u = q[qi]; qi += 1
                for v in self.model.children_of(u):
                    if v in depths:
                        continue
                    depths[v] = depths[u] + 1
                    q.append(v)
        # Assign remaining (e.g., cyclic components) to depth 0
        for nid in nodes:
            depths.setdefault(nid, 0)
        # Group by depth
        layers: Dict[int, List[str]] = {}
        for nid, d in depths.items():
            layers.setdefault(d, []).append(nid)
        # Positioning
        gap_x = 180.0
        gap_y = 140.0
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
    def __init__(self, model: GraphModel, pred_id: str, succ_id: str, dep_type: str, lag: int, view: 'GraphView'):
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
                QMessageBox.warning(self.view.window, "PM-Link", "Verknüpfung wurde nicht angelegt (Zyklus oder Duplikat).")
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


class GraphView(QGraphicsView):
    def __init__(self, model: GraphModel, window: 'MainWindow'):
        super().__init__()
        self.model = model
        self.window = window
        self.setRenderHint(QPainter.Antialiasing, True)
        self.setViewportUpdateMode(QGraphicsView.FullViewportUpdate)
        self.setDragMode(QGraphicsView.RubberBandDrag)
        self.scene_ = GraphScene(model)
        self.setScene(self.scene_)
        self.undo_stack = QUndoStack(self)
        self.undo_stack.setClean()
        self.items_by_id: Dict[str, NodeItem] = {}
        self.edges: List[EdgeItem] = []
        self._init_background()
        self.sync_items_from_model()

    def _init_background(self):
        self.setBackgroundBrush(QBrush(QColor(250, 250, 250)))

    # Utility
    def item_for_node(self, node_id: str) -> Optional[NodeItem]:
        return self.items_by_id.get(node_id)

    def sync_items_from_model(self):
        # remove missing items
        for nid in list(self.items_by_id.keys()):
            if nid not in self.model.doc.nodes:
                self.scene_.removeItem(self.items_by_id[nid])
                del self.items_by_id[nid]
        # add/update items
        for nid, n in self.model.doc.nodes.items():
            item = self.items_by_id.get(nid)
            if not item:
                item = NodeItem(self.model, nid)
                self.scene_.addItem(item)
                self.items_by_id[nid] = item
            item.setPos(QPointF(n.layout.x, n.layout.y))
        self._rebuild_edges()
        self.scene_.update()
        # keep minimap in sync
        try:
            self.window._update_minimap_fit()
        except Exception:
            pass

    def _rebuild_edges(self):
        for e in self.edges:
            self.scene_.removeItem(e)
        self.edges.clear()
        deco = self.model.doc.settings.edges.decorationsEnabled
        for nid, n in self.model.doc.nodes.items():
            if n.parentId and n.parentId in self.items_by_id:
                e = EdgeItem(self.items_by_id[n.parentId], self.items_by_id[nid], decorations=deco)
                self.scene_.addItem(e)
                self.edges.append(e)
        # PM dependency edges (only visible in PM mode)
        if self.model.doc.settings.pm.enabled:
            for nid, n in self.model.doc.nodes.items():
                if not n.pmDeps:
                    continue
                for d in n.pmDeps:
                    src_id = d.predId
                    dst_id = nid
                    if src_id in self.items_by_id and dst_id in self.items_by_id:
                        e = EdgeItem(self.items_by_id[src_id], self.items_by_id[dst_id], decorations=deco,
                                     is_pm=True, pm_type=d.type, pm_lag=int(getattr(d, 'lag', 0)),
                                     pred_id=src_id, succ_id=dst_id)
                        # Style: dashed grey; red if both nodes critical
                        pen = QPen(QColor(140, 140, 140), 1.4)
                        pen.setStyle(Qt.DashLine)
                        try:
                            src_pm = self.model.doc.nodes[src_id].pm
                            dst_pm = self.model.doc.nodes[dst_id].pm
                            if src_pm and dst_pm and src_pm.isCritical and dst_pm.isCritical:
                                pen = QPen(QColor(200, 40, 40), 2.0)
                                pen.setStyle(Qt.SolidLine)
                        except Exception:
                            pass
                        e.pen_normal = pen
                        e.update_path()
                        self.scene_.addItem(e)
                        self.edges.append(e)

    def update_all_edges(self):
        for e in self.edges:
            e.update_path()

    # Zoom controls
    def zoom_in(self):
        self.scale(1.15, 1.15)

    def zoom_out(self):
        self.scale(0.87, 0.87)

    def fit_to_view(self):
        items = self.items()
        if not items:
            return
        rect = self.scene_.itemsBoundingRect()
        if rect.isNull():
            return
        self.fitInView(rect.adjusted(-40, -40, 40, 40), Qt.KeepAspectRatio)

    # PNG export (whole scene, transparent)
    def export_png(self, path: str):
        rect = self.scene_.itemsBoundingRect().toRect()
        if rect.isEmpty():
            return
        img = QPixmap(rect.size())
        img.fill(Qt.transparent)
        painter = QPainter(img)
        painter.setRenderHint(QPainter.Antialiasing)
        self.scene_.render(painter, target=QRectF(img.rect()), source=QRectF(rect))
        painter.end()
        img.save(path, "PNG")

    # Undo helpers
    def push_move_command(self, old: Dict[str, QPointF], new: Dict[str, QPointF]):
        cmd = MoveNodesCommand(self.model, old, new, self)
        self.undo_stack.push(cmd)

    def wheelEvent(self, event):
        if event.modifiers() & Qt.ControlModifier:
            # Ctrl + Wheel = normal scroll
            super().wheelEvent(event)
            return
        delta = event.angleDelta().y()
        if delta > 0:
            self.zoom_in()
        else:
            self.zoom_out()

# -----------------------------
# Minimap View
# -----------------------------

class MiniMap(QGraphicsView):
    def __init__(self, main_view: GraphView):
        super().__init__(main_view.scene())
        self.main_view = main_view
        self.setRenderHint(QPainter.Antialiasing, False)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setInteractive(False)
        self.setStyleSheet("background: rgba(255,255,255,220); border: 1px solid #aaa;")
        self.setFixedSize(200, 150)
        # keep updated when scene changes
        try:
            self.scene().changed.connect(self._on_scene_changed)
        except Exception:
            pass

    def _on_scene_changed(self, *_):
        self.fit_to_scene()

    def fit_to_scene(self):
        rect = self.scene().itemsBoundingRect()
        if not rect.isNull():
            self.fitInView(rect.adjusted(-40, -40, 40, 40), Qt.KeepAspectRatio)

    def showEvent(self, event):
        super().showEvent(event)
        self.fit_to_scene()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.fit_to_scene()

    def mousePressEvent(self, event):
        p = self.mapToScene(event.position().toPoint())
        self._center_main(p)

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.LeftButton:
            p = self.mapToScene(event.position().toPoint())
            self._center_main(p)

    def _center_main(self, scene_point: QPointF):
        self.main_view.centerOn(scene_point)

    def drawForeground(self, painter: QPainter, rect):
        # draw the main view's visible rect as an overlay
        try:
            vis = self.main_view.mapToScene(self.main_view.viewport().rect()).boundingRect()
            pen = QPen(QColor(200, 0, 0))
            pen.setWidth(2)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(vis)
        except Exception:
            pass


# -----------------------------
# Info Panel
# -----------------------------

class InfoPanel(QWidget):
    def __init__(self, model: GraphModel, view: GraphView):
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
        self.shape_combo = QComboBox(); self.shape_combo.addItems(SHAPES)
        self.inherit_chk = QCheckBox("Farbe erben")
        self.color_btn = QPushButton("Farbe wählen…")
        self.color_lbl = QLabel("#-")

        # Text / Beschreibung
        self.text_edit = QTextEdit()
        self.text_edit.setPlaceholderText("Beschreibung / Text …")
        self.text_edit.setFixedHeight(100)

        # Buttons
        self.btn_edit = QPushButton("Bearbeiten")
        self.btn_save = QPushButton("Speichern")
        self.btn_cancel = QPushButton("Abbrechen")
        self.btn_save.hide(); self.btn_cancel.hide()

        self.form.addRow("ID:", self.id_lbl)
        self.form.addRow("Label:", self.label_edit)
        self.form.addRow("Shape:", self.shape_combo)
        self.form.addRow("", self.inherit_chk)
        hl = QHBoxLayout(); hl.addWidget(self.color_btn); hl.addWidget(self.color_lbl); w = QWidget(); w.setLayout(hl)
        self.form.addRow("Farbe:", w)
        self.form.addRow("Text:", self.text_edit)

        # PM fields (projektnode)
        self.pm_number = QLineEdit()
        self.pm_name = QLineEdit()
        self.pm_duration = QSpinBox(); self.pm_duration.setRange(0, 100000); self.pm_duration.setValue(1)
        self.pm_faz = QLineEdit(); self.pm_faz.setReadOnly(True)
        self.pm_fez = QLineEdit(); self.pm_fez.setReadOnly(True)
        self.pm_saz = QLineEdit(); self.pm_saz.setReadOnly(True)
        self.pm_sez = QLineEdit(); self.pm_sez.setReadOnly(True)
        self.pm_gp = QLineEdit(); self.pm_gp.setReadOnly(True)
        self.pm_fp = QLineEdit(); self.pm_fp.setReadOnly(True)

        self.form.addRow("Vorgangsnummer:", self.pm_number)
        self.form.addRow("Vorgangsname:", self.pm_name)
        self.form.addRow("Dauer (d, Tage):", self.pm_duration)
        self.form.addRow("FAZ/FEZ:", self.pm_faz)
        self.form.addRow("SAZ/SEZ:", self.pm_saz)
        self.form.addRow("GP/FP:", self.pm_gp)
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
        for w in (self.label_edit, self.shape_combo, self.inherit_chk, self.color_btn, self.text_edit,
                  self.pm_number, self.pm_name, self.pm_duration):
            w.setEnabled(on)
        # If summary, duration stays read-only even in edit mode
        if on and self._pm_is_summary:
            try:
                self.pm_duration.setEnabled(False)
            except Exception:
                pass
        self.btn_edit.setVisible(not on)
        self.btn_save.setVisible(on)
        self.btn_cancel.setVisible(on)

    def show_node(self, node_id: Optional[str]):
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
        # summary detection: has children or marked summary
        has_children = len(self.view.window.model.children_of(n.id)) > 0
        self._pm_is_summary = bool(n.pm and (n.pm.isSummary or has_children))
        if n.pm:
            self.pm_number.setText(n.pm.number or "")
            self.pm_name.setText(n.pm.name or n.label)
            self.pm_duration.setValue(int(n.pm.duration))
            self.pm_faz.setText(f"{n.pm.FAZ} | FEZ {n.pm.FEZ}")
            self.pm_saz.setText(f"{n.pm.SAZ} | SEZ {n.pm.SEZ}")
            self.pm_gp.setText(f"GP {n.pm.GP} / FP {n.pm.FP}")
            # lock duration if summary
            try:
                self.pm_duration.setEnabled(not self._pm_is_summary)
            except Exception:
                pass
        else:
            for w in (self.pm_number, self.pm_name, self.pm_duration, self.pm_faz, self.pm_saz, self.pm_gp):
                if isinstance(w, QSpinBox):
                    w.setValue(1)
                else:
                    w.setText("")
        self._set_editing(False)

    def edit_node(self, node_id: str):
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
        attrs = {
            "label": self.label_edit.text(),
            "shape": self.shape_combo.currentText(),
            "inherit": self.inherit_chk.isChecked(),
            "color": self.color_lbl.text() if self.color_lbl.text() and self.color_lbl.text() != "#-" else None,
        }
        # merge text into data
        cur = dict(self.model.doc.nodes[self.current_id].attrs.data)
        cur["text"] = self.text_edit.toPlainText()
        attrs["data"] = cur
        # PM payload (only if projektnode or PM fields were filled)
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
        c = QColorDialog.getColor(QColor(120, 170, 255), self, "Farbe wählen")
        if c.isValid():
            self.color_lbl.setText(c.name())

    def _shape_changed(self, _):
        pass  # handled on save

    def _inherit_toggled(self, _):
        pass  # handled on save


# -----------------------------
# Hilfe Window
# -----------------------------

class HelpWindow(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Hilfe")
        self.resize(700, 600)
        lay = QVBoxLayout(self)
        txt = QTextEdit(self)
        txt.setReadOnly(True)
        txt.setPlainText(self._help_text())
        btn_close = QPushButton("Schließen", self)
        btn_close.clicked.connect(self.accept)
        lay.addWidget(txt)
        lay.addWidget(btn_close)

    def _help_text(self) -> str:
        # ASCII-only help text to avoid encoding issues
        return (
            "DAG Graph Editor - Hilfe\n\n"
            "Ueberblick\n"
            "- Toolbar: Neue Node, Re-Parent, Undo/Redo, Auto-Layout, Speichern/Laden, PNG.\n"
            "- Info-Panel (rechts): Label/Shape/Farbe/Text und bei Projektnodes PM-Felder.\n"
            "- Minimap (unten): Uebersicht, ein-/ausblendbar.\n\n"
            "Projektmanagement (PM)\n"
            "- PM-Modus an/aus: schaltet PM-Rendering und Berechnungen.\n"
            "- Projektnode: Kopf (Nr-Name), Zeile1 FAZ|d|FEZ, Zeile2 SAZ|GP/FP|SEZ.\n"
            "- Verknuepfen (PM): Toolbar -> Quelle -> Ziel -> Typ/Lag waehlen; Kantenlabel z.B. FS+2.\n"
            "- Kritischen Pfad berechnen: aktualisiert FAZ/FEZ/SAZ/SEZ/GP/FP und Markierung.\n"
            "- Auto-Recalc: bei Aenderungen (Dauer, PM-Link, Re-Parent, Loeschen).\n\n"
            "Abkuerzungen\n"
            "- FAZ: Fruehester Anfangszeitpunkt\n"
            "- FEZ: Fruehester Endzeitpunkt (= FAZ + d)\n"
            "- SAZ: Spaetester Anfangszeitpunkt\n"
            "- SEZ: Spaetester Endzeitpunkt (= SAZ + d)\n"
            "- d: Dauer (Tage)\n"
            "- GP: Gesamtpuffer (= SAZ - FAZ)\n"
            "- FP: Freier Puffer (allgemein je Link-Typ):\n"
            "      FS: min(ES_j) - (EF_i + Lag)\n"
            "      SS: min(ES_j) - (ES_i + Lag)\n"
            "      FF: min(EF_j) - (EF_i + Lag)\n"
            "      SF: min(EF_j) - (ES_i + Lag)\n\n"
            "PM-Verknuepfungstypen\n"
            "- FS (Finish-Start)\n"
            "- SS (Start-Start)\n"
            "- FF (Finish-Finish)\n"
            "- SF (Start-Finish)\n"
            "- Lag: Zeitversatz in Tagen (negativ=Lead erlaubt).\n\n"
            "Summary/WBS\n"
            "- Parent fasst Kinder zusammen: ES=min(ES Kinder), EF=max(EF Kinder), d=EF-ES.\n"
            "- Summary-Felder berechnet; keine eigenen PM-Links noetig.\n\n"
            "Bedienhinweise\n"
            "- Neue Node: im PM-Modus automatisch Projektnode.\n"
            "- Re-Parent: Kind klicken, dann neuer Parent.\n"
            "- Rechtsklick Node: Kontextmenue (Bearbeiten/Loeschen).\n"
            "- Rechtsklick PM-Kante: Bearbeiten (Typ/Lag) oder Loeschen.\n\n"
            "Fehler & Validierung\n"
            "- Zyklen werden beim Anlegen von PM-Links blockiert.\n"
            "- Negative Lags erlaubt; Einheit: Tage (kein Kalender).\n"
        )
# -----------------------------
# Main Window
# -----------------------------

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("DAG Graph Editor — MVP")
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
        ciw = QWidget(); cil = QVBoxLayout(ciw)
        self.custom_info_edit = QPlainTextEdit()
        self.custom_info_edit.setPlaceholderText("JSON der Node-Attribute 'data' hier bearbeiten…")
        cil.addWidget(self.custom_info_edit)
        ci_buttons = QHBoxLayout()
        self.custom_info_apply_btn = QPushButton("Übernehmen")
        self.custom_info_reload_btn = QPushButton("Neu laden")
        ci_buttons.addWidget(self.custom_info_apply_btn)
        ci_buttons.addWidget(self.custom_info_reload_btn)
        cil.addLayout(ci_buttons)
        self.custom_info_dock = QDockWidget("Custom Info")
        self.custom_info_dock.setWidget(ciw)
        self.addDockWidget(Qt.RightDockWidgetArea, self.custom_info_dock)
        self.custom_info_apply_btn.clicked.connect(self.custom_info_apply)
        self.custom_info_reload_btn.clicked.connect(self.custom_info_reload)

        # Menu bar: Hilfe
        mb = self.menuBar()
        m_help = mb.addMenu("Hilfe")
        self.act_show_help = QAction("Hilfe anzeigen", self)
        self.act_show_help.triggered.connect(self.show_help)
        m_help.addAction(self.act_show_help)

        # Toolbar
        self.toolbar = QToolBar("Tools")
        self.addToolBar(Qt.TopToolBarArea, self.toolbar)
        self._build_toolbar()

        # Status
        self.statusBar().showMessage("Bereit")

        # Selection change handler via timer polling (simpler than signals wiring)
        self._sel_timer = QTimer(self)
        self._sel_timer.timeout.connect(self._update_selected_in_panel)
        self._sel_timer.start(300)

        # Reparent state
        self._reparent_mode = False
        self._reparent_child: Optional[str] = None
        # PM link state
        self._pm_link_mode = False
        self._pm_link_src: Optional[str] = None

        # Settings affect UI
        self._apply_settings_to_ui()

        # Seed content
        self._seed_sample()

        # keep minimap viewport overlay updated on main view scroll/zoom
        try:
            self.view.horizontalScrollBar().valueChanged.connect(lambda _: self.minimap.viewport().update())
            self.view.verticalScrollBar().valueChanged.connect(lambda _: self.minimap.viewport().update())
        except Exception:
            pass

        # Help window instance holder
        self._help_window: Optional[HelpWindow] = None

    # ------------- UI building -------------
    def _build_toolbar(self):
        def btn(text: str, slot):
            a = QAction(text, self)
            a.triggered.connect(slot)
            self.toolbar.addAction(a)
            return a

        self.act_new_node = btn("Neue Node", self.add_node)
        self.act_delete_node = btn("Node löschen", self.delete_selected)
        self.toolbar.addSeparator()
        self.act_reparent = btn("Re-Parent-Modus", self.begin_reparent_mode)
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
        self.act_save = btn("Graph speichern", self.save_graph)
        self.act_load = btn("Graph laden", self.load_graph)
        self.act_export = btn("PNG exportieren", self.export_png)
        self.toolbar.addSeparator()
        # PM mode toggles
        self.act_pm_toggle = btn("PM-Modus an/aus", self.toggle_pm_mode)
        self.act_pm_buffers = btn("PM-Puffer anzeigen", self.toggle_pm_buffers)
        self.act_pm_link = btn("Vorgang verknüpfen (PM)", self.begin_pm_link_mode)
        self.act_pm_cpm = btn("Kritischen Pfad berechnen", self.action_compute_cpm)
        self.toolbar.addSeparator()
        self.act_toggle_minimap = btn("Minimap an/aus", self.toggle_minimap)
        self.act_toggle_acyclic = btn("Azyklik prüfen an/aus", self.toggle_acyclic)
        self.act_toggle_inherit = btn("Farbvererbung an/aus", self.toggle_inheritance)
        self.toolbar.addSeparator()
        # Edge arrowheads toggle
        self.act_toggle_arrows = btn("Pfeile an/aus", self.toggle_arrows)
        self.toolbar.addSeparator()
        self.act_toggle_info = btn("Info an/aus", self.toggle_info)
        # Gradient controls (simple: preset buttons)
        self.toolbar.addSeparator()
        self.act_grad_light = btn("Gradient -8/-3", self.set_default_gradient)

    # ------------- Actions -------------
    def _update_selected_in_panel(self):
        # Beim Editieren: nicht überschreiben
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
        self.minimap_dock.setVisible(self.model.doc.settings.ui.showMinimap)
        self._update_minimap_fit()
        self.view.scene_.update()

    def toggle_pm_mode(self):
        s = self.model.doc.settings
        s.pm.enabled = not s.pm.enabled
        self.statusBar().showMessage(f"PM-Modus: {'an' if s.pm.enabled else 'aus'}", 2000)
        if s.pm.enabled:
            try:
                self.model.compute_cpm()
            except Exception:
                pass
        self.view._rebuild_edges()
        self.view.scene_.update()

    def toggle_pm_buffers(self):
        s = self.model.doc.settings
        s.pm.showBuffers = not s.pm.showBuffers
        self.view.scene_.update()

    def _update_minimap_fit(self):
        if self.minimap.isVisible():
            self.minimap.fit_to_scene()

    def show_help(self):
        if self._help_window is None:
            self._help_window = HelpWindow(self)
        self._help_window.show()
        self._help_window.raise_()
        self._help_window.activateWindow()

    def toggle_minimap(self):
        s = self.model.doc.settings
        s.ui.showMinimap = not s.ui.showMinimap
        self._apply_settings_to_ui()

    def toggle_info(self):
        self.info_dock.setVisible(not self.info_dock.isVisible())

    def toggle_acyclic(self):
        s = self.model.doc.settings
        s.validation.enforceAcyclic = not s.validation.enforceAcyclic
        self.statusBar().showMessage(f"Azyklik-Prüfung: {'an' if s.validation.enforceAcyclic else 'aus'}", 2000)

    def toggle_inheritance(self):
        s = self.model.doc.settings
        s.styling.enableColorInheritance = not s.styling.enableColorInheritance
        self.view.scene_.update()

    def toggle_arrows(self):
        s = self.model.doc.settings
        s.edges.decorationsEnabled = not s.edges.decorationsEnabled
        # Rebuild edges to reflect arrowheads on/off
        self.view._rebuild_edges()
        self.view.scene_.update()

    def set_default_gradient(self):
        s = self.model.doc.settings.styling
        s.inheritanceLuminanceStep = -8
        s.inheritanceSaturationStep = -3
        self.view.scene_.update()

    def item_for_node(self, node_id: str) -> Optional[NodeItem]:
        return self.view.item_for_node(node_id)

    def add_node(self):
        pos = self.view.mapToScene(self.view.viewport().rect().center())
        parent_id = None
        sel = [it for it in self.view.scene_.selectedItems() if isinstance(it, NodeItem)]
        if sel:
            parent_id = sel[0].node_id
        cmd = AddNodeCommand(self.model, parent_id, pos, self.view)
        self.view.undo_stack.push(cmd)

    def delete_selected(self):
        sel = [it for it in self.view.scene_.selectedItems() if isinstance(it, NodeItem)]
        if not sel:
            QMessageBox.information(self, "Löschen", "Bitte eine Node auswählen.")
            return
        self.delete_node(sel[0].node_id)

    def delete_node(self, node_id: str):
        ret = QMessageBox.question(
            self,
            "Löschen",
            "Node wirklich löschen?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if ret != QMessageBox.Yes:
            return
        cmd = DeleteNodeCommand(self.model, node_id, self.view)
        self.view.undo_stack.push(cmd)

    # Reparent flow (Variant A)
    def begin_reparent_mode(self):
        self._reparent_mode = True
        self._reparent_child = None
        self.statusBar().showMessage("Re-Parent: Zuerst Child klicken, dann neuen Parent.")
        log.info("reparent_mode begin")
        # Install temporary event filter on scene to capture clicks
        self.view.viewport().installEventFilter(self)

    def end_reparent_mode(self):
        if self._reparent_mode:
            self._reparent_mode = False
            self._reparent_child = None
            self.statusBar().showMessage("Re-Parent beendet", 2000)
            log.info("reparent_mode end")
            self.view.viewport().removeEventFilter(self)

    # ----- PM link flow -----
    def begin_pm_link_mode(self):
        self._pm_link_mode = True
        self._pm_link_src = None
        self.statusBar().showMessage("PM-Link: Zuerst Quelle, dann Ziel anklicken.")
        try:
            self.view.viewport().installEventFilter(self)
        except Exception:
            pass

    def end_pm_link_mode(self):
        if self._pm_link_mode:
            self._pm_link_mode = False
            self._pm_link_src = None
            self.statusBar().showMessage("PM-Link beendet", 2000)
            try:
                self.view.viewport().removeEventFilter(self)
            except Exception:
                pass

    def _prompt_pm_link(self) -> Optional[Tuple[str, int]]:
        # Simple modal dialog for type/lag
        from PySide6.QtWidgets import QDialog, QDialogButtonBox
        dlg = QDialog(self)
        dlg.setWindowTitle("PM-Verknüpfung")
        lay = QFormLayout(dlg)
        type_combo = QComboBox(dlg)
        type_combo.addItems(["FS", "SS", "FF", "SF"])
        lag_spin = QSpinBox(dlg)
        lag_spin.setRange(-100000, 100000)
        lag_spin.setValue(0)
        lay.addRow("Typ:", type_combo)
        lay.addRow("Lag (Tage):", lag_spin)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, parent=dlg)
        lay.addWidget(bb)
        bb.accepted.connect(dlg.accept)
        bb.rejected.connect(dlg.reject)
        if dlg.exec() == QDialog.Accepted:
            return type_combo.currentText(), int(lag_spin.value())
        return None

    def action_compute_cpm(self):
        ok, err = self.model.compute_cpm()
        if not ok and err:
            QMessageBox.warning(self, "CPM", err)
        self.view.sync_items_from_model()

    def eventFilter(self, obj, event):
        if obj is self.view.viewport() and self._reparent_mode:
            if event.type() == QEvent.MouseButtonPress and event.button() == Qt.LeftButton:
                try:
                    sp = event.position().toPoint()  # Qt6
                except Exception:
                    sp = event.pos()                # fallback
                scene_p = self.view.mapToScene(sp)
                items = self.view.scene_.items(scene_p)
                node_item = next((it for it in items if isinstance(it, NodeItem)), None)
                if node_item:
                    if not self._reparent_child:
                        self._reparent_child = node_item.node_id
                        self.statusBar().showMessage("Re-Parent: Jetzt neuen Parent wählen…")
                        log.info("reparent pick child=%s", self._reparent_child)
                    else:
                        new_parent = node_item.node_id
                        child = self._reparent_child
                        if self.model.doc.settings.validation.enforceAcyclic and not self.model.is_acyclic_if_reparent(child, new_parent):
                            QMessageBox.warning(self, "Re-Parent", "Zyklus würde entstehen – abgebrochen.")
                            self.end_reparent_mode()
                            return True
                        cmd = ReparentCommand(self.model, child, new_parent, self.view)
                        self.view.undo_stack.push(cmd)
                        log.info("reparent commit child=%s new_parent=%s", child, new_parent)
                        self.end_reparent_mode()
                        return True
                else:
                    # click on empty → treat as root parent
                    if self._reparent_child:
                        cmd = ReparentCommand(self.model, self._reparent_child, None, self.view)
                        self.view.undo_stack.push(cmd)
                        log.info("reparent commit child=%s new_parent=None", self._reparent_child)
                        self.end_reparent_mode()
                        return True
        return super().eventFilter(obj, event)

    def auto_layout(self):
        cmd = AutoLayoutCommand(self.model, self.view)
        self.view.undo_stack.push(cmd)
        # update minimap after relayout
        self._update_minimap_fit()

    def export_png(self):
        path, _ = QFileDialog.getSaveFileName(self, "PNG exportieren", "graph.png", "PNG (*.png)")
        if not path:
            return
        self.view.export_png(path)

    def save_graph(self):
        path, _ = QFileDialog.getSaveFileName(self, "Graph speichern", "graph.json", "JSON (*.json)")
        if not path:
            return
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.model.to_json(), f, ensure_ascii=False, indent=2)
        self.statusBar().showMessage("Gespeichert.", 2000)

    def load_graph(self):
        path, _ = QFileDialog.getOpenFileName(self, "Graph laden", "", "JSON (*.json)")
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.model.from_json(data)
            # If PM mode is on, compute CPM before syncing
            if self.model.doc.settings.pm.enabled:
                try:
                    self.model.compute_cpm()
                except Exception:
                    pass
            self.view.sync_items_from_model()
            self._apply_settings_to_ui()
            # keep minimap in sync after loading
            self._update_minimap_fit()
            self.statusBar().showMessage("Geladen.", 2000)
        except Exception as e:
            QMessageBox.critical(self, "Fehler", str(e))

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
        node_id = self.info_panel.current_id
        if not node_id or node_id not in self.model.doc.nodes:
            return
        try:
            new_data = json.loads(self.custom_info_edit.toPlainText() or "{}")
        except Exception as e:
            QMessageBox.critical(self, "JSON-Fehler", f"Custom Info ist kein gültiges JSON:\n{e}")
            return
        cmd = EditNodeCommand(self.model, node_id, {"data": new_data}, self.view)
        self.view.undo_stack.push(cmd)

    def custom_info_reload(self):
        self._update_custom_info_for_node(self.info_panel.current_id)

    # Seed sample content
    def _seed_sample(self):
        # Create 3 nodes in a chain
        a = self.model.add_node("Root", None, QPointF(0, 0))
        b = self.model.add_node("Child A", a.id, QPointF(0, 120))
        c = self.model.add_node("Child B", b.id, QPointF(0, 240))
        self.view.sync_items_from_model()
        self.view.fit_to_view()


# -----------------------------
# App entry
# -----------------------------

def main():
    app = QApplication(sys.argv)
    w = MainWindow()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
