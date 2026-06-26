# Bugfix Design Document

## Overview

Este documento describe el diseño técnico de la corrección del bug en el que los atributos de texto (nombre, grado, etc.) no se alinean igual en el diseñador de plantillas que en la vista previa / impresión (PDF). El objetivo es que un atributo de texto se posicione de forma idéntica (alineación + tamaño efectivo + centrado) en el diseñador y en la vista previa, tanto en la ranura 1 como en la ranura 2, sin importar la longitud del dato real que sustituye al atributo.

La solución se basa en el modelo acordado en los requisitos: **caja de ancho fijo controlada por el usuario** (igual que la foto), **alineación resuelta dentro de la caja** y **auto-ajuste del tamaño de fuente (shrink-to-fit)** cuando el dato real no cabe, aplicando el mismo modelo en ambos motores de render.

## Glossary

- **Diseñador / lienzo:** el editor visual de plantillas; el render lo realiza `GraphicElement` en `ui/widgets/canvas.py` con Qt (QPainter).
- **Vista previa / PDF:** el resultado de impresión; lo genera `PDFEngine` en `renderer/pdf_engine.py` con ReportLab. La "vista previa" es un PDF generado con el mismo motor que la impresión final.
- **Caja del elemento:** rectángulo fijo definido por `x, y, width, height` (en mm) en el JSON del elemento.
- **Shrink-to-fit (auto-ajuste):** reducción proporcional del tamaño de fuente para que el texto quepa dentro del ancho de la caja.
- **Ranura 1 / Ranura 2:** posiciones (slots) de las dos credenciales por hoja en la charola de impresión.
- **WYSIWYG:** que lo mostrado en el diseñador coincide con el resultado impreso.
- **DPI:** puntos por pulgada; el diseñador escala a ~96 DPI (`MM_TO_PX = 3.7795`) y el PDF a 72 DPI (`MM_TO_POINTS = 2.83465`).

## Bug Details

Existen **dos rutas de render independientes** para el texto, con reglas distintas que producen la desalineación:

1. **Diseñador** — `GraphicElement._paint_text()` en `src/credencializacion/ui/widgets/canvas.py`:
   - Dibuja **siempre centrado** e **ignora** la propiedad `alignment`:
     ```python
     painter.drawText(self._rect, Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap, texto)
     ```
   - Hace **word-wrap** dentro de la caja fija `self._rect`.
   - Muestra el **nombre del campo** (p. ej. `"nombre"`) salvo que exista `props["test_text"]`.
   - Escala la fuente a px a ~96 DPI: `size_px = int(font_size * 0.352778 * MM_TO_PX)`.

2. **Vista previa / impresión** — `PDFEngine._draw_text()` en `src/credencializacion/renderer/pdf_engine.py`:
   - **Respeta** `alignment`: `left → drawString(x, …)`, `center → drawCentredString(x + w/2, …)`, `right → drawRightString(x + w, …)`.
   - Dibuja **una sola línea**: no hace word-wrap ni reduce la fuente si el texto excede `w`.
   - Usa el **dato real** del registro vía `_get_element_text()`.
   - Trabaja a 72 DPI; centrado vertical aproximado `text_y = y + (h - font_size)/2`.

Divergencias concretas:

| # | Diseñador (`_paint_text`) | PDF (`_draw_text`) | Efecto |
|---|---------------------------|--------------------|--------|
| A | Ignora `alignment` (siempre center) | Respeta `alignment` | left/right no coinciden |
| B | Word-wrap multilínea | Una sola línea | Forma/posición del bloque difiere |
| C | No reduce fuente | No reduce fuente | El dato largo se desborda en el PDF |
| D | Muestra nombre del campo | Muestra dato real | El diseñador no es WYSIWYG |
| E | Escala a 96 DPI | Escala a 72 DPI | Tamaño efectivo relativo a la caja distinto |

Ambas ranuras (1 y 2) pasan por la misma rutina `_render_card → _render_element → _draw_text`, por lo que una corrección en `_draw_text` aplica idéntica a las dos. La foto coincide porque `_draw_image` usa width/height fijos y `preserveAspectRatio` sin depender del contenido.

## Expected Behavior

- Un atributo de texto con alineación `center` o `right` se posiciona **idéntico** en el diseñador y en la vista previa, anclado a la caja fija, sin importar la longitud del dato real (Req. 2.1, 2.2).
- Si el dato real excede el ancho de la caja, el sistema **reduce el tamaño de fuente** (shrink-to-fit) con el mismo ajuste en ambos motores (Req. 2.3).
- El diseñador coincide visualmente con la vista previa (Req. 2.4) y el comportamiento es igual en ranura 1 y ranura 2 (Req. 2.5).
- Se preserva sin cambios: foto/imagen, formas, QR, código de barras, fondo, y texto `left` que ya cabe con su tamaño definido (Req. 3.1–3.4).

