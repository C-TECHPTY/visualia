@echo off
setlocal

if not exist ".venv\Scripts\python.exe" (
    echo No se encontro el entorno virtual .venv.
    exit /b 1
)

.venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 exit /b 1

.venv\Scripts\python.exe -m PyInstaller --noconfirm --onefile --windowed --name "VISUALIA 1.4.4 - Nelson Sanchez Dillon" --distpath "dist\1.4.4" --workpath "build\1.4.4" --icon "assets\visualia.ico" --add-data "assets;assets" main.py
if errorlevel 1 exit /b 1

copy /Y ".env.example" "dist\1.4.4\.env.example" >nul

echo.
echo EXE generado en dist\1.4.4.
echo Usa Configurar API dentro del programa para agregar tu clave.
pause
