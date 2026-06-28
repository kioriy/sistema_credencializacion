# Requirements Document

## Introduction

El **multiplantillaje base** permite que un mismo diseño use distintas **imágenes de fondo** según los datos de cada registro, sin crear diseños adicionales. La configuración se define **por lado** de cada diseño: la clave es la combinación `(diseño, lado)` con `lado` en {frente, vuelta}, y existe a lo sumo una configuración por esa combinación. Un mismo diseño puede tener, por ejemplo, cinco variantes en el lado frente y una sola (sin flujo de reglas) en el lado vuelta.

Una **Configuracion_Por_Lado** contiene una **Imagen_Base_Por_Defecto** (la imagen que se muestra en el diseñador y en la vista previa) más cero o más **Variantes**. Cada **Variante** combina una o más **Condiciones** del tipo "atributo igual a valor" en conjunción lógica (Y) —por ejemplo `grado == 1 Y grupo == "A"`— que mapean a **una ruta de imagen base** (un `path`), no a un diseño. El resto del layout del diseño (textos, foto, QR, posiciones) se mantiene idéntico en todas las variantes: lo único que cambia es la imagen de fondo del lado.

El flujo de interfaz se inicia al hacer clic en el **encabezado FRENTE o VUELTA** del Editor de Plantillas, que abre el explorador de archivos con selección múltiple. Si se selecciona **una sola imagen**, esta se asigna directamente como imagen base de ese lado, sin crear configuración ni reglas (comportamiento actual de imagen base). Si se seleccionan **dos o más imágenes**, se abre directamente la **Vista_Configuracion** para ese lado: una fila por imagen con su vista previa, sus condiciones atributo=valor (agregar/quitar en conjunción) y una marca para indicar cuál es la imagen base por defecto. Mientras exista una Configuracion_Por_Lado para un lado, la asignación de imagen desde el encabezado de ese lado queda inhabilitada y el botón de configuración (engranaje ⚙, junto al encabezado) queda habilitado.

En impresión, para cada registro y cada lado: si el diseño tiene Configuracion_Por_Lado para ese lado, el Motor_Seleccion_Imagen evalúa las variantes (conjunción de condiciones, primera coincidencia por orden) y elige la ruta de imagen base, renderizando el mismo layout del diseño con esa imagen de fondo; si ninguna variante coincide, se usa la Imagen_Base_Por_Defecto. Si no hay configuración para el lado, se conserva el comportamiento actual (la imagen base del diseño en `Plantilla.recursos`).

Esta especificación corrige el modelo previo: se elimina toda noción de "plantilla destino como diseño" y de "configuración por cliente". Las imágenes base son únicamente rutas de imagen almacenadas dentro de una configuración por `(diseño, lado)`; el sistema no crea diseños ni plantillas nuevas al cargar varias imágenes base.

## Glossary

