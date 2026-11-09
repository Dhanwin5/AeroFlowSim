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
ChangesEnvironment=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Tasks]
; A tick box on the installer's "Additional tasks" page (ticked by default)
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"
; The program folder on the user's PATH, so that Claude (the AeroFlowSim plugin) and terminals can start it by its name
; "AeroFlowSim" (the folder holds only AeroFlowSim.exe and _internal\; removed again on uninstall)
Name: "addtopath"; Description: "Let Claude and the command line start AeroFlowSim (add it to PATH)"; GroupDescription: "AI assistants:"

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

; the user's PATH (HKCU, no administrator rights): appended once, removed on uninstall ([Code] below)
Root: HKCU; Subkey: "Environment"; ValueType: expandsz; ValueName: "Path"; ValueData: "{olddata};{app}"; Tasks: addtopath; Check: NeedsAddPath(ExpandConstant('{app}'))

[Run]
Filename: "{app}\AeroFlowSim.exe"; Description: "Start AeroFlowSim"; Flags: nowait postinstall skipifsilent

[Code]
{ True when the folder is not yet on the user's PATH (so a re-install does not add it twice). }
function NeedsAddPath(Folder: string): Boolean;
var
  Paths: string;
begin
  if not RegQueryStringValue(HKCU, 'Environment', 'Path', Paths) then
  begin
    Result := True;
    exit;
  end;
  Result := Pos(';' + Uppercase(Folder) + ';', ';' + Uppercase(Paths) + ';') = 0;
end;

{ On uninstall: take the program folder out of the user's PATH again. }
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  Paths, Folder: string;
  P: Integer;
begin
  if CurUninstallStep <> usPostUninstall then
    exit;
  if not RegQueryStringValue(HKCU, 'Environment', 'Path', Paths) then
    exit;
  Folder := ExpandConstant('{app}');
  P := Pos(';' + Uppercase(Folder), Uppercase(Paths));
  if P > 0 then
  begin
    Delete(Paths, P, Length(Folder) + 1);
    RegWriteExpandStringValue(HKCU, 'Environment', 'Path', Paths);
  end;
end;
