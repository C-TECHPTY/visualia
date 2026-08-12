@echo off
setlocal

if not exist ".venv\Scripts\python.exe" (
    echo No se encontro el entorno virtual .venv.
    exit /b 1
)

.venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 exit /b 1

.venv\Scripts\python.exe -m PyInstaller --noconfirm --onefile --windowed --name "Generador de Imagenes por Lote" --icon "assets\visualia.ico" --add-data "assets;assets" main.py
if errorlevel 1 exit /b 1

copy /Y ".env.example" "dist\.env.example" >nul

echo.
echo EXE generado en la carpeta dist.
echo Copia dist\.env.example como dist\.env o usa Configurar API dentro del programa.
pause
