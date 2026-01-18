"""
Graphics items for DAG Graph Editor.

Contains NodeItem and EdgeItem classes for visual representation of the graph.
"""

from __future__ import annotations

import math
from typing import Dict, Optional, Set, TYPE_CHECKING

from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPainterPath, QPen, QPolygonF
from PySide6.QtWidgets import QGraphicsItem, QGraphicsPathItem, QGraphicsTextItem, QMenu, QMessageBox

from .constants import NODE_W, NODE_H
from .model import GraphModel, PMData

if TYPE_CHECKING:
    from .views import GraphView
    from .commands import AddPMDepCommand


class EdgeItem(QGraphicsPathItem):
    """Visual representation of an edge between nodes."""
    
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
        
        # Label for PM edges
        self.text_item = QGraphicsTextItem("", self)
        self.text_item.setDefaultTextColor(QColor(90, 90, 90))
        self.text_item.setFont(QFont("Arial", 8))
        self.update_path()

    def update_path(self):
        """Update the edge path based on current node positions."""
        s = self.src.connection_pos_out()
        d = self.dst.connection_pos_in()
        path = QPainterPath(s)
        dx = (d.x() - s.x()) * 0.5
        c1 = QPointF(s.x() + dx, s.y())
        c2 = QPointF(d.x() - dx, d.y())
        path.cubicTo(c1, c2, d)
        self.setPath(path)
        self.setPen(self.pen_normal)
        
        # Place label at midpoint for PM edges
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
            # Draw arrow at target
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
            
        m = QMenu()
        act_edit = m.addAction("Edit PM Link...")
        act_del = m.addAction("Delete PM Link")
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
    """Visual representation of a node in the graph."""
    
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
        self._orig_positions: Dict[str, QPointF] = {}

    def connection_pos_in(self) -> QPointF:
        """Get the connection point for incoming edges."""
        return self.mapToScene(QPointF(0, -NODE_H / 2))

    def connection_pos_out(self) -> QPointF:
        """Get the connection point for outgoing edges."""
        return self.mapToScene(QPointF(0, NODE_H / 2))

    def boundingRect(self) -> QRectF:
        return self.rect.adjusted(-8, -8, 8, 8)

    def shape(self) -> QPainterPath:
        return self._shape_path()

    def _shape_path(self) -> QPainterPath:
        """Get the shape path based on node type."""
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
            # Header: number + name
            header = ""
            if n.pm:
                if n.pm.number:
                    header = f"{n.pm.number} — {n.pm.name or n.label}"
                else:
                    header = n.pm.name or n.label
            else:
                header = n.label
                
            # PM data rows
            faz = n.pm.FAZ if n.pm else 0
            fez = n.pm.FEZ if n.pm else (faz + (n.pm.duration if n.pm else 1))
            saz = n.pm.SAZ if n.pm else 0
            sez = n.pm.SEZ if n.pm else saz + (n.pm.duration if n.pm else 1)
            dval = n.pm.duration if n.pm else 1
            gp = n.pm.GP if n.pm else 0
            fp = n.pm.FP if n.pm else 0
            row1 = f"ES {faz} | d {dval} | EF {fez}"
            if self.model.doc.settings.pm.showBuffers:
                row2 = f"LS {saz} | TF {gp}/FF {fp} | LF {sez}"
            else:
                row2 = f"LS {saz} | LF {sez}"
                
            # Draw lines
            header_rect = QRectF(br.left()+6, br.top()+4, br.width()-12, br.height()/3)
            row1_rect = QRectF(br.left()+6, br.top()+22, br.width()-12, br.height()/3)
            row2_rect = QRectF(br.left()+6, br.top()+40, br.width()-12, br.height()/3)
            painter.drawText(header_rect, Qt.AlignLeft | Qt.TextSingleLine, header)
            painter.drawText(row1_rect, Qt.AlignLeft | Qt.TextSingleLine, row1)
            painter.drawText(row2_rect, Qt.AlignLeft | Qt.TextSingleLine, row2)
        else:
            # Default: simple center label
            painter.drawText(br, Qt.AlignCenter | Qt.TextWordWrap, n.label)

    def mousePressEvent(self, event):
        if event.button() == Qt.RightButton:
            try:
                sp = event.screenPos()
            except Exception:
                sp = event.scenePos()
            self._show_context_menu(sp)
            event.accept()
            return
            
        # PM link mode handling
        if event.button() == Qt.LeftButton:
            try:
                win = self.scene().views()[0].window
            except Exception:
                win = None
            if win is not None and getattr(win, "_pm_link_mode", False):
                if not getattr(win, "_pm_link_src", None):
                    win._pm_link_src = self.node_id
                    win.statusBar().showMessage("PM-Link: Source selected. Click target...")
                    event.accept()
                    return
                else:
                    src = win._pm_link_src
                    dst = self.node_id
                    if src == dst:
                        QMessageBox.information(win, "PM-Link", "Source and target cannot be the same.")
                        win.end_pm_link_mode()
                        event.accept()
                        return
                    res = win._prompt_pm_link()
                    if res is None:
                        win.end_pm_link_mode()
                        event.accept()
                        return
                    dep_type, lag = res
                    from .commands import AddPMDepCommand
                    cmd = AddPMDepCommand(self.model, src, dst, dep_type, lag, self.scene().views()[0])
                    self.scene().views()[0].undo_stack.push(cmd)
                    win.end_pm_link_mode()
                    event.accept()
                    return
                    
        if event.button() == Qt.LeftButton and (event.modifiers() & Qt.ShiftModifier):
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
            self.scene().views()[0].update_all_edges()
            event.accept()
            return
        super().mouseMoveEvent(event)
        self.scene().views()[0].update_all_edges()

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        view = self.scene().views()[0]
        new_positions = {}
        if self._moving_with_children:
            for nid in self._orig_positions:
                item = view.item_for_node(nid)
                if item:
                    new_positions[nid] = item.pos()
        else:
            new_positions[self.node_id] = self.pos()
        if new_positions:
            view.push_move_command(self._orig_positions, new_positions)

    def _show_context_menu(self, screen_pos):
        m = QMenu()
        act_edit = m.addAction("Edit...")
        act_del = m.addAction("Delete")
        m.addSeparator()
        act_reparent = m.addAction("Start Re-Parent")
        act = m.exec(screen_pos)
        if act == act_edit:
            self.scene().views()[0].window.info_panel.edit_node(self.node_id)
        elif act == act_del:
            self.scene().views()[0].window.delete_node(self.node_id)
        elif act == act_reparent:
            self.scene().views()[0].window.begin_reparent_mode()
