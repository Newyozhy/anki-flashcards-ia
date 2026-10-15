@echo off
setlocal enabledelayedexpansion
title AnkiCraft AI - Gestor de Modelos Locales Ollama
color 0D

cd /d "%~dp0"

:: -------------------------------------------------------------
:: 1. Verificacion de ejecutable Ollama y Windows Terminal
:: -------------------------------------------------------------
set "OLLAMA_CMD=ollama"
where ollama >nul 2>&1
if %errorlevel% equ 0 goto :check_wt

if exist "%LOCALAPPDATA%\Programs\Ollama\ollama.exe" (
    set "OLLAMA_CMD=%LOCALAPPDATA%\Programs\Ollama\ollama.exe"
    goto :check_wt
)
if exist "%USERPROFILE%\AppData\Local\Programs\Ollama\ollama.exe" (
    set "OLLAMA_CMD=%USERPROFILE%\AppData\Local\Programs\Ollama\ollama.exe"
    goto :check_wt
)
if exist "C:\Users\Manolo\AppData\Local\Programs\Ollama\ollama.exe" (
    set "OLLAMA_CMD=C:\Users\Manolo\AppData\Local\Programs\Ollama\ollama.exe"
    goto :check_wt
)

echo [ERROR] No se encontro Ollama instalado en el sistema.
echo Por favor descargalo e instalalo desde: https://ollama.com
echo.
pause
exit /b 1

:check_wt
set "WT_EXE="
where wt.exe >nul 2>&1
if %errorlevel% equ 0 (
    set "WT_EXE=wt.exe"
    goto :check_args
)
if exist "%LOCALAPPDATA%\Microsoft\WindowsApps\wt.exe" (
    set "WT_EXE=%LOCALAPPDATA%\Microsoft\WindowsApps\wt.exe"
    goto :check_args
)
if exist "%USERPROFILE%\AppData\Local\Microsoft\WindowsApps\wt.exe" (
    set "WT_EXE=%USERPROFILE%\AppData\Local\Microsoft\WindowsApps\wt.exe"
    goto :check_args
)
if exist "C:\Users\Manolo\AppData\Local\Microsoft\WindowsApps\wt.exe" (
    set "WT_EXE=C:\Users\Manolo\AppData\Local\Microsoft\WindowsApps\wt.exe"
    goto :check_args
)

:check_args
:: Soporte para argumentos directos por linea de comandos
if /i "%~1"=="serve" goto :ensure_service
if /i "%~1"=="qwen14" goto :run_qwen14b
if /i "%~1"=="qwen" goto :run_qwen14b
if /i "%~1"=="llama" goto :run_llama3b
if /i "%~1"=="vl" goto :run_qwenvl7b

:menu_loop
cls
echo =======================================================
echo     AnkiCraft AI - Gestor de Modelos Locales Ollama
echo =======================================================
echo.

:: -------------------------------------------------------------
:: 2. Verificacion de estado del servicio Ollama
:: -------------------------------------------------------------
curl.exe -s --connect-timeout 2 http://127.0.0.1:11434 >nul 2>&1
if %errorlevel% equ 0 goto :service_already_up

echo [*] Estado del servicio: DETENIDO. Iniciando...
call :ensure_service
goto :service_status_done

