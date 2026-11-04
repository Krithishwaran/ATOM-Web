' =============================================================================
' ATOM-Web silent launcher (Windows 11)
' Starts the FastAPI server hidden and opens http://127.0.0.1:8000 in browser
' =============================================================================
Option Explicit
Dim fso, shell, projectDir, pythonw
Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")
projectDir = fso.GetParentFolderName(WScript.ScriptFullName)
pythonw = projectDir & "\.venv\Scripts\pythonw.exe"

If Not fso.FileExists(pythonw) Then
    MsgBox "ATOM-Web: virtualenv not found. Create .venv and install requirements.txt first.", vbCritical, "ATOM-Web"
    WScript.Quit 1
End If

shell.CurrentDirectory = projectDir
shell.Run """" & pythonw & """ -m src.main", 0, False