- **Editor_Plantillas**: Vista de edición de plantillas (`template_editor.py`) donde se edita el layout de un diseño y se asigna la imagen base por lado.
- **Plantilla**: Definición visual de un diseño perteneciente a un Cliente (`models.py:Plantilla`). Almacena su layout y las imágenes base actuales en `Plantilla.recursos` (`fondo_frente`/`fondo_vuelta`).
- **Lado**: Cara del diseño sobre la que aplica una configuración, con valor `frente` o `vuelta`.
- **Encabezado_Lado**: Control del Editor_Plantillas etiquetado "FRENTE" o "VUELTA", uno por Lado, cuyo clic inicia el flujo de selección de imágenes base de ese Lado.
- **Explorador_Archivos**: Selector de archivos de imagen del sistema operativo, abierto con selección múltiple habilitada, mediante el cual el usuario elige una o más imágenes base.
- **Boton_Configuracion**: Control de interfaz que muestra el icono de engranaje (estilo `qtawesome fa5s.cog`), ubicado junto a cada Encabezado_Lado, que abre la Vista_Configuracion de la Configuracion_Por_Lado de ese Lado.
- **Configuracion_Por_Lado**: Conjunto persistido, único por la combinación `(Plantilla, Lado)`, que contiene una referencia a la Imagen_Base_Por_Defecto y de 0 a 100 Variantes. Una misma Plantilla puede tener una Configuracion_Por_Lado distinta para el Lado frente y para el Lado vuelta.
- **Variante**: Unidad de una Configuracion_Por_Lado compuesta por una o más Condicion que deben cumplirse todas (conjunción lógica Y) y por una Ruta_Imagen_Base destino. Se expresa como "Condicion [Y Condicion]... → Ruta_Imagen_Base".
- **Condicion**: Elemento de una Variante compuesto por un Atributo, un operador de igualdad y un valor. Se expresa como "atributo igual a valor". Una Variante coincide únicamente cuando todas sus Condicion se cumplen.
- **Ruta_Imagen_Base**: Ruta de archivo (`path`) de una imagen que se usa como fondo del Lado. Es el destino de una Variante y de la Imagen_Base_Por_Defecto. No referencia un diseño ni una Plantilla.
- **Imagen_Base_Por_Defecto**: Ruta_Imagen_Base de una Configuracion_Por_Lado que el sistema usa como fondo del Lado cuando ninguna Variante coincide, y que se muestra en el Editor_Plantillas y en la Vista_Previa.
- **Vista_Configuracion**: Vista que lista una fila por Ruta_Imagen_Base de la Configuracion_Por_Lado, mostrando la Vista_Previa_Imagen de cada una, sus Condicion (agregar/quitar en conjunción) y la marca de Imagen_Base_Por_Defecto.
- **Vista_Previa_Imagen**: Representación visual en miniatura de una Ruta_Imagen_Base mostrada en su fila de la Vista_Configuracion.
- **Vista_Previa**: Función de vista previa del diseñador existente, accionada por su botón actual, que renderiza el Lado con su imagen base resultante. No se agregan botones nuevos de vista previa.
- **Atributo**: Clave de los datos dinámicos de un registro (`Registro.datos`, por ejemplo `grado`, `grupo`, `nivel_escolar`) usada como criterio de una Condicion.
- **Atributos_Disponibles**: Conjunto de claves de Atributo ofrecidas al usuario en la Vista_Configuracion, derivado de `Cliente.config["known_attributes"]` y/o de las claves presentes en `Registro.datos`.
- **Flujo_Impresion**: Proceso que arma la cola de impresión (`control_panel.py`) y genera el PDF (`print_center.py` + `pdf_engine.py`).
- **Motor_Seleccion_Imagen**: Componente lógico que, dado un Registro, un Lado y la Configuracion_Por_Lado correspondiente, evalúa las Variantes y devuelve la Ruta_Imagen_Base a usar como fondo de ese Lado.
- **Cliente**: Organización propietaria de registros y plantillas (`models.py:Cliente`).
- **Registro**: Sujeto individual de una credencial con datos dinámicos en `Registro.datos` (`models.py:Registro`).

## Requirements

### Requisito 1: Iniciar la selección de imágenes base desde el encabezado de un lado

**Historia de usuario:** Como diseñador de credenciales, quiero hacer clic en el encabezado FRENTE o VUELTA y elegir una o varias imágenes, para asignar la imagen base del lado o configurar su multiplantillaje desde un único punto.

#### Criterios de Aceptación

1. WHEN el usuario activa el Encabezado_Lado de un Lado, THE Editor_Plantillas SHALL abrir el Explorador_Archivos con selección múltiple de imágenes habilitada para ese Lado.
2. WHEN el usuario confirma en el Explorador_Archivos la selección de exactamente una imagen, THE Editor_Plantillas SHALL asignar la Ruta_Imagen_Base seleccionada como imagen base del Lado en `Plantilla.recursos` sin crear una Configuracion_Por_Lado.
3. WHEN el usuario confirma en el Explorador_Archivos la selección de dos o más imágenes para un Lado, THE Editor_Plantillas SHALL abrir la Vista_Configuracion de ese Lado mostrando una fila por imagen seleccionada, sin presentar un paso previo de selección por casillas.
4. WHILE existe una Configuracion_Por_Lado para un Lado, THE Editor_Plantillas SHALL mantener inhabilitada la activación del Encabezado_Lado de ese Lado para asignar imágenes.
5. IF el usuario cancela el Explorador_Archivos sin confirmar una selección, THEN THE Editor_Plantillas SHALL conservar la imagen base del Lado sin cambios y no abrir la Vista_Configuracion.
6. IF alguna de las imágenes seleccionadas en el Explorador_Archivos no puede leerse como imagen, THEN THE Editor_Plantillas SHALL mostrar un mensaje de error que identifique el archivo afectado y SHALL conservar la imagen base del Lado sin cambios.

