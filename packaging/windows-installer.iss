; Inno Setup script — builds OphthalElectrophysiology-<version>-windows-setup.exe
; Called from the GitHub Actions workflow with /DVersion=... /DSource=... /DOut=...
#ifndef Version
  #define Version "0.0.0"
#endif
#ifndef Source
  #define Source "..\dist\OphthalElectrophysiology"
#endif
#ifndef Out
  #define Out "..\dist"
#endif

[Setup]
AppId={{7D1D2E53-3B7A-4E3D-9D8E-2C4F1A6B9E01}
AppName=Ophthal Electrophysiology
AppVersion={#Version}
AppPublisher=Kukje Eye Clinic
DefaultDirName={autopf}\OphthalElectrophysiology
DefaultGroupName=Ophthal Electrophysiology
UninstallDisplayIcon={app}\OphthalElectrophysiology.exe
OutputDir={#Out}
OutputBaseFilename=OphthalElectrophysiology-{#Version}-windows-setup
Compression=lzma2
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
WizardStyle=modern
#ifexist "build-icons\icon.ico"
SetupIconFile=build-icons\icon.ico
#endif

[Languages]
Name: "korean"; MessagesFile: "compiler:Languages\Korean.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "{#Source}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Ophthal Electrophysiology"; Filename: "{app}\OphthalElectrophysiology.exe"
Name: "{autodesktop}\Ophthal Electrophysiology"; Filename: "{app}\OphthalElectrophysiology.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\OphthalElectrophysiology.exe"; Description: "{cm:LaunchProgram,Ophthal Electrophysiology}"; Flags: nowait postinstall skipifsilent
