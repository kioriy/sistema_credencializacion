# Requirements Document

## Introduction

El **multiplantillaje base** permite que un mismo punto de configuración asocie varias plantillas (diseños) a un cliente y seleccione automáticamente, para cada registro a imprimir, qué plantilla base (imagen de fondo y elementos de frente/vuelta) corresponde, en función del valor de un atributo del registro.

Hoy el flujo de impresión usa una sola plantilla para toda la cola: el usuario elige una plantilla en el Panel de Control y el Centro de Impresión renderiza todos los registros con la plantilla del primer ítem de la cola. Con esta funcionalidad, el sistema evalúa un conjunto de reglas, donde cada regla combina una o más condiciones del tipo "atributo igual a valor" en conjunción lógica (Y), por ejemplo `grado == 1 Y grupo == "A"`, `grado == 1 Y grupo == "B"`, o una condición simple `grado == 1`. El sistema asigna a cada registro la plantilla destino indicada por la primera regla cuyas condiciones se cumplen todas, con una plantilla por defecto cuando ninguna regla coincide.

La funcionalidad incluye: (1) un diálogo de configuración que lista las plantillas/diseños disponibles del cliente, muestra una vista previa del diseño base de cada plantilla seleccionada y permite, en la misma fila de cada plantilla, capturar las condiciones (atributo y valor) que la activan; (2) la persistencia de esa configuración como una única Configuracion_Multiplantillaje por cliente que el flujo de impresión pueda leer; (3) un botón de configuración (icono de engranaje) ubicado junto a la vista previa individual de frente/vuelta en el Editor de Plantillas; y (4) la evaluación automática de las reglas durante el armado de la cola y/o la generación del PDF.

El flujo de configuración soporta continuación y reentrada: la selección base del conjunto de plantillas no queda bloqueada hasta que se guarda, y una configuración guardada puede estar parcialmente completa (con plantillas aún sin condiciones), permitiendo seguir asignándolas más tarde desde el Boton_Configuracion.

## Glossary

- **Editor_Plantillas**: Vista de edición de plantillas (`template_editor.py`) donde se asigna la imagen base por lado (frente/vuelta) y donde residen los encabezados "FRENTE"/"VUELTA" con su botón de vista previa individual.
- **Boton_Configuracion**: Control de interfaz que muestra únicamente el icono de engranaje (estilo `qtawesome fa5s.cog`), ubicado junto al botón de vista previa individual de cada lado en el Editor_Plantillas, que abre el Dialogo_Multiplantillaje.
- **Dialogo_Multiplantillaje**: Ventana modal que lista las plantillas/diseños disponibles del cliente, muestra una Vista_Previa_Diseno de cada plantilla seleccionada y permite crear o editar la única Configuracion_Multiplantillaje del cliente asignando condiciones por atributo en la fila de cada plantilla.
- **Configuracion_Multiplantillaje**: Conjunto persistido, único por cliente, que agrupa las reglas de asignación de plantilla base de un cliente, más la referencia a la Plantilla_Por_Defecto. Un cliente tiene como máximo una Configuracion_Multiplantillaje, independientemente del número de plantillas que contenga.
- **Regla_Asignacion**: Unidad de la Configuracion_Multiplantillaje compuesta por una o más Condicion_Asignacion que deben cumplirse todas (conjunción lógica Y), asociada a una Plantilla_Destino. Se expresa como "Condicion_Asignacion [Y Condicion_Asignacion]... → Plantilla_Destino".
- **Condicion_Asignacion**: Elemento de una Regla_Asignacion compuesto por un Atributo, un operador de igualdad y un valor. Se expresa como "atributo igual a valor". Una Regla_Asignacion coincide únicamente cuando todas sus Condicion_Asignacion se cumplen.
- **Vista_Previa_Diseno**: Representación visual del diseño base de una plantilla (imagen de fondo almacenada en `Plantilla.recursos` como `fondo_frente`/`fondo_vuelta`) mostrada en el Dialogo_Multiplantillaje junto a la plantilla correspondiente.
- **Plantilla_Destino**: Plantilla seleccionada como resultado de una Regla_Asignacion coincidente para un registro.
- **Plantilla_Por_Defecto**: Plantilla que el sistema asigna a un registro cuando ninguna Regla_Asignacion coincide.
- **Atributo**: Clave de los datos dinámicos de un registro (`Registro.datos`, por ejemplo `grado`, `grupo`, `nivel_escolar`) usada como criterio de una Regla_Asignacion.
- **Atributos_Disponibles**: Conjunto de claves de atributo ofrecidas al usuario en el Dialogo_Multiplantillaje, derivado de `Cliente.config["known_attributes"]` y/o de las claves presentes en `Registro.datos`.
- **Flujo_Impresion**: Proceso que arma la cola de impresión (`control_panel.py`) y genera el PDF (`print_center.py` + `pdf_engine.py`), incluyendo la asignación de `plantilla_id` por cada ItemCola.
- **Motor_Asignacion**: Componente lógico que, dado un registro y una Configuracion_Multiplantillaje, evalúa las reglas y devuelve la plantilla asignada.
- **Cliente**: Organización propietaria de registros y plantillas (`models.py:Cliente`).
- **Registro**: Sujeto individual de una credencial con datos dinámicos en `Registro.datos` (`models.py:Registro`).
- **Plantilla**: Definición visual de un diseño perteneciente a un Cliente (`models.py:Plantilla`).