### Requisito 2: Habilitar y reflejar el estado del botón de configuración

**Historia de usuario:** Como diseñador de credenciales, quiero un botón de engranaje junto a cada encabezado de lado que se habilite cuando corresponde, para acceder a la configuración de multiplantillaje del lado.

#### Criterios de Aceptación

1. THE Editor_Plantillas SHALL mostrar un Boton_Configuracion con el icono de engranaje adyacente a cada Encabezado_Lado, uno por Lado.
2. THE Boton_Configuracion SHALL mostrar únicamente el icono de engranaje, sin texto de etiqueta visible.
3. WHILE la Plantilla en edición está guardada y existe una Configuracion_Por_Lado para un Lado, THE Editor_Plantillas SHALL mantener habilitado el Boton_Configuracion de ese Lado.
4. WHILE la Plantilla en edición no está guardada, THE Editor_Plantillas SHALL mantener deshabilitado el Boton_Configuracion de cada Lado.
5. WHEN el usuario activa un Boton_Configuracion habilitado, THE Editor_Plantillas SHALL abrir la Vista_Configuracion del Lado correspondiente en un máximo de 1 segundo.
6. WHEN el usuario guarda la Plantilla en edición, THE Editor_Plantillas SHALL actualizar el estado habilitado o deshabilitado del Boton_Configuracion de cada Lado para reflejar si ese Lado tiene una Configuracion_Por_Lado, sin requerir reabrir el Editor_Plantillas.
7. WHEN el usuario mantiene el puntero sobre un Boton_Configuracion durante al menos 1 segundo, THE Editor_Plantillas SHALL mostrar un texto de ayuda legible, con suficiente contraste entre el color del texto y el color de fondo, que identifique la acción de configurar el multiplantillaje del Lado.

### Requisito 3: Configurar variantes de imagen base en la Vista de Configuración

**Historia de usuario:** Como diseñador de credenciales, quiero definir para cada imagen base las condiciones que la activan y marcar la imagen por defecto, para que cada registro use la imagen de fondo correcta sin alterar el resto del diseño.

#### Criterios de Aceptación

1. WHEN la Vista_Configuracion se abre, THE Vista_Configuracion SHALL mostrar una fila por cada Ruta_Imagen_Base de la Configuracion_Por_Lado, cada una con su Vista_Previa_Imagen.
2. IF una Ruta_Imagen_Base de una fila no puede leerse como imagen, THEN THE Vista_Configuracion SHALL mostrar un indicador de vista previa no disponible para esa fila y SHALL permitir continuar con la configuración de esa fila.
3. THE Vista_Configuracion SHALL permitir definir, en la fila de cada Ruta_Imagen_Base, una Variante compuesta por una o más Condicion, donde cada Condicion incluye un Atributo, un operador de igualdad y un valor de 1 a 255 caracteres.
4. THE Vista_Configuracion SHALL permitir agregar y quitar Condicion dentro de la Variante de una fila, manteniendo al menos una Condicion por Variante.
5. THE Vista_Configuracion SHALL ofrecer la selección del Atributo de cada Condicion a partir de los Atributos_Disponibles del Cliente.
6. THE Vista_Configuracion SHALL representar cada Variante como la conjunción de sus Condicion en la forma "Atributo igual a valor [Y Atributo igual a valor]... usa esta imagen base".
7. THE Vista_Configuracion SHALL permitir marcar exactamente una Ruta_Imagen_Base de la Configuracion_Por_Lado como Imagen_Base_Por_Defecto.
8. IF el usuario intenta guardar y alguna Condicion definida carece de Atributo o de valor, THEN THE Vista_Configuracion SHALL rechazar el guardado, conservar los datos ya ingresados sin alterarlos y mostrar un mensaje que indique cada campo faltante.
9. IF el usuario intenta guardar y dos Variantes tienen el mismo conjunto de Condicion (mismos pares Atributo y valor), THEN THE Vista_Configuracion SHALL rechazar el guardado y mostrar un mensaje que indique la Variante duplicada.
10. IF el usuario intenta guardar sin haber marcado una Imagen_Base_Por_Defecto, THEN THE Vista_Configuracion SHALL rechazar el guardado y mostrar un mensaje que indique que se requiere designar la imagen base por defecto.

