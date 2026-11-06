#define AppVersion "0.2.3"
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
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: checkedonce
Name: "autostart"; Description: "Start TubeVault in the background when I sign into Windows"; Flags: checkedonce

[Files]
Source: "..\dist\TubeVault\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\TubeVault"; Filename: "{app}\TubeVault.exe"
Name: "{autodesktop}\TubeVault"; Filename: "{app}\TubeVault.exe"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "TubeVault"; ValueData: """{app}\TubeVault.exe"" --background"; Flags: uninsdeletevalue; Tasks: autostart

[Run]
Filename: "{app}\TubeVault.exe"; Description: "Open TubeVault"; Flags: nowait postinstall skipifsilent

; Archive data and Credential Manager secrets intentionally survive uninstall.