## Requirements

### Requisito 1: Abrir la configuración de multiplantillaje desde el Editor de Plantillas

**Historia de usuario:** Como diseñador de credenciales, quiero un botón de engranaje junto a la vista previa individual de cada lado, para acceder rápidamente a la configuración de multiplantillaje desde el Editor de Plantillas.

#### Criterios de Aceptación

1. THE Editor_Plantillas SHALL mostrar un Boton_Configuracion con el icono de engranaje adyacente al botón de vista previa individual de cada lado (frente y vuelta), uno por cada lado.
2. THE Boton_Configuracion SHALL mostrar únicamente el icono de engranaje, sin texto de etiqueta visible.
3. WHEN el usuario activa el Boton_Configuracion estando la plantilla asociada a un Cliente identificable, THE Editor_Plantillas SHALL abrir el Dialogo_Multiplantillaje para el Cliente de la plantilla en edición en un máximo de 1 segundo.
4. WHEN el usuario mantiene el puntero sobre el Boton_Configuracion durante al menos 1 segundo, THE Editor_Plantillas SHALL mostrar un texto de ayuda que identifique la acción de configurar el multiplantillaje.
5. IF la plantilla en edición no está asociada a un Cliente identificable, THEN THE Editor_Plantillas SHALL mantener el Boton_Configuracion deshabilitado y mostrar, al situar el puntero sobre él durante al menos 1 segundo, un texto de ayuda que indique que se requiere guardar la plantilla antes de configurar el multiplantillaje.
6. IF el usuario activa el Boton_Configuracion y el Dialogo_Multiplantillaje no puede abrirse, THEN THE Editor_Plantillas SHALL mostrar un mensaje de error que indique que no se pudo abrir la configuración de multiplantillaje y mantener el Editor_Plantillas en su estado actual sin cambios.

### Requisito 2: Listar diseños disponibles y seleccionar varias plantillas

**Historia de usuario:** Como diseñador de credenciales, quiero ver la lista de diseños disponibles del cliente y seleccionar varios, para incluirlos en la configuración de multiplantillaje.

#### Criterios de Aceptación

1. WHEN el Dialogo_Multiplantillaje se abre, THE Dialogo_Multiplantillaje SHALL listar las plantillas que pertenecen al Cliente de la plantilla en edición y completar la carga de la lista en un máximo de 3 segundos.
2. WHEN el Dialogo_Multiplantillaje se abre, THE Dialogo_Multiplantillaje SHALL mostrar de forma visible el nombre de cada plantilla listada.
3. WHEN el usuario selecciona una plantilla de la lista, THE Dialogo_Multiplantillaje SHALL mostrar una Vista_Previa_Diseno del diseño base de esa plantilla, obtenida de la imagen de fondo almacenada en `Plantilla.recursos`, junto a la plantilla seleccionada.
4. IF la imagen de fondo de una plantilla seleccionada no está disponible en `Plantilla.recursos`, THEN THE Dialogo_Multiplantillaje SHALL mostrar un indicador de vista previa no disponible para esa plantilla y SHALL permitir continuar con la configuración de la plantilla.
5. THE Dialogo_Multiplantillaje SHALL permitir al usuario seleccionar una o más plantillas de la lista para incluirlas en la Configuracion_Multiplantillaje.
6. IF el Cliente tiene una sola plantilla disponible, THEN THE Dialogo_Multiplantillaje SHALL mostrar un mensaje que indique que se requieren al menos dos plantillas para configurar el multiplantillaje.
7. IF la carga de la lista de plantillas del Cliente falla, THEN THE Dialogo_Multiplantillaje SHALL mostrar un mensaje de error que indique el fallo de la carga y SHALL mantener deshabilitada la acción de guardar la Configuracion_Multiplantillaje.
8. WHILE el usuario no ha seleccionado al menos una plantilla destino, THE Dialogo_Multiplantillaje SHALL mantener deshabilitada la acción de guardar la Configuracion_Multiplantillaje.

