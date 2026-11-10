# Generador de Imágenes por Lote

Aplicación de escritorio para Windows que edita imágenes con OpenAI, trabaja por lotes y puede crear
infografías comerciales con texto exacto agregado localmente.

## Novedades 1.4.0: fichas técnicas y Mis prompts

En **Opciones avanzadas → Configurar fuente**, selecciona un Excel general o una carpeta
con fichas TXT, XLSX, XLSM o CSV (un archivo por producto, también en subcarpetas).
Por ejemplo, `100-9689.txt` corresponde a la imagen `100-9689.jpg`.
Las fichas TXT admiten `Producto: Vaso`, `Material: Vidrio` y texto libre;
las fichas Excel admiten una fila de producto con encabezados o pares Campo/Valor.

El Excel general se identifica por ITEM, SKU o código. Si la estructura es distinta,
indica la hoja, la columna identificadora y la fila de encabezados. Los archivos XLS antiguos
deben convertirse a XLSX. Las fórmulas deben tener sus resultados calculados y guardados.
Usa **Revisar coincidencias y datos** para detectar productos sin ficha o conflictos antes del lote.
Los duplicados y conflictos bloquean la carga; los productos sin ficha utilizan solo el prompt y la imagen.

La ficha completa se combina con tu prompt y las imágenes tanto en vista previa como en lotes.
Elige **Según el prompt**, **Solo referencia** o **Campos seleccionados** para controlar el texto.
Para diseños libres guiados por el prompt, usa **Imagen IA**. La infografía local conserva una
composición fija con espacio limitado; revisa la vista previa antes de generar el lote completo.
ITEM sigue tomando su valor visible del nombre original de la imagen; SKU se conserva por separado.

Pulsa **Guardar prompt**, escribe un nombre y recupéralo desde **Mis prompts**.
Puedes cargarlo para editar, actualizarlo con el mismo nombre, duplicarlo con otro nombre o eliminarlo.
La biblioteca permanece en `%LOCALAPPDATA%\Visualia\prompts.json` al cerrar o actualizar el programa.
Solo se guarda el texto original del usuario, sin los datos de un producto particular.

## Funciones principales

- Entrada JPG, JPEG, PNG, WEBP, BMP, TIF y TIFF, sin distinguir mayúsculas.
- Vista previa pagada reutilizable como primera salida.
- Procesamiento de 1, 5, 10 o todos los productos.
- Modo demostración sin API ni coste.
- Visor Antes/Después durante el lote.
- Agrupación individual, por prefijo/SKU o por subcarpeta.
- Varias fotos de referencia para un mismo producto.
- Importación de datos verificados desde CSV o Excel XLSX.
- Todas las columnas no vacías del Excel se añaden al prompt como datos verificados, incluidos descripción,
  tamaño, piezas, medidas, material, edad, peso, capacidad, modelo, color y campos personalizados.
- Presets: catálogo blanco, escena de uso e infografía comercial.
- Calidad Baja, Media o Alta, seleccionable junto al tamaño antes de generar.
- Selector de modelos de imagen de OpenAI: recomendado (`gpt-image-2.5-sunburst`), versión fija
  (`gpt-image-2.5-sunburst-2026-09-08`), GPT Image 2 y modelos heredados señalados como obsoletos.
- Salida como imagen IA o infografía con texto local exacto.
- Creación independiente de catálogos PDF multipágina con plantillas guardadas.
- Omisión de archivos terminados, versionado, reintentos y cancelación segura.
- Validación básica del PNG y reporte CSV por lote.
- Configuración de API desde la interfaz.
- Presupuesto local con saldo cargado, gasto estimado, proyección y límite automático del lote.

