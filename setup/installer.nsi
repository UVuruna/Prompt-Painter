Unicode true

; =================================================================
; PromptPainter Installer -- NSIS Script
;
; Creates a standard Windows installer:
;   - Choose install location (default: Program Files\PromptPainter)
;   - Start Menu + Desktop shortcuts
;   - Optional autostart with Windows (HKCU Run - standard-user app)
;   - Uninstaller in Add/Remove Programs
; =================================================================

!include "MUI2.nsh"
!include "FileFunc.nsh"

; -- App Info -----------------------------------------------------
!define APP_NAME "PromptPainter"
!define APP_EXE "PromptPainter.exe"
!define APP_DESCRIPTION "Generates images from prompt-sheet .md files by driving an open Gemini/ChatGPT tab over CDP"

; Registry key for uninstall info
!define UNINST_KEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}"

; -- Paths and company info (passed from build.py via /D flags) ---
; DIST_DIR      -- PyInstaller output (dist\PromptPainter\)
; SETUP_DIR     -- setup folder (for icon reference)
; APP_VERSION   -- version string (reads setup/app_info.json)
; APP_PUBLISHER -- company name (reads root company.json)
; APP_URL       -- website URL  (reads root company.json)

; -- General Settings ---------------------------------------------
Name "${APP_NAME}"
OutFile "${DIST_DIR}\${APP_NAME}_Setup.exe"
InstallDir "$PROGRAMFILES64\${APP_NAME}"
InstallDirRegKey HKLM "${UNINST_KEY}" "InstallLocation"
RequestExecutionLevel admin
SetCompressor /SOLID lzma

; -- Version Info (embeds a VERSIONINFO resource into the Setup.exe) --
; APP_VERSION is passed as three components (e.g. "0.0.086"); the VI*
; directives require four, hence the trailing ".0".
VIProductVersion "${APP_VERSION}.0"
VIFileVersion "${APP_VERSION}.0"
VIAddVersionKey "ProductName" "${APP_NAME}"
VIAddVersionKey "ProductVersion" "${APP_VERSION}"
VIAddVersionKey "CompanyName" "${APP_PUBLISHER}"
VIAddVersionKey "FileDescription" "${APP_NAME} Installer"
VIAddVersionKey "FileVersion" "${APP_VERSION}"
VIAddVersionKey "LegalCopyright" "Copyright (C) ${APP_PUBLISHER}"

; -- Icon ---------------------------------------------------------
!define MUI_ICON "${PROJECT_DIR}\assets\icon.ico"
!define MUI_UNICON "${PROJECT_DIR}\assets\icon.ico"

; -- Interface Settings -------------------------------------------
!define MUI_ABORTWARNING
!define MUI_WELCOMEPAGE_TITLE "Welcome to ${APP_NAME} Setup"
!define MUI_WELCOMEPAGE_TEXT "This wizard will install ${APP_NAME} on your computer.$\r$\n$\r$\n${APP_DESCRIPTION}$\r$\n$\r$\nClick Next to continue."
!define MUI_FINISHPAGE_RUN "$INSTDIR\${APP_EXE}"
!define MUI_FINISHPAGE_RUN_TEXT "Launch ${APP_NAME}"

; -- Pages --------------------------------------------------------
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_COMPONENTS
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

; Uninstaller pages
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

; -- Language -----------------------------------------------------
!insertmacro MUI_LANGUAGE "English"

; =================================================================
; INITIALIZATION -- force the 64-bit registry view
;
; This is a 64-bit-only app (InstallDir already points at
; $PROGRAMFILES64). Without SetRegView 64 a 32-bit NSIS installer
; reads/writes HKLM under the WOW6432Node redirection, so the
; uninstall keys written in SecMain would land in the 32-bit view
; and never be seen by Add/Remove Programs or by a 64-bit process.
; Must run in .onInit / un.onInit -- before InstallDirRegKey is
; resolved and before any registry access in either direction.
; =================================================================

Function .onInit
    SetRegView 64
FunctionEnd

Function un.onInit
    SetRegView 64
FunctionEnd

; =================================================================
; INSTALLER SECTIONS
; =================================================================