### Requisito 4: Persistir la configuración por lado mediante upsert

**Historia de usuario:** Como usuario del sistema, quiero que cada par diseño-lado tenga una única configuración que se cree o actualice al guardar, para que la impresión la use sin generar configuraciones duplicadas ni diseños nuevos.

#### Criterios de Aceptación

1. WHEN el usuario confirma el guardado en la Vista_Configuracion, THE Configuracion_Por_Lado SHALL persistirse como la única configuración asociada a la combinación `(Plantilla, Lado)`, creándola si no existe o actualizándola si ya existe.
2. THE Configuracion_Por_Lado SHALL mantener una relación de a lo sumo una configuración por combinación `(Plantilla, Lado)`, de modo que incluir varias imágenes base no produzca varias Configuracion_Por_Lado.
3. WHEN el usuario guarda una Configuracion_Por_Lado para una combinación `(Plantilla, Lado)` que ya tiene una, THE Configuracion_Por_Lado SHALL actualizar la configuración existente reemplazando sus Variantes y su Imagen_Base_Por_Defecto en lugar de crear una nueva.
4. THE Configuracion_Por_Lado SHALL almacenar de 0 a 100 Variantes, cada una con una o más Condicion y una Ruta_Imagen_Base, más una referencia a la Imagen_Base_Por_Defecto.
5. THE Configuracion_Por_Lado SHALL almacenar las Variantes como rutas de imagen base y SHALL no crear ninguna Plantilla ni diseño al guardar.
6. WHEN la persistencia de la Configuracion_Por_Lado finaliza correctamente, THE Vista_Configuracion SHALL mostrar una confirmación visible de guardado exitoso al usuario.
7. WHEN la Vista_Configuracion se abre para una combinación `(Plantilla, Lado)` que ya tiene una Configuracion_Por_Lado, THE Vista_Configuracion SHALL cargar y mostrar todas las Variantes con sus Condicion y la Imagen_Base_Por_Defecto previamente guardadas.
8. IF la persistencia de la Configuracion_Por_Lado falla, THEN THE Vista_Configuracion SHALL conservar sin modificaciones los cambios mostrados en pantalla y SHALL mostrar un mensaje de error que indique la causa del fallo.
9. IF la carga de una Configuracion_Por_Lado existente falla al abrir la Vista_Configuracion, THEN THE Vista_Configuracion SHALL mostrar un mensaje de error que indique la causa del fallo y SHALL abrirse sin Variantes precargadas.

### Requisito 5: Seleccionar automáticamente la imagen base por registro durante la impresión

**Historia de usuario:** Como operador de impresión, quiero que cada registro reciba automáticamente la imagen de fondo correcta según sus datos, para imprimir lotes mixtos sin cambiar la imagen base manualmente.

#### Criterios de Aceptación