### Requisito 3: Definir reglas de asignación con condiciones compuestas por atributo

**Historia de usuario:** Como diseñador de credenciales, quiero asignar a cada diseño seleccionado una o más condiciones sobre atributos del registro que deban cumplirse en conjunto, para que el sistema use una plantilla solo cuando coincidan combinaciones como "grado=1 Y grupo=A".

#### Criterios de Aceptación

1. WHEN el usuario selecciona una plantilla destino en el Dialogo_Multiplantillaje, THE Dialogo_Multiplantillaje SHALL permitir definir una Regla_Asignacion compuesta por una o más Condicion_Asignacion, donde cada Condicion_Asignacion incluye un Atributo, un operador de igualdad y un valor de hasta 255 caracteres.
2. THE Dialogo_Multiplantillaje SHALL permitir capturar el Atributo y el valor de cada Condicion_Asignacion en la misma fila que la plantilla destino correspondiente.
3. THE Dialogo_Multiplantillaje SHALL permitir agregar y quitar Condicion_Asignacion dentro de una misma Regla_Asignacion, manteniendo al menos una Condicion_Asignacion por regla.
4. THE Dialogo_Multiplantillaje SHALL ofrecer la selección del Atributo de cada Condicion_Asignacion a partir de los Atributos_Disponibles del Cliente.
5. IF los Atributos_Disponibles del Cliente están vacíos, THEN THE Dialogo_Multiplantillaje SHALL impedir la creación de la Condicion_Asignacion mediante selector y mostrar un mensaje que indique que no existen atributos disponibles.
6. WHEN el usuario selecciona un Atributo para una Condicion_Asignacion, THE Dialogo_Multiplantillaje SHALL permitir especificar el valor que dispara la condición, con una longitud mínima de 1 carácter y máxima de 255 caracteres.
7. THE Dialogo_Multiplantillaje SHALL representar cada Regla_Asignacion como la conjunción de sus Condicion_Asignacion en la forma "Atributo igual a valor [Y Atributo igual a valor]... asigna Plantilla_Destino".
8. IF el usuario intenta guardar una Regla_Asignacion en la que alguna Condicion_Asignacion carece de Atributo o de valor, THEN THE Dialogo_Multiplantillaje SHALL rechazar el guardado, conservar los datos ya ingresados sin alterarlos y mostrar un mensaje que indique cada campo faltante.
9. IF el usuario intenta guardar una Regla_Asignacion cuyo conjunto de Condicion_Asignacion (pares Atributo y valor) coincide con el conjunto de Condicion_Asignacion de una Regla_Asignacion ya existente en la Configuracion_Multiplantillaje, THEN THE Dialogo_Multiplantillaje SHALL rechazar el guardado y mostrar un mensaje que indique la regla duplicada.
10. THE Dialogo_Multiplantillaje SHALL permitir designar exactamente una de las plantillas como Plantilla_Por_Defecto de la Configuracion_Multiplantillaje.

### Requisito 4: Persistir la configuración de multiplantillaje

**Historia de usuario:** Como usuario del sistema, quiero que exista una única configuración de multiplantillaje por cliente que se cree o actualice al guardar, para que el flujo de impresión la utilice sin generar configuraciones duplicadas.

#### Criterios de Aceptación