## Instalación y ejecución

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe main.py
```

## Uso básico compatible

1. Selecciona una carpeta de entrada y otra de salida.
2. Escribe el prompt.
3. Elige tamaño, cantidad y salida 1080x1080.
4. Usa **Generar vista previa** o **Generar lote**.

El modo predeterminado sigue tratando cada archivo como un producto independiente.
**Crear catálogo PDF** es una función separada: presenta la página 1 antes de exportar, espera tu
confirmación y luego crea un PDF multipágina. El preset inicial **Animal Planet** usa una cuadrícula
de 2 columnas por 3 filas en A4; puedes modificar título, subtítulo, pie, colores, logo y cuadrícula,
y guardar cada diseño como una plantilla de catálogo independiente.

El catálogo usa las imágenes de la carpeta de entrada y, si está configurada, la fuente de productos
CSV/XLSX. La plantilla Animal Planet muestra por defecto `DESCRIPCION`, `Cub.`, `MARCA`,
`DISPONIBLE`, `Precio`, `EMPAQUE`, `UM`, `CTN` y `CBARRA`; puedes personalizar esta lista en la
plantilla guardada. El precio se muestra en su propia etiqueta y los demás campos aparecen en la
ficha. También puedes añadir una imagen de mascotas al encabezado para acercar la página al diseño
de referencia. Los códigos, precios y valores de inventario se imprimen a partir de los datos, sin
generarlos con IA. También admite CSV guardados en UTF-8 o en la codificación habitual de Windows.
Esta exportación no llama a la API. Si quieres usar fotos previamente editadas con IA, selecciona
como entrada la carpeta donde quedaron guardadas. Las plantillas se conservan en
`%LOCALAPPDATA%\Visualia\catalog_templates.json`.

## Probar sin saldo

### Editar imágenes en varias carpetas

Selecciona la carpeta principal y activa **Editar imágenes de subcarpetas y guardar en editadas**.
Esta opcion esta desactivada por defecto. Procesa cada formato admitido individualmente, incluso en
subcarpetas anidadas, y guarda el resultado en `editadas` junto a su original. En este modo
la carpeta de salida y la agrupacion seleccionadas no se usan para las imagenes.
Las carpetas llamadas `editadas` se excluyen de la entrada. Los originales no se modifican.
`foto.jpg` produce `editadas/foto.png` (o `foto.jpg` si eliges JPG).
Si coexiste `foto.png`, su salida recibe un sufijo como `foto_png_2.png` para evitar colisiones.
Con **Omitir existentes** se saltan las salidas terminadas; en caso contrario se crean versiones
sin sobrescribir resultados. La vista previa tambien se guarda en la carpeta correspondiente.
El reporte conjunto se guarda en `editadas` de la carpeta principal, con las rutas de cada salida.
**Abrir carpeta de salida** abre la carpeta principal en este modo.
Prueba primero con **Modo demostracion**. En unidades de red se necesita acceso de escritura.

Cada tarea conserva `original_path`, `original_filename` e `item_code`. El ITEM se calcula con
`Path.stem`: tanto `LS24-03763.jpg` como `LS24-03763.png` producen `ITEM: LS24-03763`.
Se inyecta explícitamente en el prompt y nunca se obtiene del PNG temporal ni del Excel.
Se respetan las plantillas sin texto; cuando solicitan ITEM, solo se autoriza el valor original.
En agrupaciones intencionales de varias referencias se usa el nombre original de la primera
imagen del grupo (orden alfabético). El modo Individual conserva una tarea por archivo.
Las transparencias se conservan al enviar PNG y se componen sobre blanco al guardar JPG.

Activa **Modo demostración (sin API)**. La aplicación probará carpetas, vista previa, visor, agrupación,
infografías, progreso e informes. Las imágenes llevarán una marca visible y no representan una edición IA.

## Opciones avanzadas

Pulsa **Opciones avanzadas** para configurar:

- **Agrupación Individual:** una salida por archivo.
- **Por prefijo/SKU:** agrupa `SKU_frente.jpg`, `SKU_detalle.jpg` y `SKU_empaque.jpg`.
- **Por subcarpeta:** cada subcarpeta representa un producto.
- **Datos CSV/XLSX:** relaciona la columna `ITEM` (por ejemplo, `100-9689`) con la imagen del mismo nombre (`100-9689.jpg`) y añade descripción, marca, medidas y las demás celdas no vacías como datos verificados.
- El registro muestra **EXCEL OK** cuando encuentra la fila del producto y **AVISO EXCEL** cuando el SKU no coincide.
- **Infografía con texto exacto:** OpenAI crea la base fotográfica; Pillow agrega los textos localmente.
- **Omitir existentes:** permite reanudar sin volver a pagar salidas terminadas.
- **Crear versiones:** genera `_v2`, `_v3`, etc. cuando se vuelve a procesar.

Puedes usar [productos_ejemplo.csv](productos_ejemplo.csv) o crear una plantilla Excel desde la aplicación.
La columna `codigo` debe coincidir con el SKU/prefijo o con el nombre de la subcarpeta.

## Costes

La aplicación recomienda `gpt-image-2.5-sunburst` y también permite fijar el snapshot
`gpt-image-2.5-sunburst-2026-09-08`. Los modelos anteriores aparecen identificados como obsoletos y se conservan
solamente por compatibilidad. El valor mostrado es una estimación: una edición también cobra tokens del
prompt y de las imágenes de entrada. Cuando no existe una tabla específica se usa el costo alternativo
configurado en `.env`.

La vista previa es una llamada real. Cuando se aprueba, se reutiliza para evitar una segunda llamada del
primer producto. El redimensionamiento e infografía local no añaden coste API.

## Configuración API

Desde **Opciones avanzadas → Configurar API**, introduce la clave y el modelo. Se guardan localmente en
`.env`, junto a la aplicación. El archivo está excluido por `.gitignore` y nunca se incluye en el EXE.

Configuración manual alternativa:

```env
OPENAI_API_KEY=sk-...
OPENAI_IMAGE_MODEL=gpt-image-2.5-sunburst
ESTIMATED_COST_PER_IMAGE_USD=0.06
```

## Reportes y errores

Cada lote crea `reporte_lote_YYYYMMDD_HHMMSS.csv` con producto, referencias, salida, estado, error, modelo,
calidad, tamaño, coste estimado y duración. Los errores individuales no detienen el resto del lote.

## Crear EXE

```powershell
.\build_exe.bat
```

Para esta versión el ejecutable queda en `dist\1.4.4`. El script no copia `.env`; configura la clave
desde la aplicación.

## Crear instalador profesional de Windows

El proyecto incluye un asistente Inno Setup con licencia, imágenes de Visualia, selección de carpeta,
acceso directo opcional, menú Inicio y desinstalador.

```powershell
.\crear_instalador.bat
```

El resultado queda en `dist\installer\Instalador_VISUALIA_1.4.4.exe`. La configuración privada y la clave API
se guardan en `%LOCALAPPDATA%\Visualia\.env`; no se incluyen en el instalador y se conservan al actualizar.

## Pruebas

```powershell
.\.venv\Scripts\python.exe -m unittest -v test_catalog_core.py
```

Al actualizar se conserva el modelo guardado. Para usar GPT Image 2.5, selecciona **Recomendado · gpt-image-2.5-sunburst**. Para este modelo se usa el costo por imagen configurado como estimación orientativa, no una tarifa oficial por imagen.