Section "!${APP_NAME} (required)" SecMain
    SectionIn RO  ; Cannot be deselected

    ; Close a running instance so locked files can be replaced on upgrade
    nsExec::ExecToLog 'taskkill /im "${APP_EXE}" /f'
    Sleep 500

    ; Remove any previous autostart unconditionally -- SecAutostart recreates
    ; it only when selected, so unchecking it on upgrade actually disables it
    DeleteRegValue HKCU "Software\Microsoft\Windows\CurrentVersion\Run" "${APP_NAME}"

    ; Copy application files
    SetOutPath "$INSTDIR"
    File /r "${DIST_DIR}\${APP_NAME}\*.*"

    ; Start Menu shortcuts
    CreateDirectory "$SMPROGRAMS\${APP_NAME}"
    CreateShortcut "$SMPROGRAMS\${APP_NAME}\${APP_NAME}.lnk" "$INSTDIR\${APP_EXE}" "" "$INSTDIR\icon.ico"
    CreateShortcut "$SMPROGRAMS\${APP_NAME}\Uninstall.lnk" "$INSTDIR\Uninstall.exe"

    ; Write uninstaller
    WriteUninstaller "$INSTDIR\Uninstall.exe"

    ; Write registry keys for Add/Remove Programs
    WriteRegStr HKLM "${UNINST_KEY}" "DisplayName" "${APP_NAME} - ${APP_DESCRIPTION}"
    WriteRegStr HKLM "${UNINST_KEY}" "DisplayIcon" "$INSTDIR\icon.ico"
    WriteRegStr HKLM "${UNINST_KEY}" "UninstallString" "$\"$INSTDIR\Uninstall.exe$\""
    WriteRegStr HKLM "${UNINST_KEY}" "InstallLocation" "$INSTDIR"
    WriteRegStr HKLM "${UNINST_KEY}" "Publisher" "${APP_PUBLISHER}"
    WriteRegStr HKLM "${UNINST_KEY}" "URLInfoAbout" "${APP_URL}"
    WriteRegStr HKLM "${UNINST_KEY}" "DisplayVersion" "${APP_VERSION}"
    WriteRegDWORD HKLM "${UNINST_KEY}" "NoModify" 1
    WriteRegDWORD HKLM "${UNINST_KEY}" "NoRepair" 1

    ; Calculate installed size
    ${GetSize} "$INSTDIR" "/S=0K" $0 $1 $2
    IntFmt $0 "0x%08X" $0
    WriteRegDWORD HKLM "${UNINST_KEY}" "EstimatedSize" $0
SectionEnd

Section "Desktop Shortcut" SecDesktop
    CreateShortcut "$DESKTOP\${APP_NAME}.lnk" "$INSTDIR\${APP_EXE}" "" "$INSTDIR\icon.ico"
SectionEnd

Section /o "Start with Windows" SecAutostart
    ; Standard-user app (no UAC elevation) -> HKCU Run is the correct
    ; autostart mechanism (root CLAUDE.md). Off by default: PromptPainter
    ; is a supervised, launch-when-you-need-it tool.
    WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Run" "${APP_NAME}" "$\"$INSTDIR\${APP_EXE}$\""
SectionEnd

; -- Section Descriptions -----------------------------------------
!insertmacro MUI_FUNCTION_DESCRIPTION_BEGIN
    !insertmacro MUI_DESCRIPTION_TEXT ${SecMain} "Install ${APP_NAME} core files (required)."
    !insertmacro MUI_DESCRIPTION_TEXT ${SecDesktop} "Create a shortcut on your Desktop."
    !insertmacro MUI_DESCRIPTION_TEXT ${SecAutostart} "Automatically start ${APP_NAME} when you log in."
!insertmacro MUI_FUNCTION_DESCRIPTION_END

; =================================================================
; UNINSTALLER
; =================================================================

Section "Uninstall"
    ; Close a running instance so program files are not locked during removal
    nsExec::ExecToLog 'taskkill /im "${APP_EXE}" /f'
    Sleep 500

    ; Remove autostart entry
    DeleteRegValue HKCU "Software\Microsoft\Windows\CurrentVersion\Run" "${APP_NAME}"

    ; Remove shortcuts
    Delete "$DESKTOP\${APP_NAME}.lnk"
    RMDir /r "$SMPROGRAMS\${APP_NAME}"

    ; Remove program files
    RMDir /r "$INSTDIR"

    ; Remove registry keys
    DeleteRegKey HKLM "${UNINST_KEY}"
SectionEnd
