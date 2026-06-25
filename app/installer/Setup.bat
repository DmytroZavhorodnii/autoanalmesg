@echo off
:: ============================================================
::  Mail@AI — Windows Installer
::  Automatycznie podnosi uprawnienia do Administratora
:: ============================================================
title Mail@AI Setup

net session >nul 2>&1
if %errorLevel% == 0 goto :run

echo Wymagane uprawnienia Administratora...
echo Kliknij TAK w oknie UAC aby kontynuowac.
timeout /t 3 /nobreak >nul
powershell -NoProfile -Command "Start-Process -FilePath 'cmd.exe' -ArgumentList '/c \"%~f0\"' -Verb RunAs"
exit /b

:run
echo.
echo  =====================================================
echo   Mail@AI -- Power Platform Message Center
echo   Instalator Windows
echo  =====================================================
echo.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1"
if %errorLevel% neq 0 (
    echo.
    echo  [BLAD] Instalator zakonczyl sie z bledem: %errorLevel%
    pause
    exit /b %errorLevel%
)
exit /b 0