## Hypothesized Root Cause

La causa raíz es la **existencia de dos implementaciones de render de texto con reglas distintas** (tabla anterior, divergencias A–E). En particular:

- El diseñador ignora `alignment` y aplica word-wrap, mientras el PDF respeta `alignment` en una sola línea.
- Ninguno aplica auto-ajuste de fuente, por lo que el dato real (de longitud variable) rompe la coincidencia: en el diseñador el ancho usado para centrar es el de la caja con texto envuelto, y en el PDF el anclaje `center/right` depende de `w` con texto de una línea que puede desbordarse.
- Los distintos factores de escala (96 vs 72 DPI) hacen que el tamaño relativo a la caja no sea equivalente.

La foto no presenta el bug porque su render no depende de la longitud de ningún texto; ese modelo de "caja fija + contenido ajustado" es el patrón a replicar para el texto.

## Correctness Properties

### Property 1: Coincidencia de alineación
Para todo atributo de texto, el ancla horizontal en el diseñador y en el PDF es la misma función de `alignment` y de la caja (`left→x`, `center→x+w/2`, `right→x+w`).

**Validates: Requirements 2.1, 2.2, 2.4**

### Property 2: Auto-ajuste idéntico
Dado el mismo `(texto, ancho de caja, fuente, tamaño base)`, ambos motores calculan el mismo `effective_size` mediante el mismo algoritmo proporcional (con tolerancia por diferencias de métricas entre motores de fuente).

**Validates: Requirements 2.3, 2.4**

### Property 3: Encaje
El texto renderizado con `effective_size` no excede el ancho útil de la caja.

**Validates: Requirements 2.3**

### Property 4: No regresión
Para entradas que no disparan el bug (texto `left` que cabe, foto, forma, QR, barcode, fondo), el resultado es idéntico al comportamiento previo (`effective_size == base_font_size`).

**Validates: Requirements 3.1, 3.2, 3.3, 3.4**

### Property 5: Igualdad entre ranuras
El render de un mismo atributo es idéntico en ranura 1 y ranura 2.

**Validates: Requirements 2.5**

## Fix Implementation

### 1. Utilidad compartida de ajuste de texto (nuevo)

Crear `src/credencializacion/renderer/text_fit.py` con una función pura, agnóstica del framework de medición:

```python
def fit_font_size(
    measure_width,        # callable(text, font_size) -> ancho en las MISMAS unidades que box_width
    text: str,
    box_width: float,
    base_font_size: float,
    min_font_size: float = 1.0,
    padding: float = 0.0,
) -> float:
    """Mayor tamaño <= base_font_size tal que measure_width(text, size) <= box_width - 2*padding.
    Si cabe con base_font_size, lo devuelve sin cambios. Acotado por min_font_size."""
```

- **Algoritmo idéntico** en ambos motores; sólo cambia el `measure_width` inyectado:
  - Diseñador (Qt): `QFontMetricsF(font).horizontalAdvance(text)` en px, `box_width` en px.
  - PDF (ReportLab): `pdfmetrics.stringWidth(text, font_name, size)` en puntos, `box_width` en puntos.
- Como el ancho del texto es monótono respecto al tamaño, se calcula `effective = base * min(1, (box_width - 2*padding) / measured_at_base)` con un ajuste fino decreciente para garantizar el encaje exacto, acotado por `min_font_size`.

### Modelo unificado de anclaje (clave de la coincidencia pixel a pixel)

Para garantizar que el diseñador y el PDF coincidan exactamente, **ningún motor delega el centrado al framework** (se elimina `drawText(rect, AlignCenter)` y se evita depender del centrado interno de cada librería). En su lugar, ambos calculan explícitamente el punto de inicio del texto con la misma matemática, usando el **ancho real medido** del texto con la fuente efectiva (esto implementa la Opción 1 acordada: el centro de referencia se calcula a partir del contenido dentro de la caja).

Algoritmo común (en unidades nativas de cada motor):

```
anchor_x = {  left: x,  center: x + w/2,  right: x + w  }[alignment]
text_w   = measure_width(text, effective_size)
start_x  = {  left: anchor_x,
              center: anchor_x - text_w/2,
              right: anchor_x - text_w  }[alignment]
```

- `effective_size` proviene de `fit_font_size` (shrink-to-fit) → el texto nunca excede `w`, por lo que con `center`/`right` el inicio nunca se sale de la caja.
- El **baseline vertical** se calcula igual en ambos motores a partir del centro vertical de la caja y de las métricas ascent/descent de la fuente, en vez de la aproximación `(h - font_size)/2`.
- La única diferencia entre motores es la función `measure_width` (nativa de cada uno) y el sistema de coordenadas (Qt top-down / PDF bottom-up), que ya se maneja en `_render_element`.