1. WHEN el usuario confirma el guardado en el Dialogo_Multiplantillaje, THE Configuracion_Multiplantillaje SHALL persistirse como la única configuración asociada al Cliente, creándola si no existe o actualizándola si ya existe, sin generar una Configuracion_Multiplantillaje adicional para ese Cliente.
2. THE Configuracion_Multiplantillaje SHALL mantener una relación de a lo sumo una configuración por Cliente, de modo que incluir varias plantillas en la configuración no produzca varias Configuracion_Multiplantillaje.
3. WHEN el usuario guarda una Configuracion_Multiplantillaje para un Cliente que ya tiene una, THE Configuracion_Multiplantillaje SHALL actualizar la configuración existente agregando o modificando sus Regla_Asignacion en lugar de crear una nueva.
4. THE Configuracion_Multiplantillaje SHALL almacenar la lista de Regla_Asignacion (de 0 a un máximo de 100 reglas), cada una con una o más Condicion_Asignacion, y una referencia obligatoria a la Plantilla_Por_Defecto.
5. WHEN la persistencia de la Configuracion_Multiplantillaje finaliza correctamente, THE Dialogo_Multiplantillaje SHALL mostrar una confirmación visible de guardado exitoso al usuario.
6. WHEN el Dialogo_Multiplantillaje se abre para un Cliente que ya tiene una Configuracion_Multiplantillaje, THE Dialogo_Multiplantillaje SHALL cargar y mostrar la lista completa de Regla_Asignacion con sus Condicion_Asignacion y la Plantilla_Por_Defecto previamente guardadas.
7. THE Configuracion_Multiplantillaje SHALL ser legible por el Flujo_Impresion para resolver la plantilla de cada Registro.
8. IF la persistencia de la Configuracion_Multiplantillaje falla, THEN THE Dialogo_Multiplantillaje SHALL conservar sin modificaciones los cambios mostrados en pantalla y SHALL mostrar un mensaje de error que indique la causa del fallo.
9. IF la carga de una Configuracion_Multiplantillaje existente falla al abrir el Dialogo_Multiplantillaje, THEN THE Dialogo_Multiplantillaje SHALL mostrar un mensaje de error que indique la causa del fallo y SHALL abrirse sin reglas precargadas.

### Requisito 5: Asignar automáticamente la plantilla por registro durante el flujo de impresión

**Historia de usuario:** Como operador de impresión, quiero que cada registro reciba automáticamente la plantilla base correcta según su atributo, para imprimir lotes mixtos sin asignar plantilla manualmente registro por registro.

#### Criterios de Aceptación

1. WHERE existe una Configuracion_Multiplantillaje para el Cliente, WHEN el Flujo_Impresion procesa un Registro, THE Motor_Asignacion SHALL evaluar las Regla_Asignacion contra los datos del Registro siguiendo el orden definido en la Configuracion_Multiplantillaje.
2. WHEN todas las Condicion_Asignacion de una Regla_Asignacion se cumplen para un Registro, donde cada Condicion_Asignacion se cumple si el valor de su Atributo en el Registro coincide con el valor de la condición (comparación sin distinción de mayúsculas/minúsculas y sin considerar espacios en blanco iniciales o finales), THE Motor_Asignacion SHALL asignar la Plantilla_Destino de esa regla al Registro.
3. IF al menos una Condicion_Asignacion de una Regla_Asignacion no se cumple para un Registro, THEN THE Motor_Asignacion SHALL tratar esa Regla_Asignacion como no coincidente para ese Registro.
4. IF ninguna Regla_Asignacion coincide con los datos del Registro, THEN THE Motor_Asignacion SHALL asignar la Plantilla_Por_Defecto al Registro.
5. WHEN los datos de un Registro hacen coincidir más de una Regla_Asignacion, THE Motor_Asignacion SHALL asignar la Plantilla_Destino de la primera regla coincidente según el orden definido en la Configuracion_Multiplantillaje.
6. WHEN el Flujo_Impresion arma la cola de impresión, THE Flujo_Impresion SHALL registrar en cada ItemCola la plantilla asignada por el Motor_Asignacion para el Registro correspondiente.
7. WHEN el Flujo_Impresion genera el PDF de una cola, THE Flujo_Impresion SHALL renderizar cada Registro con la imagen base y los elementos de frente y vuelta de la plantilla asignada a ese Registro.
8. WHERE no existe una Configuracion_Multiplantillaje para el Cliente, THE Flujo_Impresion SHALL conservar el comportamiento actual de usar la plantilla seleccionada para todos los registros de la cola.
9. IF ninguna Regla_Asignacion coincide y no existe una Plantilla_Por_Defecto configurada en la Configuracion_Multiplantillaje, THEN THE Motor_Asignacion SHALL dejar el Registro sin plantilla asignada y registrar una indicación de error que identifique el Registro afectado, conservando los datos del Registro sin modificación.
10. IF la plantilla asignada a un Registro no puede cargarse al generar el PDF (imagen base o elementos de frente o vuelta no disponibles), THEN THE Flujo_Impresion SHALL omitir la generación de ese Registro y presentar una indicación de error que identifique el Registro y la plantilla afectados, continuando con los Registros restantes de la cola.

