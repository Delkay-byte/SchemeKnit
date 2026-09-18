; SchemeKnit NSIS Installer Customizations
; Preserves user data on uninstall.
; Brand migration note: this installer was previously branded TeachFlow.
; Upgrade detection checks BOTH the legacy and current registry keys so
; existing TeachFlow installations are still recognised for upgrade.

!macro customInit
  ; Check for existing installation (legacy brand first, then current)
  ReadRegStr $0 HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\TeachFlow" "InstallLocation"
  ${If} $0 == ""
    ReadRegStr $0 HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\SchemeKnit" "InstallLocation"
  ${EndIf}
  ${If} $0 != ""
    MessageBox MB_YESNO "Existing SchemeKnit installation found at $0.$\n$\nDo you want to upgrade?" IDYES customInit_done
    Quit
  ${EndIf}
  customInit_done:
!macroend

!macro customUnInit
  ; Ask about user data
  MessageBox MB_YESNO "Do you want to keep your lesson plans and settings?" IDYES keep_data IDNO remove_data

  keep_data:
    Goto done

  remove_data:
    ; Only remove the application directory, not user data
    RMDir /r "$LOCALAPPDATA\TeachFlow\temp"
    RMDir /r "$LOCALAPPDATA\SchemeKnit\temp"

  done:
!macroend
