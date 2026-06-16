from typing import Any
from PySide6.QtCore import Qt, Signal, QRectF, QPointF
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QBrush, QTransform
from PySide6.QtWidgets import (
    QGraphicsView,
    QGraphicsScene,
    QGraphicsItem,
    QGraphicsRectItem,
    QGraphicsTextItem,
    QWidget,
)

MM_TO_PX = 3.7795  # 96 DPI approx

class GraphicElement(QGraphicsItem):
    """Elemento gráfico base para el lienzo de diseño."""
    
    def __init__(self, data: dict[str, Any]):
        super().__init__()
        self._data = data
        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
            | QGraphicsItem.GraphicsItemFlag.ItemIsMovable
            | QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges
        )
        self.setAcceptHoverEvents(True)
        self._rect = QRectF(0, 0, 100, 50)
        self._update_from_data()

    def get_data(self) -> dict[str, Any]:
        """Devuelve el dict JSON actualizado de este elemento."""
        # Sincronizar posición actual (convertir px a mm)
        self._data["x"] = self.pos().x() / MM_TO_PX
        self._data["y"] = self.pos().y() / MM_TO_PX
        self._data["width"] = self._rect.width() / MM_TO_PX
        self._data["height"] = self._rect.height() / MM_TO_PX
        return self._data

    def data_dict(self) -> dict[str, Any]:
        """Alias de get_data() para uso de consulta sin sync de posición."""
        return self._data

    def set_data(self, data: dict[str, Any]) -> None:
        """Actualiza el elemento desde un dict modificado externamente."""
        self._data = data
        self._update_from_data()

    def _update_from_data(self) -> None:
        """Aplica las propiedades de self._data al QGraphicsItem."""
        x = self._data.get("x", 0) * MM_TO_PX
        y = self._data.get("y", 0) * MM_TO_PX
        w = self._data.get("width", 30) * MM_TO_PX
        h = self._data.get("height", 10) * MM_TO_PX

        self.setPos(x, y)
        self._rect = QRectF(0, 0, w, h)
        
        self.setZValue(self._data.get("z_order", 1))
        self.update()

    def boundingRect(self) -> QRectF:
        return self._rect

    def paint(self, painter: QPainter, option, widget=None) -> None:
        # Dibujar borde de selección si está seleccionado
        if self.isSelected():
            pen = QPen(QColor("#3B82F6"), 2, Qt.PenStyle.DashLine)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(self._rect)

        # Delegar dibujo al tipo específico
        elem_type = self._data.get("type", "shape")
        props = self._data.get("properties", {})

        if elem_type == "base_image":
            self._paint_base_image(painter, props)
        elif elem_type == "text" or elem_type == "composite":
            render_as = props.get("render_as", "Texto")
            if render_as == "Código QR":
                self._paint_image(painter, props, f"📱 QR\n[{self._data.get('campo_dato', '')}]")
            elif render_as == "Código de Barras":
                self._paint_image(painter, props, f"▊██▊ Barras\n[{self._data.get('campo_dato', '')}]")
            else:
                self._paint_text(painter, props)
        elif elem_type == "image" or elem_type == "photo_path":
            campo = self._data.get('campo_dato', 'foto')
            self._paint_image(painter, props, f"📷 {campo}")
        elif elem_type == "qr" or elem_type == "barcode":
            self._paint_image(painter, props, "📱 Código")
        elif elem_type == "shape":
            self._paint_shape(painter, props)
        elif elem_type == "background":
            self._paint_shape(painter, props, is_bg=True)

    def _paint_text(self, painter: QPainter, props: dict) -> None:
        font_family = props.get("font_family", "Inter")
        font_size = props.get("font_size", 12)
        elem_type = self._data.get("type", "text")

        campo = self._data.get("campo_dato", "")
        test_text = props.get("test_text", "")

        if test_text:
            # Si hay dato de prueba, mostrarlo con el color real
            color = QColor(props.get("color", "#171A2B"))
            texto = test_text
        elif elem_type == "composite":
            # Texto compuesto: mostrar la plantilla o una muestra
            tmpl = props.get("composite_template", "")
            color = QColor("#1D4ED8")   # azul
            texto = tmpl if tmpl else f"\u2194 Texto Compuesto"
        else:
            # Atributo normal: mostrar nombre del campo con color descriptivo
            color = QColor("#64748B")   # gris
            texto = campo if campo else "Atributo"

        font = QFont(font_family)
        size_mm = font_size * 0.352778
        size_px = int(size_mm * MM_TO_PX)
        if size_px > 0:
            font.setPixelSize(size_px)
        else:
            font.setPointSize(font_size)

        # Fondo suave semi-transparente para que sea legible
        if not test_text:
            bg = QColor("#EFF6FF") if elem_type == "composite" else QColor("#F8FAFC")
            painter.setBrush(QBrush(bg))
            painter.setPen(QPen(QColor("#CBD5E1"), 1, Qt.PenStyle.DashLine))
            painter.drawRoundedRect(self._rect, 3, 3)

        painter.setFont(font)
        painter.setPen(QPen(color))
        painter.drawText(self._rect, Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap, texto)

    def _paint_image(self, painter: QPainter, props: dict, label: str) -> None:
        painter.setPen(QPen(QColor("#94A3B8"), 1, Qt.PenStyle.SolidLine))
        painter.setBrush(QColor("#F1F5F9"))
        painter.drawRect(self._rect)
        
        painter.setPen(QColor("#64748B"))
        painter.setFont(QFont("Inter", 10))
        
        if self._data.get("type") == "image":
            img_src = props.get("image_source", "Estudiante")
            label = f"🖼️ {img_src}"
        elif self._data.get("type") == "photo_path":
            label = f"📷 {self._data.get('label', 'Foto')}"
        elif self._data.get("type") == "qr":
            qr_type = props.get("qr_type", "Atributo Simple")
            if qr_type == "Texto Compuesto":
                label = "📱 QR\n(Compuesto)"
            else:
                label = f"📱 QR\n[{self._data.get('campo_dato', 'token')}]"
        elif self._data.get("type") == "barcode":
            label = f"▮▮▮ Código\n[{self._data.get('campo_dato', 'token')}]"
                
        painter.drawText(self._rect, Qt.AlignmentFlag.AlignCenter, label)

    def _paint_base_image(self, painter: QPainter, props: dict) -> None:
        """Renderiza la imagen base (plantilla de fondo) ocupando todo el lienzo."""
        from pathlib import Path
        from PySide6.QtGui import QPixmap

        src = props.get("src", "")
        if src and Path(src).exists():
            pixmap = QPixmap(src)
            if not pixmap.isNull():
                painter.drawPixmap(self._rect.toRect(), pixmap)
                return

        # Fallback: fondo gris suave con texto indicativo
        painter.setBrush(QBrush(QColor("#F1F5F9")))
        painter.setPen(QPen(QColor("#CBD5E1"), 1, Qt.PenStyle.DashLine))
        painter.drawRect(self._rect)
        painter.setPen(QColor("#94A3B8"))
        painter.setFont(QFont("Inter", 10))
        painter.drawText(self._rect, Qt.AlignmentFlag.AlignCenter, "🖼 Imagen base no encontrada")

    def _paint_shape(self, painter: QPainter, props: dict, is_bg: bool = False) -> None:
        color = QColor(props.get("color", "#E2E8F0"))
        painter.setPen(Qt.PenStyle.NoPen if is_bg else QPen(color.darker(), 1))
        painter.setBrush(QBrush(color))
        painter.drawRect(self._rect)


    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange and self.scene():
            # Limitar al scene rect
            rect = self.scene().sceneRect()
            new_pos = value
            if not rect.contains(new_pos):
                new_pos.setX(min(rect.right() - self._rect.width(), max(new_pos.x(), rect.left())))
                new_pos.setY(min(rect.bottom() - self._rect.height(), max(new_pos.y(), rect.top())))
                return new_pos
        return super().itemChange(change, value)


