@echo off
REM ============================================================
REM  Quiz Cabo de Guerra - Inicializador automatico (Windows)
REM  Abre o servidor + 2 clientes (Alice e Bob) em janelas
REM  separadas, sem precisar digitar comandos manualmente.
REM ============================================================

title Quiz Cabo de Guerra - Launcher

REM Vai para a pasta onde este script esta (raiz do projeto)
cd /d "%~dp0"

REM ---- Descobre o executavel do Python -----------------------
set "PYTHON="

REM 1) Tenta o launcher oficial "py"
where py >nul 2>&1
if %ERRORLEVEL%==0 (
    set "PYTHON=py"
    goto :found
)

REM 2) Tenta "python" no PATH (ignora o alias da Microsoft Store,
REM    que tem tamanho 0 e nao funciona)
where python >nul 2>&1
if %ERRORLEVEL%==0 (
    set "PYTHON=python"
    goto :found
)

REM 3) Caminho comum de instalacao do Python 3.12 do usuario
if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" (
    set "PYTHON=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
    goto :found
)

REM 4) Python 3.11 como fallback
if exist "%LOCALAPPDATA%\Programs\Python\Python311\python.exe" (
    set "PYTHON=%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
    goto :found
)

echo.
echo [ERRO] Python nao encontrado.
echo Instale o Python 3 em https://www.python.org/downloads/
echo e marque a opcao "Add Python to PATH" durante a instalacao.
echo.
pause
exit /b 1

:found
echo ============================================================
echo   Quiz Cabo de Guerra
echo   Usando Python: %PYTHON%
echo ============================================================
echo.

REM ---- Inicia o SERVIDOR em uma nova janela -------------------
echo Iniciando o servidor...
start "Quiz - SERVIDOR" cmd /k ""%PYTHON%" -m src.server.server"

REM Espera o servidor subir antes de conectar os clientes
timeout /t 2 /nobreak >nul

REM ---- Inicia o CLIENTE 1 (Alice) ----------------------------
echo Abrindo janela do Jogador 1 (Alice)...
start "Quiz - Jogador 1 (Alice)" cmd /k ""%PYTHON%" -m src.client.gui --id-jogador player-1 --apelido Alice --porta-udp 5002"

REM ---- Inicia o CLIENTE 2 (Bob) ------------------------------
echo Abrindo janela do Jogador 2 (Bob)...
start "Quiz - Jogador 2 (Bob)" cmd /k ""%PYTHON%" -m src.client.gui --id-jogador player-2 --apelido Bob --porta-udp 5003"

echo.
echo ============================================================
echo   Tudo pronto! Tres janelas foram abertas:
echo     - SERVIDOR (deixe aberta)
echo     - Jogador 1 (Alice)
echo     - Jogador 2 (Bob)
echo.
echo   Em cada janela de jogador, clique em "Conectar".
echo   A partida comeca automaticamente.
echo ============================================================
echo.
echo Esta janela pode ser fechada.
timeout /t 5 /nobreak >nul
exit /b 0
