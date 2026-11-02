@echo off
chcp 65001 > nul
title SENA - Sistema para Estudiantes: Navegacion y Ahorro

echo.
echo  Iniciando SENA...
echo.

:: Buscar Python: primero en el venv local (si existe), luego en el venv de sena
set LOCAL_VENV=%~dp0venv\Scripts\python.exe
set SENA_VENV=C:\Users\sebas\Downloads\sena\sena\venv\Scripts\python.exe

if exist "%LOCAL_VENV%" (
    set PYTHON=%LOCAL_VENV%
) else if exist "%SENA_VENV%" (
    set PYTHON=%SENA_VENV%
) else (
    echo  [ERROR] No se encontro el entorno virtual.
    echo.
    echo  Crea el entorno virtual ejecutando en esta carpeta:
    echo     python -m venv venv
    echo     venv\Scripts\pip install -r requirements.txt
    echo.
    pause
    exit /b 1
)

:: Cambiarse a la carpeta del proyecto (donde esta manage.py)
cd /d "%~dp0"

:: Aplicar migraciones sin pedir nada
echo  Aplicando migraciones (si las hay)...
"%PYTHON%" manage.py migrate --run-syncdb -v 0 2>&1
if errorlevel 1 (
    echo.
    echo  [ERROR] Fallo al aplicar migraciones. Revisa el error arriba.
    pause
    exit /b 1
)

echo.
echo  ==========================================
echo   App lista en: http://127.0.0.1:8000
echo.
echo   Inicia sesion con tu cuenta o registrate
echo   en http://127.0.0.1:8000/registro/
echo.
echo   Presiona Ctrl+C para detener el servidor.
echo  ==========================================
echo.

:: Iniciar el servidor (no pide ninguna contrasena)
"%PYTHON%" manage.py runserver 127.0.0.1:8000
