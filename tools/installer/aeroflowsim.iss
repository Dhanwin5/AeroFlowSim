; AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
; Copyright (C) 2026 Dhanwin Mehta
; SPDX-License-Identifier: GPL-3.0-or-later
;
; Inno Setup 6 script of the Windows installer (built by tools/build_installer.py, which passes AppVersion,
; SourceDir = the PyInstaller one-folder build, and OutputDir). Per-user install: no administrator rights.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId={{6E5B1C2A-8E0F-4C1B-9F6A-AF5A1D0C7B21}
AppName=AeroFlowSim
AppVersion={#AppVersion}
AppPublisher=Dhanwin Mehta
DefaultDirName={localappdata}\Programs\AeroFlowSim
DefaultGroupName=AeroFlowSim
PrivilegesRequired=lowest
DisableProgramGroupPage=yes
OutputDir={#OutputDir}
OutputBaseFilename=AeroFlowSim-{#AppVersion}-setup
Compression=lzma2/max
SolidCompression=yes
LicenseFile={#SourceDir}\_internal\LICENSE
UninstallDisplayIcon={app}\AeroFlowSim.exe
ChangesAssociations=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Tasks]
; A tick box on the installer's "Additional tasks" page (ticked by default)
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"

[Icons]
Name: "{userprograms}\AeroFlowSim"; Filename: "{app}\AeroFlowSim.exe"
Name: "{userdesktop}\AeroFlowSim"; Filename: "{app}\AeroFlowSim.exe"; Tasks: desktopicon
Name: "{userprograms}\AeroFlowSim user guide"; Filename: "{app}\_internal\docs\user_guide.md"
Name: "{userprograms}\Uninstall AeroFlowSim"; Filename: "{uninstallexe}"

[Registry]
; .afsproj files (the file project.afsproj in every project folder) open the project in AeroFlowSim
Root: HKCU; Subkey: "Software\Classes\.afsproj"; ValueType: string; ValueName: ""; ValueData: "AeroFlowSim.Project"; Flags: uninsdeletevalue
Root: HKCU; Subkey: "Software\Classes\AeroFlowSim.Project"; ValueType: string; ValueName: ""; ValueData: "AeroFlowSim project"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\AeroFlowSim.Project\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\AeroFlowSim.exe,0"
Root: HKCU; Subkey: "Software\Classes\AeroFlowSim.Project\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\AeroFlowSim.exe"" ""%1"""

[Run]
Filename: "{app}\AeroFlowSim.exe"; Description: "Start AeroFlowSim"; Flags: nowait postinstall skipifsilent
