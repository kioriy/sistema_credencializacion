"""
Motor de renderizado PDF para credenciales.

Genera archivos PDF con ReportLab, colocando múltiples credenciales
por página según la configuración de la plantilla. Soporta textos,
imágenes, códigos QR, fondos y formas geométricas.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

from reportlab.lib.pagesizes import letter, A4
from reportlab.lib.units import cm as RL_CM, mm as RL_MM
from reportlab.lib.colors import HexColor, Color
from reportlab.pdfgen.canvas import Canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.graphics import renderPDF
from reportlab.graphics.shapes import Drawing
from reportlab.graphics.barcode import createBarcodeDrawing

from credencializacion.renderer.coordinates import (
    cm_to_points,
    mm_to_points,
    calculate_card_positions_from_config,
    final_coordinate,
)
from credencializacion.renderer.rotation import (
    should_rotate,
    apply_rotation,
    restore_rotation,
    get_rotated_dimensions,
)

if TYPE_CHECKING:
    from credencializacion.db.models import Plantilla, Registro

logger = logging.getLogger(__name__)

# Mapeo de nombres de página a tamaños de ReportLab
PAGE_SIZES = {
    "letter": letter,
    "a4": A4,
    "custom_297_320": (297 * RL_MM, 320 * RL_MM),
}

# Fuentes ya registradas (evitar duplicados)
_registered_fonts: set[str] = set()


def _register_font(font_name: str, font_path: Path | None = None) -> str:
    """Registra una fuente TTF en ReportLab si aún no está registrada.

    Args:
        font_name: Nombre lógico de la fuente (e.g., 'Inter').
        font_path: Ruta al archivo .ttf. Si es None, usa el nombre como fallback.

    Returns:
        El nombre registrado de la fuente para uso en drawString.
    """
    if font_name in _registered_fonts:
        return font_name

    if font_path and font_path.exists():
        try:
            pdfmetrics.registerFont(TTFont(font_name, str(font_path)))
            _registered_fonts.add(font_name)
            return font_name
        except Exception as e:
            logger.warning("No se pudo registrar fuente '%s': %s", font_name, e)

    # Fallback a fuente estándar de ReportLab
    return "Helvetica"


def _hex_to_color(hex_color: str) -> Color:
    """Convierte color hexadecimal a objeto Color de ReportLab."""
    try:
        return HexColor(hex_color)
    except Exception:
        return HexColor("#000000")


class PDFEngine:
    """Motor de generación de PDFs para impresión de credenciales.

    Toma una plantilla y genera un PDF con N registros, distribuyendo
    las credenciales en las posiciones definidas por la plantilla.

    Args:
        plantilla: Modelo Plantilla con la definición del diseño.
    """

    def __init__(self, plantilla: "Plantilla") -> None:
        self.plantilla = plantilla
        
        from credencializacion.core.settings import AppSettings
        from credencializacion.renderer.coordinates import mm_to_points
        w_mm, h_mm = AppSettings.get_page_dimensions()
        self._page_size = (mm_to_points(w_mm), mm_to_points(h_mm))
        self._cards_per_page = (plantilla.posiciones_hoja or {}).get(
            "cards_per_page", 2
        )
        self._card_positions = calculate_card_positions_from_config(
            self._page_size,
            plantilla.posiciones_hoja or {},
        )
        self._rotate = should_rotate(plantilla)

    def render(
        self,
        registros: list["Registro"],
        cara: str,
        output_path: Path,
    ) -> Path:
        """Genera el PDF con las credenciales de los registros dados.

        Args:
            registros: Lista de registros a imprimir.
            cara: 'frente' o 'vuelta'.
            output_path: Ruta donde se guardará el PDF.

        Returns:
            La ruta al PDF generado.
        """
        output_path.parent.mkdir(parents=True, exist_ok=True)
        c = Canvas(str(output_path), pagesize=self._page_size)

        elementos = (
            self.plantilla.elementos_frente
            if cara == "frente"
            else self.plantilla.elementos_vuelta
        )

        # Imagen base para esta cara
        recursos = self.plantilla.recursos or {}
        base_key = "fondo_frente" if cara == "frente" else "fondo_vuelta"
        self._current_base_img = recursos.get(base_key, "")
        self._current_cara = cara

        # Agrupar registros por página
        for page_idx in range(0, len(registros), self._cards_per_page):
            page_records = registros[page_idx : page_idx + self._cards_per_page]

            for slot_idx, registro in enumerate(page_records):
                if slot_idx >= len(self._card_positions):
                    break
                base_pos = self._card_positions[slot_idx]
                self._render_card(c, registro, elementos, base_pos)

            c.showPage()

        c.save()
        logger.info("PDF generado: %s (%d registros)", output_path, len(registros))
        return output_path

    def render_both(
        self,
        registros: list["Registro"],
        output_path: Path,
    ) -> Path:
        """Genera un PDF de 2 páginas: frentes en pág.1, vueltas en pág.2.

        Página 1: frente del registro 1 en slot 1, frente del registro 2 en slot 2.
        Página 2: vuelta del registro 1 en slot 1, vuelta del registro 2 en slot 2.

        Args:
            registros: Lista de hasta 2 registros a imprimir.
            output_path: Ruta donde se guardará el PDF.

        Returns:
            La ruta al PDF generado.
        """
        output_path.parent.mkdir(parents=True, exist_ok=True)
        c = Canvas(str(output_path), pagesize=self._page_size)
        recursos = self.plantilla.recursos or {}

        # Página 1: frentes
        self._current_cara = "frente"
        self._current_base_img = recursos.get("fondo_frente", "")
        elems_frente = self.plantilla.elementos_frente
        for slot_idx, registro in enumerate(registros):
            if slot_idx >= len(self._card_positions):
                break
            self._render_card(c, registro, elems_frente, self._card_positions[slot_idx])
        c.showPage()

        # Página 2: vueltas
        self._current_cara = "vuelta"
        self._current_base_img = recursos.get("fondo_vuelta", "")
        elems_vuelta = self.plantilla.elementos_vuelta
        for slot_idx, registro in enumerate(registros):
            if slot_idx >= len(self._card_positions):
                break
            self._render_card(c, registro, elems_vuelta, self._card_positions[slot_idx])
        c.showPage()

        c.save()
        logger.info(
            "PDF dual generado: %s (%d registros, frente+vuelta)",
            output_path, len(registros),
        )
        return output_path

    def render_queue(
        self,
        items: list[tuple["Registro", "Plantilla"]],
        cara: str,
        output_path: Path,
    ) -> Path:
        """Genera PDF de una cola de impresión (solo frentes o solo vueltas).

        Agrupa ítems en pares (2 por página). Si el último grupo tiene
        solo 1 registro, la segunda posición queda vacía.
        El orden de los ítems se respeta para que frentes y vueltas
        coincidan al dar vuelta la hoja.

        Args:
            items: Lista de tuplas (registro, plantilla) en orden.
            cara: 'frente' o 'vuelta'.
            output_path: Ruta donde se guardará el PDF.

        Returns:
            La ruta al PDF generado.
        """
        output_path.parent.mkdir(parents=True, exist_ok=True)
        c = Canvas(str(output_path), pagesize=self._page_size)

        for page_idx in range(0, len(items), self._cards_per_page):
            page_items = items[page_idx : page_idx + self._cards_per_page]

            for slot_idx, (registro, plantilla) in enumerate(page_items):
                if slot_idx >= len(self._card_positions):
                    break

                # Configurar elementos y fondo para esta plantilla
                elementos = (
                    plantilla.elementos_frente
                    if cara == "frente"
                    else plantilla.elementos_vuelta
                )
                recursos = plantilla.recursos or {}
                base_key = "fondo_frente" if cara == "frente" else "fondo_vuelta"
                self._current_base_img = recursos.get(base_key, "")
                self._current_cara = cara

                base_pos = self._card_positions[slot_idx]
                self._render_card(c, registro, elementos, base_pos)

            c.showPage()

        c.save()
        logger.info(
            "PDF cola generado (%s): %s (%d registros)",
            cara, output_path, len(items),
        )
        return output_path


    def _render_card(
        self,
        canvas: Canvas,
        registro: "Registro",
        elementos: list[dict[str, Any]],
        base_pos: tuple[float, float],
    ) -> None:
        """Renderiza una credencial individual en la posición dada.

        Args:
            canvas: Canvas de ReportLab.
            registro: Datos del registro.
            elementos: Lista de elementos del diseño.
            base_pos: Posición base (x, y) en puntos.
        """
        card_w = cm_to_points(self.plantilla.ancho)
        card_h = cm_to_points(self.plantilla.alto)

        if self._rotate:
            # Para credenciales verticales acostadas a la izquierda: 
            # Trasladar a (base_x + card_h, base_y) y rotar +90°
            canvas.saveState()
            canvas.translate(base_pos[0] + card_h, base_pos[1])
            canvas.rotate(90)
        else:
            canvas.saveState()
            canvas.translate(base_pos[0], base_pos[1])

        # ── Imagen base (plantilla de fondo) ──────────────────────────────
        # La ruta se establece en render() como self._current_base_img
        base_img_path = getattr(self, "_current_base_img", "")
        if base_img_path and Path(base_img_path).exists():
            try:
                canvas.drawImage(
                    base_img_path, 0, 0,
                    width=card_w, height=card_h,
                    preserveAspectRatio=False, mask="auto",
                )
            except Exception as e:
                logger.warning("Error al dibujar imagen base: %s", e)


        # Ordenar elementos por z_order
        sorted_elements = sorted(elementos, key=lambda e: e.get("z_order", 0))

        for elem in sorted_elements:
            self._render_element(canvas, registro, elem, card_h)

        canvas.restoreState()


    def _render_element(
        self,
        canvas: Canvas,
        registro: "Registro",
        elem: dict[str, Any],
        card_height_pts: float,
    ) -> None:
        """Renderiza un elemento individual del diseño.

        Args:
            canvas: Canvas de ReportLab.
            registro: Datos del registro para sustitución de campos.
            elem: Definición del elemento (dict JSON).
            card_height_pts: Altura de la tarjeta en puntos (para flip Y).
        """
        elem_type = elem.get("type", "")
        x_pts = mm_to_points(elem.get("x", 0))
        y_pts = mm_to_points(elem.get("y", 0))
        w_pts = mm_to_points(elem.get("width", 0))
        h_pts = mm_to_points(elem.get("height", 0))
        props = elem.get("properties", {})

        # PDF tiene Y invertido: convertir de top-down a bottom-up
        y_pdf = card_height_pts - y_pts - h_pts

        if elem_type == "background":
            self._draw_background(canvas, x_pts, y_pdf, w_pts, h_pts, props)
        elif elem_type == "image" or elem_type == "photo_path":
            self._draw_image(canvas, registro, x_pts, y_pdf, w_pts, h_pts, elem, props)
        elif elem_type == "shape":
            self._draw_shape(canvas, x_pts, y_pdf, w_pts, h_pts, props)
        elif elem_type in ("text", "composite", "qr", "barcode"):
            # Compatibilidad y nuevos renders dinámicos
            render_as = props.get("render_as", "Texto")
            if elem_type == "qr": render_as = "Código QR"
            if elem_type == "barcode": render_as = "Código de Barras"

            if render_as == "Código QR":
                self._draw_qr(canvas, registro, x_pts, y_pdf, w_pts, h_pts, elem, props)
            elif render_as == "Código de Barras":
                self._draw_barcode(canvas, registro, x_pts, y_pdf, w_pts, h_pts, elem, props)
            else:
                self._draw_text(canvas, registro, x_pts, y_pdf, w_pts, h_pts, elem, props)

    def _draw_background(
        self,
        canvas: Canvas,
        x: float,
        y: float,
        w: float,
        h: float,
        props: dict,
    ) -> None:
        """Dibuja fondo: imagen o rectángulo de color."""
        src = props.get("src", "")
        if src and Path(src).exists():
            try:
                canvas.drawImage(
                    str(src), x, y, width=w, height=h,
                    preserveAspectRatio=True, mask="auto",
                )
            except Exception as e:
                logger.warning("Error al dibujar fondo '%s': %s", src, e)
        elif props.get("color"):
            canvas.setFillColor(_hex_to_color(props["color"]))
            canvas.rect(x, y, w, h, fill=1, stroke=0)

    def _get_element_text(self, registro: "Registro", elem: dict, props: dict) -> str:
        """Resuelve el texto a renderizar, manejando atributos simples y compuestos."""
        elem_type = elem.get("type", "")
        if elem_type == "composite":
            template = props.get("composite_template", "")
            if not template:
                return ""
            import re
            result = template
            keys = re.findall(r"\{(\w+)\}", template)
            for k in keys:
                result = result.replace(f"{{{k}}}", str(registro.get_dato(k, "")))
            return result

        campo = elem.get("campo_dato")
        if campo:
            return str(registro.get_dato(campo, ""))
        return props.get("text", "")

    def _draw_text(
        self,
        canvas: Canvas,
        registro: "Registro",
        x: float,
        y: float,
        w: float,
        h: float,
        elem: dict,
        props: dict,
    ) -> None:
        """Dibuja texto con sustitución de campo_dato."""
        text = self._get_element_text(registro, elem, props)

        if not text:
            return

        # Configurar fuente
        font_name = props.get("font_family", "Helvetica")
        font_size = props.get("font_size", 12)
        font_weight = props.get("font_weight", "normal")
        font_italic = props.get("font_italic", False)

        # Determinar variante (Bold, Italic, BoldItalic)
        is_bold = font_weight == "bold"
        if is_bold and font_italic:
            variant_suffix = "-BoldOblique"
        elif is_bold:
            variant_suffix = "-Bold"
        elif font_italic:
            variant_suffix = "-Oblique"
        else:
            variant_suffix = ""

        # Intentar registrar fuente custom; fallback a Helvetica con variante
        registered_name = _register_font(font_name)
        if registered_name == "Helvetica" and variant_suffix:
            registered_name = f"Helvetica{variant_suffix}"

        canvas.setFont(registered_name, font_size)

        # Color del texto
        color = props.get("color", "#171A2B")
        canvas.setFillColor(_hex_to_color(color))

        # Alineación
        alignment = props.get("alignment", "left")
        text_y = y + (h - font_size) / 2  # Centrado vertical aprox.

        if alignment == "center":
            canvas.drawCentredString(x + w / 2, text_y, text)
        elif alignment == "right":
            canvas.drawRightString(x + w, text_y, text)
        else:
            canvas.drawString(x, text_y, text)

    def _draw_image(
        self,
        canvas: Canvas,
        registro: "Registro",
        x: float,
        y: float,
        w: float,
        h: float,
        elem: dict,
        props: dict,
    ) -> None:
        """Dibuja una imagen (foto del registro o recurso estático)."""
        campo = elem.get("campo_dato", "")
        img_path: str | None = None

        # 1. Foto cacheada localmente en la BD
        if registro.photo_path and Path(str(registro.photo_path)).exists():
            img_path = str(registro.photo_path)

        # 2. Campo dinámico del registro (puede ser ruta local o URL HTTP)
        if not img_path:
            candidates = [campo] if campo else []
            for key in candidates + ["photo_url", "photo_path", "foto", "url_foto"]:
                val = registro.get_dato(key, "")
                if not val:
                    continue
                val_str = str(val)
                # Ruta local
                if Path(val_str).exists():
                    img_path = val_str
                    break
                # URL HTTP — descargar y cachear
                if val_str.startswith(("http://", "https://")):
                    cached = self._download_image(val_str)
                    if cached:
                        img_path = cached
                        break

        # 3. Src estático en props
        if not img_path:
            src = props.get("src", "")
            if src and Path(str(src)).exists():
                img_path = src
            elif src and str(src).startswith(("http://", "https://")):
                img_path = self._download_image(src)

        if img_path:
            try:
                canvas.drawImage(
                    str(img_path), x, y, width=w, height=h,
                    preserveAspectRatio=True, mask="auto",
                )
            except Exception as e:
                logger.warning("Error al dibujar imagen '%s': %s", img_path, e)
                canvas.setFillColorRGB(0.9, 0.9, 0.9)
                canvas.rect(x, y, w, h, fill=1, stroke=0)
        else:
            # Placeholder visual cuando no hay imagen disponible
            canvas.setFillColorRGB(0.93, 0.95, 0.98)
            canvas.setStrokeColorRGB(0.78, 0.83, 0.9)
            canvas.setLineWidth(0.5)
            canvas.rect(x, y, w, h, fill=1, stroke=1)
            canvas.setFillColorRGB(0.6, 0.65, 0.75)
            canvas.setFont("Helvetica", min(8, h * 0.25))
            canvas.drawCentredString(x + w / 2, y + h / 2 - 2, "[ FOTO ]")

    def _download_image(self, url: str) -> str | None:
        """Descarga una imagen desde URL y la guarda en caché temporal.

        Args:
            url: URL HTTP/HTTPS de la imagen.

        Returns:
            Ruta local del archivo descargado, o None si falla.
        """
        import tempfile, urllib.request, urllib.error

        # Clave de caché simple por URL
        if not hasattr(self, "_img_cache"):
            self._img_cache: dict[str, str] = {}
        if url in self._img_cache:
            cached = self._img_cache[url]
            return cached if Path(cached).exists() else None

        try:
            # Detectar extensión de la URL
            ext = ".jpg"
            for candidate in (".png", ".jpg", ".jpeg", ".gif", ".webp"):
                if candidate in url.lower():
                    ext = candidate
                    break

            fd, tmp_path = tempfile.mkstemp(suffix=ext, prefix="credencial_img_")
            import os; os.close(fd)

            # Timeout de 10 segundos
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                with open(tmp_path, "wb") as f:
                    f.write(resp.read())

            self._img_cache[url] = tmp_path
            logger.info("Imagen descargada: %s -> %s", url, tmp_path)
            return tmp_path
        except Exception as e:
            logger.warning("No se pudo descargar imagen '%s': %s", url, e)
            return None


    def _draw_qr(
        self,
        canvas: Canvas,
        registro: "Registro",
        x: float,
        y: float,
        w: float,
        h: float,
        elem: dict,
        props: dict,
    ) -> None:
        """Dibuja un código QR usando ReportLab."""
        qr_content = self._get_element_text(registro, elem, props)

        if not qr_content:
            return

        from reportlab.graphics.barcode import qr
        qr_code = qr.QrCodeWidget(qr_content)
        qr_code.barLevel = "M"
        
        bounds = qr_code.getBounds()
        qr_w = bounds[2] - bounds[0]
        qr_h = bounds[3] - bounds[1]

        # Calcular factor de escala para que encaje en (w, h)
        scale = min(w / qr_w, h / qr_h)
        
        # Centrar el QR dentro del rectángulo (w, h)
        tx = x + (w - qr_w * scale) / 2
        ty = y + (h - qr_h * scale) / 2
        
        d = Drawing(w, h, transform=[scale, 0, 0, scale, tx, ty])
        d.add(qr_code)
        renderPDF.draw(d, canvas, 0, 0)

    def _draw_barcode(
        self,
        canvas: Canvas,
        registro: "Registro",
        x: float,
        y: float,
        w: float,
        h: float,
        elem: dict,
        props: dict,
    ) -> None:
        """Genera y dibuja un código de barras en el lienzo usando reportlab."""
        content = self._get_element_text(registro, elem, props)
        if not content:
            return

        barcode_format = props.get("barcode_format", "Code128")
        
        try:
            from reportlab.graphics.barcode import createBarcodeDrawing
            bc = createBarcodeDrawing(barcode_format, value=content, width=w, height=h)
            # Dibujar centrado dentro del (w, h)
            # Barcode drawing objects from ReportLab ya vienen con drawOn
            bc.drawOn(canvas, x, y)
        except Exception as e:
            logger.warning("Error dibujando código de barras '%s': %s", content, e)

    def _draw_shape(
        self,
        canvas: Canvas,
        x: float,
        y: float,
        w: float,
        h: float,
        props: dict,
    ) -> None:
        """Dibuja formas geométricas (rectángulo, línea, etc.)."""
        shape_type = props.get("shape_type", "rect")
        fill_color = props.get("fill_color")
        stroke_color = props.get("stroke_color", "#000000")
        stroke_width = props.get("stroke_width", 1)

        canvas.setLineWidth(stroke_width)
        canvas.setStrokeColor(_hex_to_color(stroke_color))

        if fill_color:
            canvas.setFillColor(_hex_to_color(fill_color))

        if shape_type == "rect":
            border_radius = props.get("border_radius", 0)
            if border_radius > 0:
                canvas.roundRect(
                    x, y, w, h,
                    radius=border_radius,
                    fill=1 if fill_color else 0,
                    stroke=1,
                )
            else:
                canvas.rect(x, y, w, h, fill=1 if fill_color else 0, stroke=1)
        elif shape_type == "line":
            canvas.line(x, y, x + w, y + h)
        elif shape_type == "ellipse":
            canvas.ellipse(x, y, x + w, y + h, fill=1 if fill_color else 0, stroke=1)
