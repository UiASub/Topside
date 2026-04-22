; Inno Setup script for the Topside dashboard.
; Compiled in CI by .github/workflows/release.yml.
; Version is injected via /DAppVersion=<tag> on the iscc command line.

#ifndef AppVersion
  #define AppVersion "0.0.0-dev"
#endif

#define MyAppName     "Topside"
#define MyAppExeName  "Topside.exe"
#define MyAppPublisher "UiASub"

[Setup]
AppId={{A3E6F5B0-5B3D-4F8A-9B10-6A8E8E8D1234}
AppName={#MyAppName}
AppVersion={#AppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=auto
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputBaseFilename=Topside-{#AppVersion}-setup
OutputDir=output
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayName={#MyAppName} {#AppVersion}

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional icons:"; Flags: unchecked

[Files]
Source: "..\dist\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion
; Ship the starter data folder, but preserve user edits on upgrade.
Source: "..\data\*"; DestDir: "{app}\data"; Flags: onlyifdoesntexist recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; WorkingDir: "{app}"; Flags: nowait postinstall skipifsilent