### 2. Diseñador — `GraphicElement._paint_text` (`ui/widgets/canvas.py`)

1. Resolver el texto priorizando `props["test_text"]` (dato real/muestra); si no existe, mantener el placeholder con el nombre del campo aplicando igualmente alineación y shrink-to-fit.
2. **Eliminar `TextWordWrap` y `AlignCenter`**: dibujar en una sola línea.
3. Calcular `effective_size` con `fit_font_size` midiendo con `QFontMetricsF.horizontalAdvance`.
4. Calcular `anchor_x` y `start_x` con el algoritmo común; medir `text_w` con `QFontMetricsF` a `effective_size`.
5. Calcular el baseline vertical con `QFontMetricsF` (centro de la caja + ascent/descent) y dibujar con `painter.drawText(QPointF(start_x, baseline_y), texto)` (variante de punto, no de rectángulo).
6. Mostrar el fondo punteado de ayuda **solo** cuando se pinta el placeholder de nombre de campo (sin `test_text`).

### 3. PDF — `PDFEngine._draw_text` (`renderer/pdf_engine.py`)

1. Tras resolver `text` y registrar la fuente, calcular `effective_size` con `fit_font_size` midiendo con `pdfmetrics.stringWidth`, `box_width = w`.
2. Calcular `anchor_x` y `start_x` con el algoritmo común; medir `text_w` con `pdfmetrics.stringWidth(text, registered_name, effective_size)`.
3. Dibujar **siempre con `canvas.drawString(start_x, baseline_y, text)`** (se deja de usar `drawCentredString`/`drawRightString`, ya que el centrado/derecha se resuelve en `start_x`), garantizando la misma fórmula que el diseñador.
4. Calcular `baseline_y` con `pdfmetrics.getAscentDescent(registered_name, effective_size)` a partir del centro vertical de la caja, unificando el centrado vertical con el diseñador.

### Mapa de alineación unificado

| `alignment` | `anchor_x` | `start_x` (a partir del ancho real `text_w`) |
|-------------|-----------|-----------------------------------------------|
| `left` | `x` | `anchor_x` |
| `center` | `x + w/2` | `anchor_x - text_w/2` |
| `right` | `x + w` | `anchor_x - text_w` |
| `justify` | `x` | `anchor_x` (tratado como left) |

Ambos motores usan `drawString`/`drawText(point)` con `start_x`; ninguno usa el centrado automático del framework.

### Componentes afectados

| Componente | Archivo | Cambio |
|-----------|---------|--------|
| Utilidad de ajuste (nuevo) | `renderer/text_fit.py` | `fit_font_size()` compartida |
| Render diseñador | `ui/widgets/canvas.py` | `_paint_text`: alignment, sin wrap, shrink-to-fit, dato real |
| Render PDF | `renderer/pdf_engine.py` | `_draw_text`: shrink-to-fit, centrado vertical unificado |
| Sin cambios | `coordinates.py`, `properties.py`, `_draw_image/_shape/_qr/_barcode` | Se preservan |

### Compatibilidad con plantillas existentes

- No se modifica el esquema JSON del elemento (`x, y, width, height, campo_dato, properties`); el ajuste se calcula en tiempo de render.
- `alignment` ausente → `left` (como hoy). Las plantillas guardadas siguen funcionando; lo único observable es que el texto que se desbordaba ahora se ajusta y alinea.

### Decisiones de diseño

- **Una sola línea + shrink-to-fit** (en vez de word-wrap): replica el modelo de la foto, es determinista y fácil de igualar entre Qt y ReportLab.
- **Utilidad compartida con `measure_width` inyectable:** un único algoritmo de ajuste evita la lógica divergente que originó el bug.
- **`justify` → `left`:** el PDF no justifica una sola línea; evitar una nueva divergencia.

## Testing Strategy

1. **Unitarias de `fit_font_size`** (con `measure_width` lineal simulado, sin Qt/ReportLab):
   - Texto que cabe → devuelve `base_font_size`.
   - Texto el doble de ancho que la caja → ~`base_font_size/2`.
   - Respeta `min_font_size`.
2. **Coincidencia de medición (integración, opcional):** para una fuente registrada, verificar que `effective_size` con `QFontMetricsF` y con `pdfmetrics.stringWidth` difiere por debajo de una tolerancia razonable.
3. **Verificación manual WYSIWYG:** atributo `nombre` con alineación `center` y `right`; `test_text` corto ("Ana") y largo ("María Guadalupe de la Concepción"); comparar diseñador vs PDF en ranura 1 y ranura 2.
4. **Flujo `preview_template`** con 2 registros reales: confirmar que ambas tarjetas alinean igual que el diseñador.
