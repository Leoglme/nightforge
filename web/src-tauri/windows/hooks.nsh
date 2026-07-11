; Kill the bundled agent sidecar before NSIS overwrites nightforge-agent.exe.
; CheckIfAppIsRunning only handles the main desktop binary, not external sidecars.

!macro NSIS_HOOK_PREINSTALL
  DetailPrint "Arret de nightforge-agent.exe avant mise a jour..."
  ExecWait 'cmd.exe /c taskkill /F /T /IM nightforge-agent.exe 2>nul' $0
  Sleep 2000
  ExecWait 'cmd.exe /c taskkill /F /T /IM nightforge-agent.exe 2>nul' $0
  Sleep 1000
!macroend

!macro NSIS_HOOK_PREUNINSTALL
  DetailPrint "Arret de nightforge-agent.exe avant desinstallation..."
  ExecWait 'cmd.exe /c taskkill /F /T /IM nightforge-agent.exe 2>nul' $0
  Sleep 1500
!macroend
