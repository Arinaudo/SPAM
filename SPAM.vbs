' ============================================================
'  SPAM - Lanceur sans console (double-cliquer sur ce fichier)
'  Ouvre l'application sans aucune fenetre noire.
'  1re utilisation : bascule sur le lanceur visible (installation).
' ============================================================
Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
dossier = fso.GetParentFolderName(WScript.ScriptFullName)
sh.CurrentDirectory = dossier

If fso.FileExists(dossier & "\.venv\Scripts\python.exe") Then
    ' Environnement pret : lancement fenetre cachee (0 = invisible)
    sh.Run """" & dossier & "\_run_hidden.bat""", 0, False
Else
    ' Premiere fois : installation visible pour voir la progression
    sh.Run """" & dossier & "\Lancer_SPAM.bat""", 1, False
End If
