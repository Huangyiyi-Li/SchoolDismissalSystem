#ifndef MyAppVersion
  #define MyAppVersion "0.0.0-dev"
#endif
#ifndef MySetupBaseName
  #define MySetupBaseName "school-dismissal-setup"
#endif

#define MyAppName "数智家校放学系统"
#define MyAppExeName "数智家校放学系统.exe"

[Setup]
AppId={{86C4D4E5-29A3-4F00-A2FC-5CC0CD8A13F2}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher=数智家校项目部
DefaultDirName={localappdata}\Programs\数智家校放学系统
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\dist
OutputBaseFilename={#MySetupBaseName}
SetupIconFile=..\build\branding\app.ico
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no
UninstallDisplayIcon={app}\{#MyAppExeName}

[Files]
Source: "..\dist\数智家校放学系统.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\led-bridge\*"; DestDir: "{app}\led-bridge"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加快捷方式："; Flags: unchecked

[Run]
Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Description: "启动{#MyAppName}"; Flags: nowait postinstall skipifsilent

[Code]
procedure RemoveLegacyStartupEntries();
var
  ResultCode: Integer;
begin
  DeleteFile(ExpandConstant('{userstartup}\{#MyAppName}开机启动.vbs'));
  Exec(ExpandConstant('{sys}\schtasks.exe'),
    '/Delete /TN "{#MyAppName}" /F', '', SW_HIDE, ewWaitUntilTerminated,
    ResultCode);
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
    RemoveLegacyStartupEntries();
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usUninstall then
  begin
    RegDeleteValue(HKEY_CURRENT_USER,
      'Software\Microsoft\Windows\CurrentVersion\Run', '{#MyAppName}');
    RemoveLegacyStartupEntries();
  end;
end;
