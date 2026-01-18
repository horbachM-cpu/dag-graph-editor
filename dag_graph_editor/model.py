"""
Data model for DAG Graph Editor.

Contains all dataclasses for nodes, settings, and the graph document,
as well as the GraphModel class with mutation and query methods.
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Set, Tuple, TYPE_CHECKING

from PySide6.QtCore import QObject, Signal, QPointF
from PySide6.QtGui import QColor

from .constants import SHAPES

log = logging.getLogger("dag_editor")


def gen_id(prefix: str = "n") -> str:
    """Generate a unique node ID."""
    return f"{prefix}{uuid.uuid4().hex[:8]}"


# -----------------------------
# Data Classes
# -----------------------------

@dataclass
class PMDep:
    """Project Management dependency between nodes."""
    predId: str
    type: str = "FS"  # FS, SS, FF, SF
    lag: int = 0      # Days, negative = Lead allowed


@dataclass
class PMData:
    """Project Management data for a node."""
    number: Optional[str] = None
    name: Optional[str] = None
    duration: int = 1              # Days
    FAZ: int = 0                   # Earliest Start (Frühester Anfangszeitpunkt)
    FEZ: int = 0                   # Earliest End (Frühester Endzeitpunkt)
    SAZ: int = 0                   # Latest Start (Spätester Anfangszeitpunkt)
    SEZ: int = 0                   # Latest End (Spätester Endzeitpunkt)
    GP: int = 0                    # Total Float (Gesamtpuffer)
    FP: int = 0                    # Free Float (Freier Puffer)
    isCritical: bool = False
    isSummary: bool = False        # WBS-Parent: Roll-up, duration not editable


@dataclass
class NodeAttrs:
    """Visual attributes for a node."""
    color: Optional[str] = None    # Hex string like "#RRGGBB"
    inheritColor: bool = True
    shape: str = "circle"
    data: Dict[str, str] = field(default_factory=dict)


@dataclass
class NodeLayout:
    """Position and layout state for a node."""
    x: float = 0.0
    y: float = 0.0
    locked: bool = False


@dataclass
class NodeData:
    """Complete data for a single node."""
    id: str
    label: str = "Node"
    parentId: Optional[str] = None
    attrs: NodeAttrs = field(default_factory=NodeAttrs)
    layout: NodeLayout = field(default_factory=NodeLayout)
    pm: Optional[PMData] = None
    pmDeps: List[PMDep] = field(default_factory=list)


@dataclass
class SettingsValidation:
    """Validation settings."""
    enforceAcyclic: bool = True


@dataclass
class SettingsHistory:
    """History/Undo settings."""
    maxDepth: int = 100


@dataclass
class SettingsUI:
    """UI visibility settings."""
    showMinimap: bool = True


@dataclass
class SettingsStyling:
    """Color and style settings."""
    enableColorInheritance: bool = True
    inheritanceLuminanceStep: int = -8   # Percent per depth level
    inheritanceSaturationStep: int = -3


@dataclass
class SettingsEdges:
    """Edge rendering settings."""
    decorationsEnabled: bool = True  # Arrows/labels


@dataclass
class SettingsPM:
    """Project Management mode settings."""
    enabled: bool = False
    showBuffers: bool = True


@dataclass
class GraphSettings:
    """All graph settings combined."""
    validation: SettingsValidation = field(default_factory=SettingsValidation)
    history: SettingsHistory = field(default_factory=SettingsHistory)
    ui: SettingsUI = field(default_factory=SettingsUI)
    styling: SettingsStyling = field(default_factory=SettingsStyling)
    edges: SettingsEdges = field(default_factory=SettingsEdges)
    pm: SettingsPM = field(default_factory=SettingsPM)


@dataclass
class GraphMeta:
    """Graph metadata."""
    title: str = "My Graph"
    createdAt: Optional[str] = None


@dataclass
class GraphDocument:
    """Complete graph document with all data."""
    version: str = "1.0"
    meta: GraphMeta = field(default_factory=GraphMeta)
    nodes: Dict[str, NodeData] = field(default_factory=dict)
    settings: GraphSettings = field(default_factory=GraphSettings)


# -----------------------------
# Graph Model
# -----------------------------

class GraphModel(QObject):
    """
    Main graph data model with query and mutation methods.
    
    Signals:
        changed: Emitted when graph data changes
        node_selected: Emitted when a node is selected (passes node_id)
    """
    changed = Signal()
    node_selected = Signal(str)

    def __init__(self):
        super().__init__()
        self.doc = GraphDocument()

    # ---------- Query helpers ----------
    def children_of(self, node_id: str) -> List[str]:
        """Get all direct children of a node."""
        return [n.id for n in self.doc.nodes.values() if n.parentId == node_id]

    def ancestors_of(self, node_id: str) -> Set[str]:
        """Get all ancestors (parents, grandparents, etc.) of a node."""
        res: Set[str] = set()
        cur = self.doc.nodes.get(node_id)
        while cur and cur.parentId:
            res.add(cur.parentId)
            cur = self.doc.nodes.get(cur.parentId)
        return res

    def descendants_of(self, node_id: str) -> Set[str]:
        """Get all descendants (children, grandchildren, etc.) of a node."""
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
        """Check if reparenting would maintain acyclic property."""
        if new_parent_id is None:
            return True
        if child_id == new_parent_id:
            return False
        # New parent must NOT be a descendant of child
        return new_parent_id not in self.descendants_of(child_id)

    # ---------- Mutations ----------
    def add_node(self, label: str = "Node", parent_id: Optional[str] = None, 
                 pos: QPointF = QPointF(0, 0)) -> NodeData:
        """Add a new node to the graph."""
        new_id = gen_id()
        n = NodeData(id=new_id, label=label, parentId=parent_id)
        n.layout.x = pos.x()
        n.layout.y = pos.y()
        
        # Default shape: if PM mode is enabled, create a projektnode
        if self.doc.settings.pm.enabled:
            n.attrs.shape = "projektnode"
            n.pm = PMData(name=label, number=None, duration=1)
        
        # Fallback guard for invalid shapes
        if n.attrs.shape not in SHAPES:
            n.attrs.shape = "circle"
            
        self.doc.nodes[new_id] = n
        log.info("add_node id=%s parent=%s pos=(%.1f,%.1f)", new_id, parent_id, n.layout.x, n.layout.y)
        self.changed.emit()
        return n

    def delete_node(self, node_id: str):
        """Delete a node and reattach its children to its parent."""
        node = self.doc.nodes.get(node_id)
        if not node:
            return
        parent_id = node.parentId
        
        # Reattach children to parent (or become roots if no parent)
        for cid in self.children_of(node_id):
            child = self.doc.nodes[cid]
            child.parentId = parent_id
            
        # Remove PM dependencies that reference the deleted node
        for n in self.doc.nodes.values():
            if getattr(n, 'pmDeps', None):
                n.pmDeps = [d for d in n.pmDeps if d.predId != node_id]
                
        del self.doc.nodes[node_id]
        log.info("delete_node id=%s (children -> %s)", node_id, parent_id)
        self.changed.emit()

    def reparent_variant_a(self, child_id: str, new_parent_id: Optional[str]):
        """
        Reparent a node using Variant A strategy.
        
        Child and its current children are moved to the new parent.
        """
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
        
        # Set child's new parent
        child.parentId = new_parent_id
        
        # Move all previous children to new_parent as well
        for cid in current_children:
            self.doc.nodes[cid].parentId = new_parent_id
            
        log.info("reparent variant A: %s -> parent %s; moved %d children", 
                 child_id, new_parent_id, len(current_children))
        self.changed.emit()

    def set_node_attrs(self, node_id: str, *, label: Optional[str] = None, 
                       color: Optional[str] = None, inherit: Optional[bool] = None, 
                       shape: Optional[str] = None, data: Optional[Dict[str, str]] = None,
                       pm: Optional[dict] = None):
        """Update node attributes."""
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
            # Apply only known keys
            if "number" in pm:
                n.pm.number = str(pm.get("number") if pm.get("number") is not None else "")
            if "name" in pm:
                n.pm.name = str(pm.get("name") if pm.get("name") is not None else "")
            if "duration" in pm:
                try:
                    n.pm.duration = int(pm.get("duration", n.pm.duration))
                except Exception:
                    pass
            # Computed fields may be set by CPM engine later
            for k in ("FAZ", "FEZ", "SAZ", "SEZ", "GP", "FP"):
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
        """Move multiple nodes to new positions."""
        for nid, (x, y) in positions.items():
            n = self.doc.nodes.get(nid)
            if n:
                n.layout.x = x
                n.layout.y = y
        log.info("move_nodes %d", len(positions))
        self.changed.emit()

    # ---------- PM Dependencies ----------
    def add_pm_dep(self, pred_id: str, succ_id: str, dep_type: str = "FS", lag: int = 0) -> bool:
        """Add a PM dependency between two nodes."""
        if pred_id not in self.doc.nodes or succ_id not in self.doc.nodes:
            return False
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
            
        # Avoid duplicates
        for d in succ.pmDeps:
            if d.predId == pred_id and d.type == dep_type and d.lag == lag:
                return False
                
        # Cycle check
        if self._pm_creates_cycle(pred_id, succ_id):
            return False
            
        succ.pmDeps.append(PMDep(predId=pred_id, type=dep_type, lag=lag))
        self.changed.emit()
        return True

    def remove_pm_dep(self, succ_id: str, pred_id: str, 
                      dep_type: Optional[str] = None, lag: Optional[int] = None):
        """Remove a PM dependency."""
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

    def _pm_creates_cycle(self, pred_id: str, succ_id: str) -> bool:
        """Check if adding a dependency would create a cycle."""
        return self._pm_reaches(succ_id, pred_id)

    def _pm_reaches(self, src_id: str, dst_id: str) -> bool:
        """Check if there's a path from src to dst through PM dependencies."""
        seen: Set[str] = set()
        stack: List[str] = [src_id]
        while stack:
            u = stack.pop()
            if u == dst_id:
                return True
            if u in seen:
                continue
            seen.add(u)
            # Find all nodes where u appears as predId
            for nid, n in self.doc.nodes.items():
                for d in getattr(n, 'pmDeps', []) or []:
                    if d.predId == u:
                        stack.append(nid)
        return False

    # ---------- CPM Engine ----------
    def compute_cpm(self) -> Tuple[bool, Optional[str]]:
        """
        Compute Critical Path Method for all project nodes.
        
        Returns:
            Tuple of (success, error_message)
        """
        nodes = self.doc.nodes
        tasks: List[str] = []
        
        for nid, n in nodes.items():
            if n.attrs.shape == "projektnode" and n.pm is None:
                n.pm = PMData(name=n.label, duration=1)
            has_children = len(self.children_of(nid)) > 0
            if n.pm and not (n.pm.isSummary or has_children):
                tasks.append(nid)

        # Build adjacency with weights
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

        # Topological order (Kahn's algorithm)
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
            return False, "Cycle detected in PM dependencies"

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
            
        # Free float calculation
        for i in tasks:
            cands: List[int] = []
            for j in tasks:
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

    # ---------- Color Helpers ----------
    def _qcolor_from_hex(self, hx: Optional[str], default: QColor = QColor(120, 170, 255)) -> QColor:
        """Convert hex string to QColor."""
        if hx:
            c = QColor(hx)
            if c.isValid():
                return c
        return default

    def effective_color(self, node_id: str, _visited: Optional[Set[str]] = None) -> QColor:
        """Get the effective display color for a node (with inheritance)."""
        node = self.doc.nodes.get(node_id)
        if not node:
            return QColor(200, 200, 200)
            
        st = self.doc.settings.styling
        
        # Direct color override
        if node.attrs.color:
            return self._qcolor_from_hex(node.attrs.color)
            
        # Inheritance disabled or no valid parent
        parent_id = node.parentId
        if (not st.enableColorInheritance
                or not node.attrs.inheritColor
                or not parent_id
                or parent_id not in self.doc.nodes
                or not self.doc.settings.validation.enforceAcyclic):
            return QColor(120, 170, 255)
            
        # Guard against cycles during inheritance
        if _visited is None:
            _visited = set()
        if node_id in _visited:
            return QColor(120, 170, 255)
        _visited.add(node_id)
        
        # Inherit from parent chain
        base = self.effective_color(parent_id, _visited)
        
        # Apply gradient by depth
        h, s, l, a = base.getHsl()
        s = max(0, min(255, int(s + (st.inheritanceSaturationStep / 100.0) * 255)))
        l = max(0, min(255, int(l + (st.inheritanceLuminanceStep / 100.0) * 255)))
        res = QColor()
        res.setHsl(h, s, l, a)
        return res

    # ---------- Serialization ----------
    def to_json(self) -> dict:
        """Serialize the graph to a JSON-compatible dict."""
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

        return {
            "version": self.doc.version,
            "meta": asdict(self.doc.meta),
            "settings": asdict(self.doc.settings),
            "nodes": [node_to_dict(n) for n in self.doc.nodes.values()],
        }

    def from_json(self, data: dict):
        """Load graph from a JSON-compatible dict."""
        try:
            self.doc = GraphDocument()
            self.doc.version = data.get("version", "1.0")
            meta = data.get("meta", {})
            self.doc.meta = GraphMeta(title=meta.get("title", "My Graph"), createdAt=meta.get("createdAt"))
            
            # Settings
            s = data.get("settings", {})
            self.doc.settings = GraphSettings(
                validation=SettingsValidation(**s.get("validation", {})),
                history=SettingsHistory(**s.get("history", {})),
                ui=SettingsUI(**s.get("ui", {})),
                styling=SettingsStyling(**s.get("styling", {})),
                edges=SettingsEdges(**(s.get("edges", {}) if isinstance(s.get("edges", {}), dict) else {})),
                pm=SettingsPM(**(s.get("pm", {}) if isinstance(s.get("pm", {}), dict) else {})),
            )
            
            # Nodes
            self.doc.nodes.clear()
            for nd in data.get("nodes", []):
                nid = nd.get("id")
                if not nid:
                    continue
                    
                # parentId compatibility
                parent_id = nd.get("parentId")
                if parent_id is None:
                    pids = nd.get("parentIds")
                    if isinstance(pids, list) and pids:
                        parent_id = pids[0]
                        
                # Attrs
                a_raw = nd.get("attrs", {}) or {}
                if not isinstance(a_raw, dict):
                    a_raw = {}
                color = a_raw.get("color")
                inherit = a_raw.get("inheritColor", True)
                shape = a_raw.get("shape", "circle")
                data_field = a_raw.get("data", {})
                if not isinstance(data_field, dict):
                    data_field = {"value": str(data_field)}
                attrs = NodeAttrs(color=color, inheritColor=bool(inherit), shape=shape, data=data_field)
                
                # Layout
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
                
                node = NodeData(id=nid, label=nd.get("label", "Node"), parentId=parent_id, 
                               attrs=attrs, layout=layout)
                               
                # PM data
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
            raise ValueError(f"Error loading graph: {e}")