### Requisito 6: Editar una configuración de multiplantillaje existente

**Historia de usuario:** Como diseñador de credenciales, quiero modificar una configuración guardada cambiando un parámetro o reemplazando una plantilla, para mantener el multiplantillaje actualizado cuando cambian los criterios.

#### Criterios de Aceptación

1. WHEN el usuario edita una Regla_Asignacion existente en el Dialogo_Multiplantillaje, THE Dialogo_Multiplantillaje SHALL permitir cambiar el Atributo o el valor de cualquiera de sus Condicion_Asignacion o la Plantilla_Destino de esa regla, conservando sin cambios los demás campos no editados de esa misma regla.
2. WHEN el usuario reemplaza la Plantilla_Destino de una Regla_Asignacion, THE Dialogo_Multiplantillaje SHALL actualizar la regla con la nueva plantilla manteniendo el resto de la Configuracion_Multiplantillaje.
3. THE Dialogo_Multiplantillaje SHALL permitir eliminar una Regla_Asignacion de la Configuracion_Multiplantillaje.
4. IF el usuario intenta confirmar los cambios cuando el valor o el Atributo de una Condicion_Asignacion editada está vacío o cuando la Plantilla_Destino de una Regla_Asignacion no referencia una plantilla existente, THEN THE Dialogo_Multiplantillaje SHALL rechazar la confirmación, mantener sin cambios la Configuracion_Multiplantillaje previamente persistida y mostrar un mensaje de error que indique el campo inválido.
5. WHEN el usuario confirma los cambios de edición y todas las Condicion_Asignacion editadas tienen Atributo y valor no vacíos y cada Regla_Asignacion tiene una Plantilla_Destino existente, THE Configuracion_Multiplantillaje SHALL persistir la versión actualizada asociada al Cliente dentro de 2 segundos.
6. IF la persistencia de la Configuracion_Multiplantillaje actualizada falla, THEN THE Dialogo_Multiplantillaje SHALL conservar la versión previamente persistida sin modificaciones y mostrar un mensaje de error que indique que los cambios no se guardaron.
7. WHEN el usuario cambia la Plantilla_Por_Defecto, THE Dialogo_Multiplantillaje SHALL actualizar la referencia de Plantilla_Por_Defecto en la Configuracion_Multiplantillaje.

### Requisito 7: Proveer atributos y valores disponibles para la configuración

**Historia de usuario:** Como diseñador de credenciales, quiero que el selector de atributo me muestre los atributos reales de los registros, para configurar reglas con datos existentes y evitar errores de tecleo.

#### Criterios de Aceptación

1. WHEN el Dialogo_Multiplantillaje carga el selector de Atributo, THE Dialogo_Multiplantillaje SHALL poblar las opciones a partir de los Atributos_Disponibles del Cliente en un tiempo máximo de 2 segundos, combinando las claves de todas las fuentes en una única lista sin duplicados, comparando las claves de forma insensible a mayúsculas/minúsculas y a espacios circundantes.
2. WHERE el Cliente tiene `known_attributes` en su configuración, THE Dialogo_Multiplantillaje SHALL incluir entre las opciones de Atributo cada clave de `known_attributes` cuya longitud, tras recortar espacios circundantes, sea de 1 a 100 caracteres, omitiendo las claves vacías.
3. WHERE existen registros del Cliente con datos, THE Dialogo_Multiplantillaje SHALL incluir entre las opciones de Atributo cada clave presente en `Registro.datos` cuya longitud, tras recortar espacios circundantes, sea de 1 a 100 caracteres, omitiendo las claves vacías y aquellas ya presentes en las opciones.
4. IF no existen Atributos_Disponibles para el Cliente, THEN THE Dialogo_Multiplantillaje SHALL permitir al usuario introducir manualmente el nombre del Atributo.
5. IF el usuario introduce manualmente un nombre de Atributo vacío o con una longitud mayor a 100 caracteres tras recortar espacios circundantes, THEN THE Dialogo_Multiplantillaje SHALL rechazar la entrada, conservar el valor previo del selector y mostrar un mensaje de error indicando que el nombre del Atributo es inválido.

### Requisito 8: Validaciones y casos borde

**Historia de usuario:** Como operador de impresión, quiero que el sistema maneje datos faltantes o inconsistentes de forma predecible, para evitar impresiones incorrectas o interrupciones del flujo.

#### Criterios de Aceptación

