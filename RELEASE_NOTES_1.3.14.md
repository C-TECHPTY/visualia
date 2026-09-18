# Visualia 1.3.14

- Corrige el filtro exclusivo JPG/JPEG del modo de subcarpetas: admite JPG, JPEG, PNG,
  WEBP, BMP, TIF y TIFF, incluyendo extensiones en mayúsculas.
- Conserva la ruta, nombre original e ITEM por tarea; inserta el ITEM calculado con
  Path.stem en el prompt, con prioridad sobre nombres temporales y datos del Excel.
  Conserva las plantillas que no solicitan texto.
- Separa archivos de igual nombre base en modo Individual y evita colisiones de salida.
- Conserva alpha en PNG y utiliza fondo blanco al convertir transparencias a JPG/A4.
- Amplía el registro con identidad original, ITEM, temporales, salida y estado.
- Mantiene interfaz, agrupaciones explícitas, configuración, costos y distribución existentes.

Causa diagnosticada: el prompt no incluía una fuente programática para ITEM y podía prohibirlo
al añadir Excel. El código no permite atribuir el ejemplo 1750242553a.png a un timestamp local;
los temporales de entrada usan el patrón nombre_índice_api.png. La exclusión de PNG sí se
reproduce directamente por el filtro JPG/JPEG del modo de subcarpetas.

Validación: 17 pruebas automatizadas aprobadas, incluyendo formatos, nombres, prompt enviado
a API simulada, vista previa, transparencias, errores/reintentos, progreso, colisiones,
reanudar y conservación de originales. No se realizaron generaciones pagadas.

Descarga y ejecuta Instalador_VISUALIA_1.3.14.exe para actualizar.
