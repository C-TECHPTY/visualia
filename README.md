# Generador de Imágenes por Lote

Aplicación de escritorio para Windows que edita imágenes con OpenAI, trabaja por lotes y puede crear
infografías comerciales con texto exacto agregado localmente.

## Funciones principales

- Entrada JPG, PNG y WEBP.
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
- Selector de modelo Económico (`gpt-image-1-mini`) o Profesional (`gpt-image-2`).
- Salida como imagen IA o infografía con texto local exacto.
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

## Probar sin saldo

Activa **Modo demostración (sin API)**. La aplicación probará carpetas, vista previa, visor, agrupación,
infografías, progreso e informes. Las imágenes llevarán una marca visible y no representan una edición IA.

## Opciones avanzadas

Pulsa **Opciones avanzadas** para configurar:

- **Agrupación Individual:** una salida por archivo.
- **Por prefijo/SKU:** agrupa `SKU_frente.jpg`, `SKU_detalle.jpg` y `SKU_empaque.jpg`.
- **Por subcarpeta:** cada subcarpeta representa un producto.
- **Datos CSV/XLSX:** añade nombre, marca, subtítulo y beneficios verificados.
- El registro muestra **EXCEL OK** cuando encuentra la fila del producto y **AVISO EXCEL** cuando el SKU no coincide.
- **Infografía con texto exacto:** OpenAI crea la base fotográfica; Pillow agrega los textos localmente.
- **Omitir existentes:** permite reanudar sin volver a pagar salidas terminadas.
- **Crear versiones:** genera `_v2`, `_v3`, etc. cuando se vuelve a procesar.

Puedes usar [productos_ejemplo.csv](productos_ejemplo.csv) o crear una plantilla Excel desde la aplicación.
La columna `codigo` debe coincidir con el SKU/prefijo o con el nombre de la subcarpeta.

## Costes

La aplicación usa `gpt-image-1-mini` y su tabla oficial para Baja, Media y Alta. El valor mostrado es
una estimación: una edición también cobra tokens del prompt y de las imágenes de entrada. Auto usa el valor
alternativo configurado en `.env`.

La vista previa es una llamada real. Cuando se aprueba, se reutiliza para evitar una segunda llamada del
primer producto. El redimensionamiento e infografía local no añaden coste API.

## Configuración API

Desde **Opciones avanzadas → Configurar API**, introduce la clave y el modelo. Se guardan localmente en
`.env`, junto a la aplicación. El archivo está excluido por `.gitignore` y nunca se incluye en el EXE.

Configuración manual alternativa:

```env
OPENAI_API_KEY=sk-...
OPENAI_IMAGE_MODEL=gpt-image-1-mini
ESTIMATED_COST_PER_IMAGE_USD=0.06
```

## Reportes y errores

Cada lote crea `reporte_lote_YYYYMMDD_HHMMSS.csv` con producto, referencias, salida, estado, error, modelo,
calidad, tamaño, coste estimado y duración. Los errores individuales no detienen el resto del lote.

## Crear EXE

```powershell
.\build_exe.bat
```

El ejecutable queda en `dist`. El script no copia `.env`; configura la clave desde la aplicación o copia
`.env.example` como `.env` dentro de `dist`.

## Crear instalador profesional de Windows

El proyecto incluye un asistente Inno Setup con licencia, imágenes de Visualia, selección de carpeta,
acceso directo opcional, menú Inicio y desinstalador.

```powershell
.\crear_instalador.bat
```

El resultado queda en `dist\installer\Instalador_VISUALIA_1.0.0.exe`. La configuración privada y la clave API
se guardan en `%LOCALAPPDATA%\Visualia\.env`; no se incluyen en el instalador y se conservan al actualizar.

## Pruebas

```powershell
.\.venv\Scripts\python.exe -m unittest -v test_catalog_core.py
```