1. WHERE existe una Configuracion_Por_Lado para la combinación `(Plantilla, Lado)`, WHEN el Flujo_Impresion procesa un Registro para ese Lado, THE Motor_Seleccion_Imagen SHALL evaluar las Variantes contra los datos del Registro siguiendo el orden definido en la Configuracion_Por_Lado.
2. WHEN todas las Condicion de una Variante se cumplen para un Registro, donde cada Condicion se cumple si el valor de su Atributo en el Registro coincide con el valor de la Condicion comparando como texto sin distinguir mayúsculas de minúsculas y eliminando los espacios al inicio y al final, THE Motor_Seleccion_Imagen SHALL seleccionar la Ruta_Imagen_Base de esa Variante para ese Lado.
3. IF al menos una Condicion de una Variante no se cumple para un Registro, THEN THE Motor_Seleccion_Imagen SHALL tratar esa Variante como no coincidente para ese Registro.
4. IF ninguna Variante coincide con los datos del Registro, THEN THE Motor_Seleccion_Imagen SHALL seleccionar la Imagen_Base_Por_Defecto de la Configuracion_Por_Lado.
5. WHEN los datos de un Registro hacen coincidir más de una Variante, THE Motor_Seleccion_Imagen SHALL seleccionar la Ruta_Imagen_Base de la primera Variante coincidente según el orden definido en la Configuracion_Por_Lado.
6. WHEN el Flujo_Impresion genera el PDF de un Registro para un Lado con Configuracion_Por_Lado, THE Flujo_Impresion SHALL renderizar el mismo layout del diseño de ese Lado usando como fondo la Ruta_Imagen_Base seleccionada por el Motor_Seleccion_Imagen.
7. WHERE no existe una Configuracion_Por_Lado para la combinación `(Plantilla, Lado)`, THE Flujo_Impresion SHALL conservar el comportamiento actual de usar la imagen base del diseño almacenada en `Plantilla.recursos` para ese Lado.
8. IF un Registro no contiene el Atributo evaluado por una Condicion de una Variante, THEN THE Motor_Seleccion_Imagen SHALL tratar esa Condicion como no cumplida y la Variante como no coincidente, continuando la evaluación con las Variantes restantes sin interrumpir el procesamiento del Registro.
9. IF la Ruta_Imagen_Base seleccionada para un Registro no puede cargarse al generar el PDF, THEN THE Flujo_Impresion SHALL omitir la generación de ese Registro para ese Lado y presentar una indicación de error que identifique el Registro y la Ruta_Imagen_Base afectados, continuando con los Registros restantes de la cola.

### Requisito 6: Editar una configuración por lado existente

**Historia de usuario:** Como diseñador de credenciales, quiero modificar una configuración guardada reasignando imágenes, cambiando condiciones o eliminando variantes, para mantener el multiplantillaje del lado actualizado.

#### Criterios de Aceptación

1. WHEN el usuario reasigna la Ruta_Imagen_Base de una Variante en la Vista_Configuracion, THE Vista_Configuracion SHALL actualizar la Ruta_Imagen_Base de esa Variante conservando sus Condicion sin cambios.
2. WHEN el usuario cambia las Condicion de una Variante, THE Vista_Configuracion SHALL actualizar las Condicion de esa Variante conservando el resto de la Configuracion_Por_Lado sin cambios.
3. THE Vista_Configuracion SHALL permitir eliminar una Variante de la Configuracion_Por_Lado.
4. WHEN la Vista_Configuracion se abre para una Configuracion_Por_Lado existente y el usuario carga imágenes adicionales mediante el Explorador_Archivos, THE Vista_Configuracion SHALL agregar una fila por cada imagen nueva para definir su Variante, conservando las Variantes existentes.
5. THE Vista_Configuracion SHALL permitir eliminar la Configuracion_Por_Lado completa, y al confirmar la eliminación THE Editor_Plantillas SHALL rehabilitar la activación del Encabezado_Lado de ese Lado para asignar imágenes.
6. WHEN el usuario cambia la marca de Imagen_Base_Por_Defecto a otra Ruta_Imagen_Base, THE Vista_Configuracion SHALL actualizar la referencia de Imagen_Base_Por_Defecto en la Configuracion_Por_Lado.
7. IF el usuario intenta confirmar cambios cuando una Variante queda sin Ruta_Imagen_Base, sin al menos una Condicion completa, o cuando ninguna Ruta_Imagen_Base está marcada como Imagen_Base_Por_Defecto, THEN THE Vista_Configuracion SHALL rechazar la confirmación, conservar la Configuracion_Por_Lado previamente persistida sin cambios y mostrar un mensaje de error que indique la causa.

### Requisito 7: Previsualizar el lado con su imagen base

**Historia de usuario:** Como diseñador de credenciales, quiero usar el botón de vista previa del diseñador para ver el lado con su imagen base, para confirmar el resultado sin controles adicionales.

#### Criterios de Aceptación

