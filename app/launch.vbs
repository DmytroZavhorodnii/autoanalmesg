' Mail@AI Launcher
' Uses paths saved by install.ps1 (install_config.json).
' If install.ps1 has not run - launches the installer first.

Set sh  = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

Dim appDir
appDir = Left(WScript.ScriptFullName, InStrRev(WScript.ScriptFullName, "\") - 1)
sh.CurrentDirectory = appDir

' Load config written by install.ps1
Dim cfgFile     : cfgFile     = appDir & "\installer\install_config.json"
Dim markerFile  : markerFile  = appDir & "\installer\install_ok.txt"
Dim installerPs : installerPs = appDir & "\installer\install.ps1"

If Not fso.FileExists(markerFile) Or Not fso.FileExists(cfgFile) Then
    Call RunInstaller()
    WScript.Quit
End If

' Read JSON values
Dim pythonExe : pythonExe = ReadJsonValue(cfgFile, "python")
Dim ollamaExe : ollamaExe = ReadJsonValue(cfgFile, "ollama")
Dim appPort   : appPort   = ReadJsonValue(cfgFile, "port")
If appPort = "" Then appPort = "8765"

' Check files still exist
If Not fso.FileExists(pythonExe) Or Not fso.FileExists(ollamaExe) Then
    Call RunInstaller()
    WScript.Quit
End If

' Start Ollama if not already running
If Not OllamaRunning() Then
    sh.Run Q(ollamaExe) & " serve", 0, False
    Dim w : For w = 1 To 20
        WScript.Sleep 1000
        If OllamaRunning() Then Exit For
    Next
End If

' Start the application
sh.Run Q(pythonExe) & " " & Q(appDir & "\main.py"), 0, False

' Wait for server to become ready
Dim i : For i = 1 To 13
    WScript.Sleep 1500
    If AppRunning(appPort) Then Exit For
Next

' Open browser
sh.Run "http://127.0.0.1:" & appPort, 1, False
WScript.Quit

' =============================================================================
Sub RunInstaller()
    If Not fso.FileExists(installerPs) Then
        MsgBox "Installer not found." & vbCrLf & _
               "Please run MailAI-Setup.exe again.", _
               vbExclamation, "Mail@AI"
        Exit Sub
    End If

    Dim ans
    ans = MsgBox("Mail@AI requires first-time setup." & vbCrLf & vbCrLf & _
                 "The installer will download and configure:" & vbCrLf & _
                 "  - Python 3.11" & vbCrLf & _
                 "  - Ollama (AI server)" & vbCrLf & _
                 "Internet connection required." & vbCrLf & _
                 "Time: approx. 5-10 minutes." & vbCrLf & vbCrLf & _
                 "Continue?", _
                 vbQuestion + vbYesNo, "Mail@AI - Setup")

    If ans = vbNo Then Exit Sub

    Dim psArgs
    psArgs = "-NoProfile -ExecutionPolicy Bypass -File " & Q(installerPs) & _
             " -InstallDir " & Q(appDir)

    sh.Run "powershell.exe -NoProfile -ExecutionPolicy Bypass -Command " & _
           Q("Start-Process powershell.exe -ArgumentList '" & _
             psArgs & "' -Verb RunAs -Wait"), 1, True

    If fso.FileExists(markerFile) Then
        MsgBox "Installation complete!" & vbCrLf & _
               "Click OK to start Mail@AI.", _
               vbInformation, "Mail@AI"
        sh.Run Q(WScript.ScriptFullName), 1, False
    Else
        Dim logFile : logFile = appDir & "\installer\install_log.txt"
        Dim logMsg  : logMsg  = ""
        If fso.FileExists(logFile) Then
            Dim f : Set f = fso.OpenTextFile(logFile, 1)
            Dim lineCount : lineCount = 0
            Do While Not f.AtEndOfStream And lineCount < 30
                logMsg = logMsg & f.ReadLine() & vbCrLf
                lineCount = lineCount + 1
            Loop
            f.Close
        End If
        MsgBox "Installation did not complete." & vbCrLf & vbCrLf & _
               "Log:" & vbCrLf & logMsg & vbCrLf & _
               "Log file: " & logFile, _
               vbExclamation, "Mail@AI - Install error"
    End If
End Sub

' =============================================================================
Function Q(s)
    Q = Chr(34) & s & Chr(34)
End Function

Function ReadJsonValue(filePath, key)
    ReadJsonValue = ""
    On Error Resume Next
    Dim f : Set f = fso.OpenTextFile(filePath, 1)
    Dim content : content = f.ReadAll()
    f.Close
    On Error GoTo 0
    Dim pattern : pattern = Chr(34) & key & Chr(34) & ":"
    Dim pos     : pos     = InStr(content, pattern)
    If pos = 0 Then Exit Function
    pos = pos + Len(pattern)
    Do While pos <= Len(content) And Mid(content, pos, 1) = " " : pos = pos + 1 : Loop
    If Mid(content, pos, 1) = Chr(34) Then
        pos = pos + 1
        Dim endPos : endPos = InStr(pos, content, Chr(34))
        If endPos > 0 Then ReadJsonValue = Mid(content, pos, endPos - pos)
    Else
        Dim numStr : numStr = ""
        Do While pos <= Len(content) And (Mid(content, pos, 1) >= "0" And Mid(content, pos, 1) <= "9")
            numStr = numStr & Mid(content, pos, 1)
            pos = pos + 1
        Loop
        ReadJsonValue = numStr
    End If
End Function

Function OllamaRunning()
    OllamaRunning = False
    On Error Resume Next
    Dim h : Set h = CreateObject("MSXML2.XMLHTTP")
    h.Open "GET", "http://localhost:11434", False
    h.Send
    OllamaRunning = (Err.Number = 0 And h.Status = 200)
    On Error GoTo 0
End Function

Function AppRunning(port)
    AppRunning = False
    On Error Resume Next
    Dim h : Set h = CreateObject("MSXML2.XMLHTTP")
    h.Open "GET", "http://127.0.0.1:" & port, False
    h.Send
    AppRunning = (Err.Number = 0 And h.Status = 200)
    On Error GoTo 0
End Function
