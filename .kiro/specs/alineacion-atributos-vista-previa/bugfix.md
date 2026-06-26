# Bugfix Requirements Document

## Introduction

En el editor de plantillas, los atributos de texto (nombre, grado, etc.) no se alinean igual en el diseñador que en la vista previa/impresión (PDF). Cuando el atributo se coloca con alineación centro o derecha, la posición del texto en la vista previa difiere de la mostrada en el diseñador, y el desfase aumenta cuando el dato real que sustituye al atributo tiene una longitud distinta a la del texto de ejemplo. El atributo de foto sí coincide entre diseñador y vista previa (y entre la ranura 1 y la ranura 2) porque tiene un ancho y alto fijos definidos por el usuario.

El objetivo es que los atributos de texto se alineen IGUAL en el diseñador y en la vista previa, tanto en la ranura 1 como en la ranura 2, sin importar la longitud del nombre/dato real. La solución debe basarse en lo ya implementado: la etiqueta del atributo debe ajustar sus proporciones a la sustitución real de los datos (reduciendo el tamaño de fuente cuando el dato no cabe en la caja), y esos mismos parámetros deben aplicarse en la vista previa con los datos reales. El diseñador y la vista previa deben coincidir usando el mismo modelo de caja fija, alineación y auto-ajuste.

## Bug Analysis

### Current Behavior (Defect)

Comportamiento actual cuando se coloca un atributo de texto con alineación centro o derecha y se genera la vista previa con datos reales.

1.1 WHEN un atributo de texto tiene alineación "center" THEN el diseñador dibuja el texto desde el borde izquierdo de su caja mientras que la vista previa lo ancla en `x + w/2`, produciendo una posición horizontal distinta entre diseñador y vista previa

1.2 WHEN un atributo de texto tiene alineación "right" THEN el diseñador dibuja el texto desde el borde izquierdo mientras que la vista previa lo ancla en `x + w`, produciendo una posición horizontal distinta entre diseñador y vista previa

1.3 WHEN el dato real que sustituye al atributo tiene una longitud distinta a la del texto de ejemplo THEN el sistema usa un ancho (`w`) derivado del boundingRect del texto de ejemplo para anclar el texto, por lo que el centro/derecha no coincide con lo mostrado y el desfase aumenta

1.4 WHEN el dato real es más ancho que la caja del atributo THEN el sistema no ajusta el tamaño del texto y este se desborda, difiriendo de lo mostrado en el diseñador

1.5 WHEN el mismo atributo de texto desalineado se renderiza en la ranura 1 y en la ranura 2 THEN el sistema reproduce la misma desalineación respecto al diseñador en ambas ranuras

### Expected Behavior (Correct)

Comportamiento correcto esperado para las mismas condiciones.

2.1 WHEN un atributo de texto tiene alineación "center" THEN el sistema SHALL posicionar el texto de forma idéntica en el diseñador y en la vista previa, anclado dentro de la caja fija del elemento, sin importar la longitud del dato real

2.2 WHEN un atributo de texto tiene alineación "right" THEN el sistema SHALL posicionar el texto de forma idéntica en el diseñador y en la vista previa, anclado al borde derecho de la caja fija del elemento, sin importar la longitud del dato real

2.3 WHEN el dato real que sustituye al atributo es más ancho que la caja del atributo THEN el sistema SHALL reducir el tamaño de fuente (auto-ajuste) hasta que el texto quepa en la caja, aplicando el mismo ajuste tanto en el diseñador como en la vista previa

2.4 WHEN se renderiza un atributo de texto THEN el sistema SHALL dibujar el texto alineado (izquierda/centro/derecha) dentro de la caja fija en el diseñador, de modo que coincida pixel a pixel con la vista previa

2.5 WHEN el mismo atributo de texto se renderiza en la ranura 1 y en la ranura 2 THEN el sistema SHALL producir la misma alineación y el mismo auto-ajuste respecto a la caja en ambas ranuras