1. WHEN el usuario acciona la Vista_Previa de un Lado, THE Editor_Plantillas SHALL renderizar ese Lado usando como fondo la Imagen_Base_Por_Defecto de su Configuracion_Por_Lado cuando esa configuración existe.
2. WHERE no existe una Configuracion_Por_Lado para un Lado, WHEN el usuario acciona la Vista_Previa de ese Lado, THE Editor_Plantillas SHALL renderizar ese Lado usando la imagen base del diseño almacenada en `Plantilla.recursos`.
3. THE Editor_Plantillas SHALL no agregar botones de vista previa adicionales para mostrar otras Variantes distintas de la Imagen_Base_Por_Defecto.

### Requisito 8: Proveer atributos disponibles para las condiciones

**Historia de usuario:** Como diseñador de credenciales, quiero que el selector de atributo muestre los atributos reales de los registros, para definir condiciones con datos existentes y evitar errores de tecleo.

#### Criterios de Aceptación

1. WHEN la Vista_Configuracion carga el selector de Atributo, THE Vista_Configuracion SHALL poblar las opciones a partir de los Atributos_Disponibles del Cliente en un máximo de 2 segundos, combinando las claves de todas las fuentes en una única lista sin duplicados, comparando las claves sin distinguir mayúsculas de minúsculas y sin considerar espacios circundantes.
2. WHERE el Cliente tiene `known_attributes` en su configuración, THE Vista_Configuracion SHALL incluir entre las opciones de Atributo cada clave de `known_attributes` cuya longitud, tras recortar espacios circundantes, sea de 1 a 100 caracteres, omitiendo las claves vacías.
3. WHERE existen Registros del Cliente con datos, THE Vista_Configuracion SHALL incluir entre las opciones de Atributo cada clave presente en `Registro.datos` cuya longitud, tras recortar espacios circundantes, sea de 1 a 100 caracteres, omitiendo las claves vacías y aquellas ya presentes en las opciones.
4. IF no existen Atributos_Disponibles para el Cliente, THEN THE Vista_Configuracion SHALL permitir al usuario introducir manualmente el nombre del Atributo.
5. IF el usuario introduce manualmente un nombre de Atributo vacío o con una longitud mayor a 100 caracteres tras recortar espacios circundantes, THEN THE Vista_Configuracion SHALL rechazar la entrada, conservar el valor previo del selector y mostrar un mensaje de error que indique que el nombre del Atributo es inválido.

### Requisito 9: Validaciones y casos borde de la selección de imagen

**Historia de usuario:** Como operador de impresión, quiero que el sistema maneje datos faltantes o imágenes inconsistentes de forma predecible, para evitar impresiones incorrectas o interrupciones del flujo.

#### Criterios de Aceptación

1. WHEN el Motor_Seleccion_Imagen compara el valor de un Atributo de un Registro contra el valor de una Condicion, THE Motor_Seleccion_Imagen SHALL comparar ambos valores como texto sin distinguir mayúsculas de minúsculas y eliminando los espacios al inicio y al final de cada valor antes de comparar.
2. IF una Configuracion_Por_Lado contiene una sola Ruta_Imagen_Base, THEN THE Editor_Plantillas SHALL asignar esa Ruta_Imagen_Base directamente como imagen base del Lado sin ejecutar el flujo de Variantes ni evaluar Condicion.
3. IF la Imagen_Base_Por_Defecto de una Configuracion_Por_Lado no puede cargarse al generar el PDF y ninguna Variante coincide, THEN THE Flujo_Impresion SHALL omitir la generación de ese Registro para ese Lado y registrar un error que identifique al Registro y la Ruta_Imagen_Base de forma única, conservando los demás Registros de la cola.
4. WHEN dos Ruta_Imagen_Base de una misma Configuracion_Por_Lado difieren en orientación o en al menos una dimensión (ancho o alto), THE Vista_Configuracion SHALL mostrar, antes de guardar, una advertencia que señale la diferencia detectada y permitir al usuario confirmar o cancelar el guardado.
5. WHILE la Vista_Configuracion permanece abierta sin guardar, THE Vista_Configuracion SHALL descartar los cambios no guardados si el usuario la cierra y SHALL conservar la Configuracion_Por_Lado previamente persistida sin modificaciones.
