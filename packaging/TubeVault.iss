#define AppVersion "0.3.10"
#ifndef BuildRoot
#define BuildRoot "..\dist"
#endif
[Setup]
AppId={{A837C735-10C2-4F80-90C7-0FCD18EFA954}
AppName=TubeVault
AppVersion={#AppVersion}
AppPublisher=TubeVault
DefaultDirName={localappdata}\Programs\TubeVault
DefaultGroupName=TubeVault
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\artifacts
OutputBaseFilename=TubeVault-Setup-{#AppVersion}
SetupIconFile=..\assets\tubevault.ico
UninstallDisplayIcon={app}\TubeVault.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no
DisableProgramGroupPage=yes

[Tasks]
Name: "pulltools"; Description: "Install YouTube download tools with WinGet (yt-dlp, FFmpeg and Deno)"
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: checkedonce
Name: "autostart"; Description: "Start TubeVault in the background when I sign into Windows"; Flags: checkedonce

[Files]
Source: "..\scripts\install-pull-tools.ps1"; DestDir: "{app}\scripts"; Flags: ignoreversion
Source: "{#BuildRoot}\TubeVault\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Repair Video Pull Tools"; Filename: "{sys}\WindowsPowerShell\v1.0\powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\scripts\install-pull-tools.ps1"" -Interactive"
Name: "{group}\TubeVault"; Filename: "{app}\TubeVault.exe"
Name: "{autodesktop}\TubeVault"; Filename: "{app}\TubeVault.exe"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "TubeVault"; ValueData: """{app}\TubeVault.exe"" --background"; Flags: uninsdeletevalue; Tasks: autostart

[Run]
Filename: "{sys}\WindowsPowerShell\v1.0\powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\scripts\install-pull-tools.ps1"""; Tasks: pulltools; Flags: skipifsilent
Filename: "{app}\TubeVault.exe"; Description: "Open TubeVault"; Flags: nowait postinstall skipifsilent

; Archive data and Credential Manager secrets intentionally survive uninstall.
