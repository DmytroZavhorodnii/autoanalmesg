@echo off
:: ============================================================
::  Mail@AI — Run Setup Wrapper
::  Obsługuje UAC i uruchamia install.ps1 z poprawnymi ścieżkami
:: ============================================================
setlocal EnableDelayedExpansion

:: Katalog tego pliku (installer\)
set "INST_DIR=%~dp0"
if "!INST_DIR:~-1!"=="\" set "INST_DIR=!INST_DIR:~0,-1!"

:: Katalog projektu = katalog nadrzędny (bez backslash)
for %%I in ("!INST_DIR!") do set "PROJ_DIR=%%~dpI"
if "!PROJ_DIR:~-1!"=="\" set "PROJ_DIR=!PROJ_DIR:~0,-1!"

:: Wstępny log do TEMP — zawsze zapisywalny
set "EARLY_LOG=%TEMP%\MailAI_early.log"
echo [%date% %time%] run_setup.bat START > "!EARLY_LOG!"
echo   INST_DIR=!INST_DIR! >> "!EARLY_LOG!"
echo   PROJ_DIR=!PROJ_DIR! >> "!EARLY_LOG!"
echo   USERNAME=%USERNAME% >> "!EARLY_LOG!"

:: ── Sprawdź uprawnienia administratora ───────────────────────────────────────
net session >nul 2>&1
if %errorLevel% == 0 (
    echo   [admin=YES] >> "!EARLY_LOG!"
    goto :run_ps
)

:: Nie admin — podnieś uprawnienia
echo   [admin=NO] uruchamiam z UAC... >> "!EARLY_LOG!"
echo Wymagane uprawnienia administratora. Pojawi sie okno UAC...
timeout /t 2 /nobreak >nul

powershell.exe -NoProfile -Command ^
  "Start-Process -FilePath '!INST_DIR!\run_setup.bat' -Verb RunAs -Wait"
goto :end

:run_ps
echo   [wywoluje install.ps1] >> "!EARLY_LOG!"
echo.
echo  =====================================================
echo   Mail@AI -- Instalator
echo   Proszę czekać, instalacja może potrwać 10-20 min.
echo  =====================================================
echo.

powershell.exe -NoProfile -ExecutionPolicy Bypass ^
  -File "!INST_DIR!\install.ps1" ^
  -InstallDir "!PROJ_DIR!" ^
  -Silent

set "PS_CODE=!errorLevel!"
echo   [PS exit code=!PS_CODE!] >> "!EARLY_LOG!"

if !PS_CODE! neq 0 (
    echo.
    echo  [BLAD] install.ps1 zakonczyl sie z kodem: !PS_CODE!
    echo  Log: %TEMP%\MailAI_install_log.txt
    echo.
    pause
)

:end
endlocal