:service_already_up
echo [*] Estado del servicio: ACTIVO [http://127.0.0.1:11434]

:service_status_done
echo.
echo [!] Modelos activos actualmente en memoria GPU:
echo -------------------------------------------------------
"%OLLAMA_CMD%" ps
echo -------------------------------------------------------
echo.
echo Modelos descargados disponibles en disco:
echo -------------------------------------------------------
"%OLLAMA_CMD%" list
echo -------------------------------------------------------
echo.
echo Selecciona que modelo deseas desplegar / ejecutar:
echo.
echo   [1] Qwen 2.5 14B    - Recomendado Texto: Razonamiento profundo y retencion Anki
echo   [2] Llama 3.2 3B    - Ultra rapido: Ligero y bajo consumo de VRAM
echo   [3] Qwen 2.5-VL 7B  - Recomendado Multimodal: Diapositivas, PDFs y Vision
echo   [4] Iniciar solo el servicio en segundo plano - Para usar con la Web App
echo   [5] Descargar / Actualizar un modelo - ollama pull con presets
echo   [6] Iniciar AnkiCraft AI completo - start.bat
echo   [0] Salir
echo.
set /p "CHOICE=Ingresa una opcion [0-6]: "

if "%CHOICE%"=="1" goto :run_qwen14b
if "%CHOICE%"=="2" goto :run_llama3b
if "%CHOICE%"=="3" goto :run_qwenvl7b
if "%CHOICE%"=="4" goto :serve_only
if "%CHOICE%"=="5" goto :pull_model
if "%CHOICE%"=="6" goto :start_ankicraft
if "%CHOICE%"=="0" exit /b 0

echo.
echo Opcion no valida. Presiona cualquier tecla para reintentar...
pause >nul
goto :menu_loop

:: -------------------------------------------------------------
:: Acciones
:: -------------------------------------------------------------

:run_qwen14b
call :ensure_service
echo.
echo [>] Verificando disponibilidad de Qwen 2.5 14B...
"%OLLAMA_CMD%" list | findstr /i "qwen2.5:14b" >nul 2>&1
if %errorlevel% equ 0 goto :launch_qwen14b

echo [i] El modelo 'qwen2.5:14b' no esta descargado en tu equipo.
echo [i] Iniciando descarga oficial de Ollama - aprox 9 GB...
echo.
"%OLLAMA_CMD%" pull qwen2.5:14b
if %errorlevel% neq 0 (
    echo [ERROR] No se pudo descargar el modelo. Revisa tu conexion a Internet.
    pause
    goto :menu_loop
)

:launch_qwen14b
echo.
echo [>] Desplegando Qwen 2.5 14B en GPU...
echo Escribe '/bye' para salir de la sesion interactiva.
echo.
"%OLLAMA_CMD%" run qwen2.5:14b
goto :after_run

:run_llama3b
call :ensure_service
echo.
echo [>] Verificando disponibilidad de Llama 3.2 3B...
"%OLLAMA_CMD%" list | findstr /i "llama3.2:3b" >nul 2>&1
if %errorlevel% equ 0 goto :launch_llama3b

echo [i] El modelo 'llama3.2:3b' no esta descargado en tu equipo.
echo [i] Iniciando descarga oficial de Ollama - aprox 2 GB...
echo.
"%OLLAMA_CMD%" pull llama3.2:3b
if %errorlevel% neq 0 (
    echo [ERROR] No se pudo descargar el modelo. Revisa tu conexion a Internet.
    pause
    goto :menu_loop
)

:launch_llama3b
echo.
echo [>] Desplegando Llama 3.2 3B en GPU...
echo Escribe '/bye' para salir de la sesion interactiva.
echo.
"%OLLAMA_CMD%" run llama3.2:3b
goto :after_run

:run_qwenvl7b
call :ensure_service
echo.
echo [>] Verificando disponibilidad de Qwen 2.5-VL 7B Multimodal...
"%OLLAMA_CMD%" list | findstr /i "qwen2.5vl:7b" >nul 2>&1
if %errorlevel% equ 0 goto :launch_qwenvl7b

echo [i] El modelo 'qwen2.5vl:7b' no esta descargado en tu equipo.
echo [i] Iniciando descarga oficial de Ollama - aprox 4.7 GB...
echo.
"%OLLAMA_CMD%" pull qwen2.5vl:7b
if %errorlevel% neq 0 (
    echo [ERROR] No se pudo descargar el modelo. Revisa tu conexion a Internet.
    pause
    goto :menu_loop
)

:launch_qwenvl7b
echo.
echo [>] Desplegando Qwen 2.5-VL 7B en GPU...
echo Escribe '/bye' para salir de la sesion interactiva.
echo.
"%OLLAMA_CMD%" run qwen2.5vl:7b
goto :after_run

:serve_only
call :ensure_service
echo.
echo =======================================================
echo Servicio Ollama activo y listo para AnkiCraft AI.
echo URL: http://127.0.0.1:11434
echo Puedes seleccionar 'Local (GPU)' en el encabezado de la web.
echo =======================================================
echo.
pause
goto :menu_loop

:pull_model
cls
echo =======================================================
echo           Descargar Nuevo Modelo con Ollama
echo =======================================================
echo.
echo Modelos recomendados para AnkiCraft AI:
echo   [1] qwen2.5vl:7b  - Vision/Multimodal lider para diapositivas y diagramas
echo   [2] qwen2.5:14b   - Razonamiento profundo para texto y leyes de Wozniak
echo   [3] llama3.2:3b   - Ultra rapido para texto
echo   [4] minicpm-v     - Vision compacta alternativa
echo.
echo Escribe el numero de la opcion [1-4] o el nombre exacto de otro modelo:
set /p "PULL_INPUT=Modelo a descargar: "

set "PULL_NAME=%PULL_INPUT%"
if "%PULL_INPUT%"=="1" set "PULL_NAME=qwen2.5vl:7b"
if "%PULL_INPUT%"=="2" set "PULL_NAME=qwen2.5:14b"
if "%PULL_INPUT%"=="3" set "PULL_NAME=llama3.2:3b"
if "%PULL_INPUT%"=="4" set "PULL_NAME=minicpm-v"

if not "%PULL_NAME%"=="" (
    echo.
    echo Descargando '%PULL_NAME%' desde el registro oficial de Ollama...
    "%OLLAMA_CMD%" pull %PULL_NAME%
    echo.
    echo Proceso finalizado.
)
pause
goto :menu_loop

:start_ankicraft
if exist "start.bat" (
    echo Iniciando AnkiCraft AI...
    start "" "start.bat"
) else (
    echo No se encontro start.bat en el directorio actual.
)
exit /b 0

:after_run
echo.
echo Sesion finalizada. El modelo permanece precargado en la memoria de la GPU
echo para que AnkiCraft AI responda de forma instantanea.
echo.
pause
goto :menu_loop

:ensure_service
curl.exe -s --connect-timeout 1 http://127.0.0.1:11434 >nul 2>&1
if %errorlevel% equ 0 exit /b 0

echo [i] Levantando servicio Ollama en segundo plano...
if defined WT_EXE (
    "%WT_EXE%" -w 0 nt --title "Ollama Daemon (GPU)" -d "%CD%" cmd /k ""%OLLAMA_CMD%" serve"
) else (
    start "AnkiCraft AI - Ollama Service" /min cmd /k ""%OLLAMA_CMD%" serve"
)

echo [i] Esperando a que el servicio Ollama este listo...
set /a WAIT_TRIES=0
:wait_ollama_ready
ping 127.0.0.1 -n 2 >nul
curl.exe -s --connect-timeout 1 http://127.0.0.1:11434 >nul 2>&1
if %errorlevel% equ 0 (
    echo [OK] Servicio Ollama iniciado exitosamente.
    exit /b 0
)
set /a WAIT_TRIES+=1
if %WAIT_TRIES% lss 15 goto :wait_ollama_ready

echo [ADVERTENCIA] El servicio Ollama tardo en responder. Continuando...
exit /b 0
