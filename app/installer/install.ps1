#Requires -Version 5.1
param(
    [string]$InstallDir = "",
    [switch]$Silent
)

# Log do %TEMP% od pierwszej linii (zawsze zapisywalny)
$LOG = "$env:TEMP\MailAI_install_log.txt"
function L { param($m)
    $ts  = Get-Date -Format "HH:mm:ss"
    $line = "[$ts] $m"
    Write-Host $line
    Add-Content -Path $LOG -Value $line -Encoding UTF8 -ErrorAction SilentlyContinue
}
Set-Content -Path $LOG `
    -Value "==== Mail@AI Install Log  $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') ====" `
    -Encoding UTF8 -ErrorAction SilentlyContinue

$psVer = $PSVersionTable.PSVersion
$isAdminNow = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
              ).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
L "START - PS $psVer  user=$env:USERNAME  admin=$isAdminNow"
L "InstallDir param: '$InstallDir'"
L "Script path: $($MyInvocation.MyCommand.Path)"

# Calosc w try/catch
try {

# Ustal katalog projektu
$SCRIPT_DIR = if ($MyInvocation.MyCommand.Path) {
                  Split-Path -Parent $MyInvocation.MyCommand.Path
              } else { $PWD.Path }

$PROJECT_DIR = if ($InstallDir -and (Test-Path $InstallDir)) {
                   $InstallDir
               } else {
                   Split-Path -Parent $SCRIPT_DIR
               }

L "PROJECT_DIR resolved: $PROJECT_DIR"

$INST_DIR    = Join-Path $PROJECT_DIR "installer"
$MARKER_FILE = Join-Path $INST_DIR    "install_ok.txt"
$CONFIG_FILE = Join-Path $INST_DIR    "install_config.json"

if (-not (Test-Path $INST_DIR)) {
    New-Item -ItemType Directory -Force -Path $INST_DIR | Out-Null
    L "Created: $INST_DIR"
}
if (Test-Path $MARKER_FILE) { Remove-Item $MARKER_FILE -Force }

$isAdmin = $isAdminNow
L "isAdmin: $isAdmin"

$ErrorActionPreference = "Continue"

# Kolory + log
function LH  { param($m) Write-Host "`n=====  $m  =====" -ForegroundColor Cyan    ; L "--- $m ---" }
function LOK { param($m) Write-Host "  [OK]  $m" -ForegroundColor Green          ; L "[OK] $m" }
function LWW { param($m) Write-Host "  [..]  $m" -ForegroundColor Yellow         ; L "[..] $m" }
function LER { param($m) Write-Host "  [!!]  $m" -ForegroundColor Red            ; L "[!!] $m" }
function LST { param($m) Write-Host "  >>   $m"  -ForegroundColor White          ; L "[>>] $m" }

# Stale
$PYTHON_MIN  = [Version]"3.10"
$PYTHON_URL  = "https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe"
$OLLAMA_URL  = "https://ollama.com/download/OllamaSetup.exe"
$OLLAMA_PORT = 11434
$APP_PORT    = 8765
$DESKTOP     = [Environment]::GetFolderPath("Desktop")

Write-Host ""
Write-Host "  ============================================================" -ForegroundColor Cyan
Write-Host "     Mail@AI - Power Platform Message Center" -ForegroundColor Cyan
Write-Host "     Instalator Windows" -ForegroundColor Cyan
Write-Host "  ============================================================" -ForegroundColor Cyan
Write-Host "  Katalog: $PROJECT_DIR" -ForegroundColor Gray
Write-Host ""

# KROK 1 - Porty
LH "KROK 1 - Kontrola portow"

function Get-PortProcess { param([int]$Port)
    try {
        $t = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue |
             Where-Object { $_.State -in @("Listen","Established") } | Select-Object -First 1
        if ($t) {
            $p = Get-Process -Id $t.OwningProcess -ErrorAction SilentlyContinue
            return [PSCustomObject]@{
                InUse = $true
                PID   = $t.OwningProcess
                Name  = if ($p) { $p.Name } else { "PID $($t.OwningProcess)" }
            }
        }
    } catch {}
    return [PSCustomObject]@{ InUse = $false }
}

$pi = Get-PortProcess -Port $OLLAMA_PORT
if ($pi.InUse -and $pi.Name -notmatch "ollama") {
    LER "Port $OLLAMA_PORT zajety przez: $($pi.Name) (PID $($pi.PID))"
    if (-not $Silent) {
        $c = Read-Host "  [1] Zakoncz proces  [2] Pomin"
        if ($c.Trim() -eq "1") {
            Stop-Process -Id $pi.PID -Force -ErrorAction SilentlyContinue
            Start-Sleep 2
        }
    }
} else { LOK "Port $OLLAMA_PORT (Ollama): OK" }

$ai = Get-PortProcess -Port $APP_PORT
if ($ai.InUse) {
    LWW "Port $APP_PORT zajety przez: $($ai.Name)"
    if (-not $Silent) {
        $c = Read-Host "  [1] Zakoncz  [2] Zmien port  [3] Pomin"
        if ($c.Trim() -eq "1") {
            Stop-Process -Id $ai.PID -Force -ErrorAction SilentlyContinue
            Start-Sleep 1
        } elseif ($c.Trim() -eq "2") {
            $np = [int](Read-Host "  Nowy port").Trim()
            $cfgPy = Join-Path $PROJECT_DIR "app\config.py"
            if (Test-Path $cfgPy) {
                (Get-Content $cfgPy -Raw) -replace "SERVER_PORT\s*=\s*\d+", "SERVER_PORT = $np" |
                    Set-Content $cfgPy -Encoding UTF8
                $APP_PORT = $np
                LOK "Port zmieniony na $APP_PORT"
            }
        }
    }
} else { LOK "Port $APP_PORT (Mail@AI): wolny" }

# KROK 2 - Windows Defender
LH "KROK 2 - Windows Defender"

if ($isAdmin) {
    foreach ($p in @($PROJECT_DIR, "$env:LOCALAPPDATA\Programs\Ollama", "$env:USERPROFILE\.ollama")) {
        try {
            if (-not (Test-Path $p)) { New-Item -ItemType Directory -Force -Path $p | Out-Null }
            Add-MpPreference -ExclusionPath $p -ErrorAction SilentlyContinue
            LOK "Defender exclude: $p"
        } catch { LWW "Defender skip: $p" }
    }
    foreach ($proc in @("ollama.exe", "python.exe", "pythonw.exe")) {
        try { Add-MpPreference -ExclusionProcess $proc -ErrorAction SilentlyContinue } catch {}
    }
} else {
    LWW "Brak admina - pomijam Defender (nie krytyczne)"
}

# KROK 3 - Python
LH "KROK 3 - Python $PYTHON_MIN+"

function Refresh-PATH {
    $machinePath = [System.Environment]::GetEnvironmentVariable("PATH", "Machine")
    $userPath    = [System.Environment]::GetEnvironmentVariable("PATH", "User")
    $env:PATH    = $machinePath + ";" + $userPath
}

function Find-Python {
    $list = @(
        (Join-Path $env:LOCALAPPDATA "Programs\Python\Python313\python.exe"),
        (Join-Path $env:LOCALAPPDATA "Programs\Python\Python312\python.exe"),
        (Join-Path $env:LOCALAPPDATA "Programs\Python\Python311\python.exe"),
        (Join-Path $env:LOCALAPPDATA "Programs\Python\Python310\python.exe"),
        (Join-Path $env:ProgramFiles  "Python313\python.exe"),
        (Join-Path $env:ProgramFiles  "Python312\python.exe"),
        (Join-Path $env:ProgramFiles  "Python311\python.exe"),
        (Join-Path $env:ProgramFiles  "Python310\python.exe"),
        "python",
        "python3"
    )
    foreach ($c in $list) {
        try {
            $raw = (& $c --version 2>&1) -replace "Python ", ""
            if ([Version]$raw.Trim() -ge $PYTHON_MIN) { return $c }
        } catch {}
    }
    return $null
}

$pythonExe = Find-Python
if ($null -eq $pythonExe) {
    LWW "Python nie znaleziony - pobieram 3.11.9..."
    $pyInst = "$env:TEMP\python_installer.exe"
    try {
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        $ProgressPreference = "SilentlyContinue"
        Invoke-WebRequest -Uri $PYTHON_URL -OutFile $pyInst -UseBasicParsing
        $ProgressPreference = "Continue"
        L "Python installer downloaded: $(Test-Path $pyInst)"
        LST "Instalacja Python (cicha)..."
        $r = Start-Process $pyInst `
            -ArgumentList "/quiet", "InstallAllUsers=0", "PrependPath=1", "Include_pip=1", "Include_launcher=1" `
            -Wait -PassThru -NoNewWindow
        L "Python installer exit: $($r.ExitCode)"
        Remove-Item $pyInst -Force -ErrorAction SilentlyContinue
        Refresh-PATH
        Start-Sleep 3
        $pythonExe = Find-Python
    } catch {
        LER "Blad pobierania Python: $_"
        L "EXC Python: $_"
    }
}

if ($null -eq $pythonExe) {
    LER "Python niedostepny - przerywam"
    L "FAIL: Python not found after install"
    if (-not $Silent) { Read-Host "Enter aby zamknac" }
    exit 1
}
LOK "Python: $(& $pythonExe --version 2>&1)  [$pythonExe]"

# KROK 4 - pip + zaleznosci
LH "KROK 4 - Zaleznosci Python"

& $pythonExe -m pip install --upgrade pip --quiet 2>&1 | Out-Null

$reqFile = Join-Path $PROJECT_DIR "requirements.txt"
if (Test-Path $reqFile) {
    LST "pip install -r requirements.txt..."
    & $pythonExe -m pip install -r $reqFile
    L "pip requirements exit: $LASTEXITCODE"
    if ($LASTEXITCODE -eq 0) { LOK "requirements.txt OK" }
    else { LER "Blad pip (kod $LASTEXITCODE)" }
} else {
    LER "Brak requirements.txt w: $PROJECT_DIR"
}

& $pythonExe -m pip install imap-tools --quiet 2>&1 | Out-Null
LOK "Zaleznosci Python: gotowe"

# KROK 5 - Ollama
LH "KROK 5 - Ollama"

function Find-Ollama {
    $list = @(
        (Join-Path $env:LOCALAPPDATA "Programs\Ollama\ollama.exe"),
        (Join-Path $env:ProgramFiles  "Ollama\ollama.exe")
    )
    foreach ($p in $list) { if (Test-Path $p) { return $p } }
    try { return (Get-Command ollama -ErrorAction Stop).Source } catch {}
    return $null
}

$ollamaExe = Find-Ollama
if ($null -ne $ollamaExe) {
    LOK "Ollama juz zainstalowana: $ollamaExe"
} else {
    LWW "Ollama nie znaleziona - pobieram..."
    $olInst = "$env:TEMP\OllamaSetup.exe"
    try {
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        $ProgressPreference = "SilentlyContinue"
        Invoke-WebRequest -Uri $OLLAMA_URL -OutFile $olInst -UseBasicParsing
        $ProgressPreference = "Continue"
        L "Ollama installer downloaded: $(Test-Path $olInst)"
        LST "Instalacja Ollama (max 5 min)..."
        $olProc = Start-Process $olInst -ArgumentList "/VERYSILENT", "/NORESTART" -PassThru
        # Czekaj max 5 minut - bez -NoNewWindow zeby instalator mogl otworzyc okno
        $finished = $olProc.WaitForExit(300000)
        L "Ollama installer finished=$finished  ExitCode=$($olProc.ExitCode)"
        if (-not $finished) {
            L "Ollama installer timeout - przerywam proces, pliki moga juz byc na dysku"
            try { $olProc.Kill() } catch {}
        }
        Remove-Item $olInst -Force -ErrorAction SilentlyContinue
        # Zatrzymaj procesy ollama uruchomione przez instalator
        LST "Zatrzymuje procesy Ollama uruchomione przez instalator..."
        Get-Process -Name "ollama" -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
        Start-Sleep 5
        Refresh-PATH
        $ollamaExe = Find-Ollama
        if ($null -ne $ollamaExe) { LOK "Ollama zainstalowana: $ollamaExe" }
        else { LER "Ollama nie znaleziona po instalacji" }
    } catch {
        LER "Blad instalacji Ollama: $_"
        L "EXC Ollama: $_"
    }
}

if ($null -eq $ollamaExe) {
    LER "Ollama niedostepna - przerywam"
    L "FAIL: Ollama not found"
    if (-not $Silent) { Read-Host "Enter aby zamknac" }
    exit 1
}
L "Ollama OK: $ollamaExe"

# KROK 6 - Ollama OK (model pobierze sie przy pierwszym uruchomieniu aplikacji)
LH "KROK 6 - Ollama OK"

function Test-OllamaServer {
    try {
        $r = Invoke-WebRequest "http://localhost:$OLLAMA_PORT" `
            -UseBasicParsing -TimeoutSec 3 -ErrorAction SilentlyContinue
        return ($r.StatusCode -eq 200)
    } catch { return $false }
}

LOK "Ollama zainstalowana: $ollamaExe"
LWW "Model gemma3 zostanie pobrany automatycznie przy pierwszym uruchomieniu aplikacji"

# KROK 7 - Zapora, launch.vbs, skrot
LH "KROK 7 - Konfiguracja"

if ($isAdmin) {
    try {
        $rn = "Mail@AI Port $APP_PORT"
        if (-not (Get-NetFirewallRule -DisplayName $rn -ErrorAction SilentlyContinue)) {
            New-NetFirewallRule -DisplayName $rn -Direction Inbound -Protocol TCP `
                -LocalPort $APP_PORT -Action Allow -Profile Private, Domain `
                -ErrorAction SilentlyContinue | Out-Null
            LOK "Zapora: port $APP_PORT"
        } else {
            LOK "Zapora: regula juz istnieje"
        }
    } catch { LWW "Zapora: nie mozna dodac reguly" }
}

# Zapisz konfiguracje (czytana przez launch.vbs)
@{
    python  = $pythonExe
    ollama  = $ollamaExe
    app_dir = $PROJECT_DIR
    port    = $APP_PORT
    date    = (Get-Date -Format "yyyy-MM-dd HH:mm:ss")
} | ConvertTo-Json | Set-Content $CONFIG_FILE -Encoding UTF8
L "Config saved: $CONFIG_FILE"

# start.bat (widoczna konsola - do debugowania)
$startBatLines = @(
    "@echo off",
    "title Mail@AI",
    "cd /d `"$PROJECT_DIR`"",
    "start `"`" `"$ollamaExe`" serve",
    "timeout /t 4 /nobreak >nul",
    "`"$pythonExe`" main.py",
    "pause"
)
Set-Content (Join-Path $PROJECT_DIR "start.bat") ($startBatLines -join "`r`n") -Encoding UTF8
LOK "start.bat: OK"

# launch.vbs - here-string, bez manipulacji cudzoslowami, tylko ASCII, bez BOM
$vbsPath = Join-Path $PROJECT_DIR "launch.vbs"

$vbsContent = @"
' Mail@AI Launcher
Set sh=CreateObject("WScript.Shell")
Set fso=CreateObject("Scripting.FileSystemObject")
Dim appDir:appDir="$PROJECT_DIR"
sh.CurrentDirectory=appDir
Dim py:py="$pythonExe"
Dim ol:ol="$ollamaExe"
If Not fso.FileExists(py) Or Not fso.FileExists(ol) Then
  MsgBox "Blad: brak Python lub Ollama. Uruchom ponownie: MailAI-Setup.exe",vbExclamation,"Mail@AI"
  WScript.Quit 1
End If
If Not OllamaOK() Then
  sh.Run Chr(34) & ol & Chr(34) & " serve",0,False
  Dim w
  For w=1 To 20
    WScript.Sleep 1000
    If OllamaOK() Then Exit For
  Next
End If
sh.Run Chr(34) & py & Chr(34) & " " & Chr(34) & appDir & "\main.py" & Chr(34),0,False
Dim i
For i=1 To 13
  WScript.Sleep 1500
  If AppOK() Then Exit For
Next
sh.Run "http://127.0.0.1:$APP_PORT",1,False
Function OllamaOK()
  OllamaOK=False:On Error Resume Next
  Dim h:Set h=CreateObject("MSXML2.XMLHTTP")
  h.Open "GET","http://localhost:$OLLAMA_PORT",False:h.Send
  OllamaOK=(Err.Number=0 And h.Status=200):On Error GoTo 0
End Function
Function AppOK()
  AppOK=False:On Error Resume Next
  Dim h:Set h=CreateObject("MSXML2.XMLHTTP")
  h.Open "GET","http://127.0.0.1:$APP_PORT",False:h.Send
  AppOK=(Err.Number=0 And h.Status=200):On Error GoTo 0
End Function
"@

# ASCII bez BOM - VBScript nie toleruje BOM (EF BB BF) na poczatku pliku
[System.IO.File]::WriteAllText($vbsPath, $vbsContent, [System.Text.Encoding]::ASCII)
LOK "launch.vbs: zaktualizowany"
L "launch.vbs: py=$pythonExe ol=$ollamaExe"

# Skrot na pulpicie
try {
    $wsh = New-Object -ComObject WScript.Shell
    $sc  = $wsh.CreateShortcut("$DESKTOP\Mail@AI.lnk")
    $sc.TargetPath       = "wscript.exe"
    $sc.Arguments        = "`"$vbsPath`""
    $sc.WorkingDirectory = $PROJECT_DIR
    $sc.Description      = "Mail@AI - Power Platform Message Center"
    $sc.Save()
    LOK "Skrot: Mail@AI.lnk"
} catch { LWW "Skrot: $_" }

# KROK 8 - Weryfikacja
LH "KROK 8 - Weryfikacja"

$allOk = $true

try {
    $t = & $pythonExe -c "import fastapi,uvicorn,pandas,openpyxl,requests; print('OK')" 2>&1
    if ($t -match "OK") { LOK "Biblioteki Python: OK" }
    else { LER "Biblioteki: $t"; $allOk = $false }
} catch { LER "Test Python: $_"; $allOk = $false }

if (Test-OllamaServer) { LOK "Ollama server: dziala" }
else { LWW "Ollama: uruchomi sie przy starcie aplikacji" }

$mainPy = Join-Path $PROJECT_DIR "main.py"
if (Test-Path $mainPy) { LOK "main.py: OK" }
else { LER "Brak main.py w $PROJECT_DIR"; $allOk = $false }

try {
    $imp = & $pythonExe -c @"
import sys, os
sys.path.insert(0, r'$PROJECT_DIR')
os.chdir(r'$PROJECT_DIR')
from app.config import SERVER_HOST, SERVER_PORT, MODEL
print(str(SERVER_HOST) + ':' + str(SERVER_PORT) + ' ' + str(MODEL))
"@ 2>&1
    if ($imp -match ":\d+") { LOK "Import app: $imp" }
    else { LER "Import: $imp"; $allOk = $false }
} catch { LER "Import: $_"; $allOk = $false }

# Zapisz znacznik sukcesu
if ($allOk) {
    "OK|$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')|$pythonExe|$ollamaExe" |
        Set-Content $MARKER_FILE -Encoding UTF8
    LOK "Znacznik instalacji zapisany"
    L "SUCCESS - marker: $MARKER_FILE"
} else {
    LER "Weryfikacja nie przeszla - brak znacznika"
    L "FAIL: verification failed"
}

# Skopiuj log do katalogu aplikacji
try {
    Copy-Item $LOG -Destination (Join-Path $INST_DIR "install_log.txt") -Force
} catch {}

Write-Host ""
if ($allOk) {
    Write-Host "============================================================" -ForegroundColor Green
    Write-Host "   INSTALACJA ZAKONCZONA POMYSLNIE" -ForegroundColor Green
    Write-Host "   Uruchom: skrot Mail@AI na pulpicie" -ForegroundColor Green
    Write-Host "   Adres:   http://127.0.0.1:$APP_PORT" -ForegroundColor Green
    Write-Host "============================================================" -ForegroundColor Green
} else {
    Write-Host "============================================================" -ForegroundColor Yellow
    Write-Host "   BLAD INSTALACJI" -ForegroundColor Yellow
    Write-Host "   Log: $LOG" -ForegroundColor Yellow
    Write-Host "============================================================" -ForegroundColor Yellow
}
Write-Host ""
L "DONE allOk=$allOk"

} catch {
    $errMsg = "KRYTYCZNY BLAD: $_ | Linia: $($_.InvocationInfo.ScriptLineNumber)"
    Add-Content -Path $LOG -Value $errMsg -Encoding UTF8 -ErrorAction SilentlyContinue
    Write-Host $errMsg -ForegroundColor Red
    Write-Host "Log: $LOG" -ForegroundColor Yellow
    if (-not $Silent) { Read-Host "Enter aby zamknac" }
    exit 1
}

if (-not $Silent) { Read-Host "Nacisnij Enter aby zamknac" }
