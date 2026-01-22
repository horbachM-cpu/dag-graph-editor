"""
View components for DAG Graph Editor.

Contains GraphScene, GraphView, and MiniMap classes.
"""

from __future__ import annotations

from typing import Dict, List, Optional, TYPE_CHECKING

from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import QBrush, QColor, QPainter, QPen, QPixmap, QUndoStack
from PySide6.QtWidgets import QGraphicsScene, QGraphicsView

from .model import GraphModel
from .items import NodeItem, EdgeItem
from .commands import MoveNodesCommand

if TYPE_CHECKING:
    from .main import MainWindow


class GraphScene(QGraphicsScene):
    """Graphics scene for the graph."""
    
    def __init__(self, model: GraphModel):
        super().__init__()
        self.model = model


class GraphView(QGraphicsView):
    """Main graph view with editing capabilities."""
    
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
        """Initialize canvas with dark theme and subtle grid pattern."""
        # Create a dark background with subtle grid
        from PySide6.QtGui import QPixmap, QPainter
        
        # Dark background color
        bg_color = QColor(30, 30, 46)  # Catppuccin base
        grid_color = QColor(49, 50, 68, 80)  # Catppuccin surface0 with alpha
        
        # Create tiled grid pattern
        grid_size = 20
        pixmap = QPixmap(grid_size, grid_size)
        pixmap.fill(bg_color)
        
        painter = QPainter(pixmap)
        painter.setPen(QPen(grid_color, 1))
        # Draw grid lines
        painter.drawLine(0, 0, grid_size, 0)
        painter.drawLine(0, 0, 0, grid_size)
        painter.end()
        
        self.setBackgroundBrush(QBrush(pixmap))

    def item_for_node(self, node_id: str) -> Optional[NodeItem]:
        """Get the NodeItem for a node ID."""
        return self.items_by_id.get(node_id)

    def sync_items_from_model(self):
        """Synchronize visual items with the model."""
        # Remove missing items
        for nid in list(self.items_by_id.keys()):
            if nid not in self.model.doc.nodes:
                self.scene_.removeItem(self.items_by_id[nid])
                del self.items_by_id[nid]
                
        # Add/update items
        for nid, n in self.model.doc.nodes.items():
            item = self.items_by_id.get(nid)
            if not item:
                item = NodeItem(self.model, nid)
                self.scene_.addItem(item)
                self.items_by_id[nid] = item
            item.setPos(QPointF(n.layout.x, n.layout.y))
            
        self._rebuild_edges()
        self.scene_.update()
        
        # Keep minimap in sync
        try:
            self.window._update_minimap_fit()
        except Exception:
            pass

    def _rebuild_edges(self):
        """Rebuild all edge items."""
        for e in self.edges:
            self.scene_.removeItem(e)
        self.edges.clear()
        
        deco = self.model.doc.settings.edges.decorationsEnabled
        
        # Parent-child edges
        for nid, n in self.model.doc.nodes.items():
            if n.parentId and n.parentId in self.items_by_id:
                e = EdgeItem(self.items_by_id[n.parentId], self.items_by_id[nid], decorations=deco)
                self.scene_.addItem(e)
                self.edges.append(e)
                
        # PM dependency edges (only in PM mode)
        if self.model.doc.settings.pm.enabled:
            for nid, n in self.model.doc.nodes.items():
                if not n.pmDeps:
                    continue
                for d in n.pmDeps:
                    src_id = d.predId
                    dst_id = nid
                    if src_id in self.items_by_id and dst_id in self.items_by_id:
                        e = EdgeItem(
                            self.items_by_id[src_id], self.items_by_id[dst_id], 
                            decorations=deco, is_pm=True, pm_type=d.type, 
                            pm_lag=int(getattr(d, 'lag', 0)),
                            pred_id=src_id, succ_id=dst_id
                        )
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
        """Update all edge paths."""
        for e in self.edges:
            e.update_path()

    def zoom_in(self):
        """Zoom in by 15%."""
        self.scale(1.15, 1.15)

    def zoom_out(self):
        """Zoom out by 13%."""
        self.scale(0.87, 0.87)

    def fit_to_view(self):
        """Fit all items into the view."""
        items = self.items()
        if not items:
            return
        rect = self.scene_.itemsBoundingRect()
        if rect.isNull():
            return
        self.fitInView(rect.adjusted(-40, -40, 40, 40), Qt.KeepAspectRatio)

    def export_png(self, path: str):
        """Export the scene to a PNG file."""
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

    def push_move_command(self, old: Dict[str, QPointF], new: Dict[str, QPointF]):
        """Push a move command to the undo stack."""
        cmd = MoveNodesCommand(self.model, old, new, self)
        self.undo_stack.push(cmd)

    def wheelEvent(self, event):
        if event.modifiers() & Qt.ControlModifier:
            super().wheelEvent(event)
            return
        delta = event.angleDelta().y()
        if delta > 0:
            self.zoom_in()
        else:
            self.zoom_out()


class MiniMap(QGraphicsView):
    """Minimap view for graph overview."""
    
    def __init__(self, main_view: GraphView):
        super().__init__(main_view.scene())
        self.main_view = main_view
        self.setRenderHint(QPainter.Antialiasing, False)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setInteractive(False)
        # Dark theme styling
        self.setStyleSheet("""
            background: rgba(24, 24, 37, 240);
            border: 2px solid #45475a;
            border-radius: 8px;
        """)
        self.setFixedSize(200, 150)
        
        try:
            self.scene().changed.connect(self._on_scene_changed)
        except Exception:
            pass

    def _on_scene_changed(self, *_):
        self.fit_to_scene()

    def fit_to_scene(self):
        """Fit the minimap to show all scene content."""
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
        """Center the main view on a scene point."""
        self.main_view.centerOn(scene_point)

    def drawForeground(self, painter: QPainter, rect):
        """Draw the main view's visible rect as an overlay."""
        try:
            vis = self.main_view.mapToScene(self.main_view.viewport().rect()).boundingRect()
            pen = QPen(QColor(200, 0, 0))
            pen.setWidth(2)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(vis)
        except Exception:
            pass
