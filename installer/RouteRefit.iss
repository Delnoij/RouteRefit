; SPDX-License-Identifier: GPL-3.0-only
; Build only with build_installer.py, after the release privacy checks.
#ifndef ProductVersion
  #error ProductVersion is required
#endif
#ifndef Payload
  #error Payload is required
#endif
#ifndef OutputFolder
  #error OutputFolder is required
#endif

[Setup]
AppId={{9C35AC65-C171-4B85-BB5B-6A2EA35C5A83}
AppName=RouteRefit
AppVersion={#ProductVersion}
AppVerName=RouteRefit {#ProductVersion} Bèta
AppPublisher=Marco Delnoij (EOSfoto)
VersionInfoVersion={#ProductVersion}.0
VersionInfoProductName=RouteRefit
VersionInfoProductVersion={#ProductVersion}.0
VersionInfoProductTextVersion={#ProductVersion} Bèta
VersionInfoDescription=RouteRefit
VersionInfoCopyright=Copyright (C) 2026 EOSfoto
DefaultDirName={localappdata}\RouteRefit
DefaultGroupName=RouteRefit
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.22000
UsePreviousAppDir=yes
DisableProgramGroupPage=yes
AllowNoIcons=yes
LicenseFile=..\LICENSE
InfoBeforeFile=privacy-installation.txt
InfoAfterFile=after-installation.txt
SetupIconFile=..\src\assets\routerefit.ico
UninstallDisplayIcon={app}\RouteRefit.exe
OutputDir={#OutputFolder}
OutputBaseFilename=RouteRefit-{#ProductVersion}-beta-Setup
Compression=lzma2/fast
SolidCompression=yes
WizardStyle=modern
CloseApplications=no
RestartApplications=no
Uninstallable=yes
UninstallDisplayName=RouteRefit {#ProductVersion} Bèta
SetupLogging=yes

[Languages]
Name: "dutch"; MessagesFile: "compiler:Languages\Dutch.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "german"; MessagesFile: "compiler:Languages\German.isl"
Name: "french"; MessagesFile: "compiler:Languages\French.isl"
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"
Name: "portuguese"; MessagesFile: "compiler:Languages\Portuguese.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "{#Payload}\RouteRefit-{#ProductVersion}-beta.exe"; DestDir: "{app}"; DestName: "RouteRefit.exe"; Flags: ignoreversion
Source: "{#Payload}\*"; DestDir: "{app}"; Excludes: "RouteRefit-{#ProductVersion}-beta.exe,Koppeling instellen.cmd"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "Koppeling instellen.cmd"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\RouteRefit"; Filename: "{app}\RouteRefit.exe"; WorkingDir: "{app}"
Name: "{autodesktop}\RouteRefit"; Filename: "{app}\RouteRefit.exe"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\RouteRefit.exe"; Description: "{cm:LaunchProgram,RouteRefit}"; Flags: nowait postinstall skipifsilent unchecked

[Code]
const
  InvalidHandle = -1;

function CreateFileW(Name: String; Access, ShareMode, Security, Creation, Flags, Template: LongWord): THandle;
  external 'CreateFileW@kernel32.dll stdcall';
function CloseHandle(Handle: THandle): Boolean;
  external 'CloseHandle@kernel32.dll stdcall';

function ProgramFilesBusy(): Boolean;
var
  Found: TFindRec;
  Handle: THandle;
begin
  Result := False;
  if FindFirst(ExpandConstant('{app}\RouteRefit*.exe'), Found) then
  begin
    try
      repeat
        { Probe write access without writing. Never force-close unsaved work. }
        Handle := CreateFileW(ExpandConstant('{app}\') + Found.Name, $40000000, 7, 0, 3, 0, 0);
        if Handle = InvalidHandle then
          Result := True
        else
          CloseHandle(Handle);
      until not FindNext(Found);
    finally
      FindClose(Found);
    end;
  end;
end;

function BusyMessage(): String;
begin
  if ActiveLanguage = 'dutch' then
    Result := 'Sla je werk op en sluit RouteRefit en lopende wegdownloads in deze map. Probeer daarna opnieuw. Je gegevens blijven behouden.'
  else
    Result := 'Save your work and close RouteRefit and active road downloads in this folder, then try again. Your data is preserved.';
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  Result := '';
  if ProgramFilesBusy() then Result := BusyMessage();
end;

function InitializeUninstall(): Boolean;
begin
  Result := not ProgramFilesBusy();
  if not Result then MsgBox(BusyMessage(), mbInformation, MB_OK);
end;

procedure CurUninstallStepChanged(Step: TUninstallStep);
var
  Service, Folder, Tasks, Task, Actions, Action: Variant;
  I, J: Integer;
  OwnTask: Boolean;
  ProtocolCommand: String;
begin
  if Step <> usUninstall then Exit;
  { Only remove this installation's opt-in task. Other portable copies are untouched. }
  try
    Service := CreateOleObject('Schedule.Service');
    Service.Connect();
    Folder := Service.GetFolder('\');
    Tasks := Folder.GetTasks(1);
    for I := Tasks.Count downto 1 do
    begin
      Task := Tasks.Item(I);
      OwnTask := False;
      if Pos('RouteRefit-Gebieden-', Task.Name) = 1 then
      begin
        Actions := Task.Definition.Actions;
        for J := 1 to Actions.Count do
        begin
          Action := Actions.Item(J);
          try
            if CompareText(Action.Path, ExpandConstant('{app}\RouteRefit.exe')) = 0 then
              OwnTask := True;
          except
            Log('Non-executable scheduled task action skipped.');
          end;
        end;
        if OwnTask then Folder.DeleteTask(Task.Name, 0);
      end;
    end;
  except
    Log('Unable to remove an optional background task: ' + GetExceptionMessage);
    MsgBox('Windows could not remove an optional RouteRefit background task. Disable it in Windows Task Scheduler. Your routes and maps remain intact.', mbInformation, MB_OK);
  end;
  if RegQueryStringValue(HKCU, 'Software\Classes\gpxwerkbank\shell\open\command', '', ProtocolCommand) then
    if CompareText(ProtocolCommand, '"' + ExpandConstant('{app}\RouteRefit.exe') + '" "%1"') = 0 then
      RegDeleteKeyIncludingSubkeys(HKCU, 'Software\Classes\gpxwerkbank');
  { There is deliberately no recursive UninstallDelete rule: personal files stay. }
end;