class CredentialScene(QGraphicsScene):
    """Escena que maneja el drag & drop y eventos del lienzo."""
    
    item_updated = Signal(object) # dict del elemento

    def __init__(self, parent=None):
        super().__init__(parent)

    def set_physical_size(self, width_cm: float, height_cm: float):
        """Ajusta el tamaño del lienzo basado en cm."""
        w_px = width_cm * 10 * MM_TO_PX
        h_px = height_cm * 10 * MM_TO_PX
        self.setSceneRect(0, 0, w_px, h_px)
        
    def dragEnterEvent(self, event):
        if event.mimeData().hasText():
            event.acceptProposedAction()
            
    def dragMoveEvent(self, event):
        if event.mimeData().hasText():
            event.acceptProposedAction()

    def dropEvent(self, event):
        text = event.mimeData().text()
        pos = event.scenePos()

        # El formato del drag_data es "tipo:campo_dato"
        # Ejemplos: "text:apellido", "photo_path:photo_url", "composite:composite"
        elem_type = "text"
        campo_dato = None

        if ":" in text:
            prefix, campo = text.split(":", 1)
            if prefix in ("text", "photo_path", "composite", "qr", "barcode", "image", "background"):
                elem_type = prefix
                campo_dato = campo if campo else None
            elif prefix == "tool":
                elem_type = campo
            elif prefix == "attr":
                # formato legacy "attr:campo"
                elem_type = "text"
                campo_dato = campo
        else:
            elem_type = text

        # Crear nuevo elemento
        data = {
            "type": elem_type,
            "x": pos.x() / MM_TO_PX,
            "y": pos.y() / MM_TO_PX,
            "width": 85 if elem_type == "background" else 30,
            "height": 54 if elem_type == "background" else 10,
            "z_order": 0 if elem_type == "background" else len(self.items()) + 1,
            "campo_dato": campo_dato,
            "properties": {
                "font_family": "Inter",
                "font_size": 12,
                "color": "#171A2B"
            }
        }

        if elem_type == "qr":
            data["width"] = 20
            data["height"] = 20
        elif elem_type in ("image", "photo_path"):
            data["width"] = 25
            data["height"] = 30

        item = GraphicElement(data)
        self.addItem(item)
        self.clearSelection()
        item.setSelected(True)

        event.acceptProposedAction()
        
        # Notificar nuevo item
        self.item_updated.emit(item.get_data())


class CredentialView(QGraphicsView):
    """Vista con zoom interactivo para el diseño de la credencial."""
    
    def __init__(self, scene: CredentialScene, parent: QWidget | None = None):
        super().__init__(scene, parent)
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.FullViewportUpdate)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setAcceptDrops(True)
        self.setStyleSheet("background: transparent; border: none;")

        # Dibujar sombra paralela del lienzo
        self.setObjectName("credentialView")

    def drawBackground(self, painter: QPainter, rect: QRectF):
        # Dibujar fondo blanco del lienzo
        scene_rect = self.sceneRect()
        painter.fillRect(scene_rect, QColor("#FFFFFF"))
        
        # Dibujar borde fino
        painter.setPen(QColor("#CBD5E1"))
        painter.drawRect(scene_rect)

    def set_zoom(self, level_percent: int):
        self.resetTransform()
        scale = level_percent / 100.0
        self.scale(scale, scale)
