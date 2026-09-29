# Visualia 1.4.0

- Fuentes de productos desde Excel general (XLSX/XLSM/CSV) o carpetas de fichas TXT/Excel, incluidas subcarpetas.
- Asociación por ITEM/SKU/código; en carpetas, un archivo por producto con el código como nombre.
- Detección de encabezados, lectura de varias hojas y selección manual de hoja, columna identificadora y fila de encabezados.
- Fichas Excel horizontales o verticales Campo/Valor. TXT con campos `Nombre: valor` o texto libre.
- Revisión de coincidencias y datos antes del lote. Los identificadores duplicados o en conflicto bloquean la carga.
- La ficha completa acompaña al prompt: descripción, producto, características, tamaño, peso, material, empaque y EAN, entre otros.
- Uso de datos según el prompt, solo como referencia o limitado a campos seleccionados para texto.
- Biblioteca local de prompts: guardar, cargar, actualizar, duplicar con otro nombre y eliminar.
- Versión visible en el título y encabezado de la aplicación; instalador actualizado a 1.4.0.

Los prompts se conservan en `%LOCALAPPDATA%\Visualia\prompts.json`. Se guarda el texto del usuario, sin datos específicos del producto ni claves API.

Los XLS antiguos deben convertirse a XLSX. Se conservan ceros iniciales escritos como texto o con formato numérico de ceros; no es posible recuperar ceros ya perdidos en el archivo. Las fórmulas requieren valores calculados guardados por Excel. La infografía local conserva su diseño fijo y espacio limitado: para composiciones libres guiadas por el prompt, usar Imagen IA y revisar una vista previa.
