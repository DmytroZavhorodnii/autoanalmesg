#Requires -Version 5.1
<#
.SYNOPSIS
    Szybki skrypt diagnostyczny — sprawdza środowisko PRZED instalacją
    Uruchom go jeśli chcesz zobaczyć co jest już zainstalowane.
#>

Write-Host ""
Write-Host "===  MC-Analysis — Diagnostyka środowiska  ===" -ForegroundColor Cyan
Write-Host ""

# Python
Write-Host "[Python]" -ForegroundColor Yellow
try {
    $pyVer = python --version 2>&1
    Write-Host "  $pyVer" -ForegroundColor Green
} catch {
    Write-Host "  Nie znaleziono" -ForegroundColor Red
}

# pip
Write-Host "[pip]" -ForegroundColor Yellow
try {
    $pipVer = python -m pip --version 2>&1
    Write-Host "  $pipVer" -ForegroundColor Green
} catch {
    Write-Host "  Nie znaleziono" -ForegroundColor Red
}

# Biblioteki Python
Write-Host "[Biblioteki Python]" -ForegroundColor Yellow
$libs = @("fastapi", "uvicorn", "pandas", "openpyxl", "requests")
foreach ($lib in $libs) {
    try {
        $ver = python -c "import $lib; print($lib.__version__)" 2>&1
        if ($ver -match "^\d") {
            Write-Host "  $lib $ver" -ForegroundColor Green
        } else {
            Write-Host "  $lib — brak" -ForegroundColor Red
        }
    } catch {
        Write-Host "  $lib — brak" -ForegroundColor Red
    }
}

# Ollama
Write-Host "[Ollama]" -ForegroundColor Yellow
try {
    $ollamaPath = Get-Command ollama -ErrorAction Stop
    Write-Host "  Zainstalowana: $($ollamaPath.Source)" -ForegroundColor Green
} catch {
    $fallback = "$env:LOCALAPPDATA\Programs\Ollama\ollama.exe"
    if (Test-Path $fallback) {
        Write-Host "  Zainstalowana: $fallback" -ForegroundColor Green
    } else {
        Write-Host "  Nie znaleziono" -ForegroundColor Red
    }
}

# Serwer Ollama
Write-Host "[Serwer Ollama (port 11434)]" -ForegroundColor Yellow
try {
    $resp = Invoke-WebRequest -Uri "http://localhost:11434" -UseBasicParsing -TimeoutSec 3
    Write-Host "  Działa (status: $($resp.StatusCode))" -ForegroundColor Green
} catch {
    Write-Host "  Nie odpowiada" -ForegroundColor Red
}

# Modele Ollama
Write-Host "[Modele Ollama]" -ForegroundColor Yellow
try {
    $models = ollama list 2>&1
    $modelLines = ($models -join "`n").Split("`n") | Where-Object { $_ -match "\S" }
    foreach ($line in $modelLines) {
        $color = if ($line -match "gemma3") { "Green" } else { "White" }
        Write-Host "  $line" -ForegroundColor $color
    }
} catch {
    Write-Host "  Nie można pobrać listy modeli" -ForegroundColor Red
}

# Port 8765
Write-Host "[Port 8765 (MC-Analysis)]" -ForegroundColor Yellow
try {
    $conn = New-Object System.Net.Sockets.TcpClient
    $conn.Connect("127.0.0.1", 8765)
    $conn.Close()
    Write-Host "  Zajęty — aplikacja prawdopodobnie już działa" -ForegroundColor Yellow
} catch {
    Write-Host "  Wolny — gotowy do uruchomienia" -ForegroundColor Green
}

# Windows Defender
Write-Host "[Windows Defender — wykluczenia]" -ForegroundColor Yellow
try {
    $excl = Get-MpPreference | Select-Object -ExpandProperty ExclusionPath
    if ($excl) {
        foreach ($e in $excl) { Write-Host "  $e" -ForegroundColor Gray }
    } else {
        Write-Host "  Brak wykluczeń" -ForegroundColor Gray
    }
} catch {
    Write-Host "  Nie można odczytać (brak uprawnień?)" -ForegroundColor Gray
}

Write-Host ""
Write-Host "=== Koniec diagnostyki ===" -ForegroundColor Cyan
Write-Host ""
Read-Host "Naciśnij Enter aby zakończyć"