1. IF un Registro no contiene el Atributo evaluado por una Condicion_Asignacion de una Regla_Asignacion, THEN THE Motor_Asignacion SHALL tratar esa Condicion_Asignacion como no cumplida y, en consecuencia, esa Regla_Asignacion como no coincidente para ese Registro, continuando la evaluación con las Regla_Asignacion restantes sin interrumpir el procesamiento del Registro.
2. IF ninguna Regla_Asignacion coincide con los datos del Registro, THEN THE Motor_Asignacion SHALL asignar la Plantilla_Por_Defecto al Registro.
3. IF la Plantilla_Por_Defecto no está definida, ninguna Regla_Asignacion coincide para un Registro y existe una plantilla seleccionada en la cola, THEN THE Flujo_Impresion SHALL asignar la plantilla seleccionada en la cola a ese Registro y registrar una advertencia que identifique al Registro de forma única.
4. IF la Plantilla_Por_Defecto no está definida, ninguna Regla_Asignacion coincide para un Registro y no existe una plantilla seleccionada en la cola, THEN THE Flujo_Impresion SHALL omitir la impresión de ese Registro y registrar un error que identifique al Registro de forma única, conservando los demás Registros de la cola.
5. WHEN el usuario selecciona como Plantilla_Destino una plantilla que pertenece a un Cliente distinto del Cliente en edición, THE Dialogo_Multiplantillaje SHALL rechazar la selección, conservar la selección previa y mostrar un mensaje que indique que solo se permiten plantillas del mismo Cliente.
6. IF una plantilla referenciada por una Regla_Asignacion ya no existe al momento de imprimir, THEN THE Motor_Asignacion SHALL asignar la Plantilla_Por_Defecto al Registro y registrar una advertencia que identifique la Regla_Asignacion afectada.
7. WHEN dos plantillas mapeadas en la Configuracion_Multiplantillaje difieren en orientación o en al menos una dimensión de lienzo (ancho o alto), THE Dialogo_Multiplantillaje SHALL mostrar, antes de guardar, una advertencia que señale la diferencia detectada y permitir al usuario confirmar o cancelar el guardado.
8. WHEN el Motor_Asignacion evalúa el valor de un Atributo de un Registro contra el valor de una Condicion_Asignacion, THE Motor_Asignacion SHALL comparar ambos valores como texto sin distinguir mayúsculas de minúsculas y eliminando los espacios al inicio y al final de cada valor antes de comparar.

### Requisito 9: Continuación y reentrada del flujo de configuración

**Historia de usuario:** Como diseñador de credenciales, quiero poder cerrar la ventana de asignación sin perder la posibilidad de reelegir plantillas y poder completar más tarde las plantillas que dejé sin condiciones, para configurar el multiplantillaje de forma gradual sin quedar bloqueado.

#### Criterios de Aceptación

1. WHEN el usuario cierra el Dialogo_Multiplantillaje sin guardar la Configuracion_Multiplantillaje, THE Dialogo_Multiplantillaje SHALL descartar los cambios no guardados y SHALL permitir al usuario volver a seleccionar plantillas desde la selección base en la siguiente apertura.
2. WHILE el usuario no ha guardado la Configuracion_Multiplantillaje, THE Dialogo_Multiplantillaje SHALL mantener disponible la modificación de la selección base de plantillas sin bloquearla.
3. WHEN el usuario guarda una Configuracion_Multiplantillaje en la que una o más plantillas seleccionadas quedaron sin Condicion_Asignacion asignada, THE Configuracion_Multiplantillaje SHALL persistirse como configuración parcialmente completa conservando las plantillas sin condiciones para asignarlas posteriormente.
4. WHEN el usuario vuelve a abrir el Dialogo_Multiplantillaje mediante el Boton_Configuracion para una Configuracion_Multiplantillaje parcialmente completa, THE Dialogo_Multiplantillaje SHALL mostrar las plantillas que aún no tienen Condicion_Asignacion y SHALL permitir asignarles condiciones y guardar la configuración actualizada.
5. THE Dialogo_Multiplantillaje SHALL indicar de forma visible cuáles plantillas de la Configuracion_Multiplantillaje carecen de Condicion_Asignacion asignada.
6. WHEN el usuario agrega Condicion_Asignacion a una plantilla previamente sin condiciones y guarda, THE Configuracion_Multiplantillaje SHALL actualizar esa plantilla con sus nuevas Condicion_Asignacion conservando sin cambios el resto de la configuración.
