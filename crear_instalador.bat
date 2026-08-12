@echo off
setlocal

set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" set "ISCC=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"

if not exist "%ISCC%" (
    echo No se encontro Inno Setup 6.
    echo Instale Inno Setup y vuelva a ejecutar este archivo.
    exit /b 1
)

if not exist "dist\VISUALIA - Nelson Sanchez Dillon.exe" (
    echo Primero se debe generar el EXE de Visualia.
    exit /b 1
)

"%ISCC%" "installer\Visualia.iss"
if errorlevel 1 exit /b 1

echo Instalador generado en dist\installer.
endlocal