### Unchanged Behavior (Regression Prevention)

Comportamiento existente que debe preservarse.

3.1 WHEN se renderiza un atributo de foto/imagen THEN el sistema SHALL CONTINUE TO alinearlo de forma idéntica en el diseñador, la vista previa y entre la ranura 1 y la ranura 2

3.2 WHEN un atributo de texto tiene alineación "left" y el dato cabe dentro de la caja THEN el sistema SHALL CONTINUE TO posicionar el texto iniciando en el borde izquierdo de la caja

3.3 WHEN el dato real que sustituye al atributo cabe dentro de la caja THEN el sistema SHALL CONTINUE TO renderizar el texto con el tamaño de fuente definido por el usuario (sin reducirlo)

3.4 WHEN se renderiza un elemento de tipo QR, código de barras, forma o fondo THEN el sistema SHALL CONTINUE TO renderizarlo sin cambios en posición ni tamaño

## Derivación de la Condición del Bug

### Función de Condición del Bug

```pascal
FUNCTION isBugCondition(X)
  INPUT: X of type RenderInput {
    elementType: string,        // tipo de elemento ("text", "image", ...)
    alignment: string,          // "left" | "center" | "right"
    boxWidth: number,           // ancho de la caja del elemento
    sampleText: string,         // texto de ejemplo usado en el diseñador
    realText: string            // dato real que sustituye al atributo
  }
  OUTPUT: boolean

  // El bug se manifiesta en atributos de texto cuando la alineación es
  // centro o derecha, o cuando el dato real no coincide en proporción con
  // el ancho usado para el anclaje (longitud distinta a la del ejemplo o
  // texto más ancho que la caja).
  RETURN X.elementType = "text"
         AND (
              X.alignment = "center"
              OR X.alignment = "right"
              OR width(X.realText) <> width(X.sampleText)
              OR width(X.realText) > X.boxWidth
         )
END FUNCTION
```

### Especificación de la Propiedad (Fix Checking)

```pascal
// Property: Fix Checking - El texto se posiciona igual en diseñador y vista
// previa dentro de la caja fija, con auto-ajuste cuando no cabe.
FOR ALL X WHERE isBugCondition(X) DO
  designerPos ← renderDesigner'(X)   // posición/anchor del texto en el diseñador
  previewPos  ← renderPreview'(X)    // posición/anchor del texto en la vista previa

  ASSERT anchorWithinBox(previewPos, X.boxWidth, X.alignment)
  ASSERT designerPos = previewPos            // coinciden pixel a pixel
  ASSERT fitsInsideBox(X.realText, X.boxWidth, fontSize'(X))  // auto-ajuste si excede
END FOR
```

### Objetivo de Preservación (Preservation Checking)

```pascal
// Property: Preservation Checking - Para entradas que no disparan el bug
// (fotos, formas, QR, barcode, y texto alineado a la izquierda que cabe),
// el comportamiento del código corregido es idéntico al original.
FOR ALL X WHERE NOT isBugCondition(X) DO
  ASSERT F(X) = F'(X)
END FOR
```

**Definiciones:**
- **F**: El código original (sin corregir): el diseñador dibuja el texto desde la izquierda y la vista previa ancla según `alignment` usando un ancho que no corresponde al dato real, sin auto-ajuste.
- **F'**: El código corregido: el texto se ancla dentro de una caja fija según la alineación y se auto-ajusta el tamaño de fuente cuando el dato real no cabe, aplicando el mismo modelo en diseñador y vista previa.
- **Contraejemplo**: Un atributo de texto "Nombre" con alineación centro, caja de ancho fijo, texto de ejemplo "Texto de ejemplo" y dato real "María Guadalupe de la Concepción": en el diseñador aparece centrado dentro de la caja, pero en la vista previa el texto aparece desplazado/desbordado respecto a esa caja.
