; Script do Inno Setup para o TradosKiller CAT Tool
#define MyAppName "TradosKiller CAT Tool"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "Wir-thunder"
#define MyAppURL "https://github.com/Wir-thunder/TradosKiller.Core"
#define MyAppExeName "TradosKiller.exe"

[Setup]
AppId={{E68A91F2-7B34-4C21-89B7-4D2A98011234}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\TradosKiller
DefaultGroupName=TradosKiller
AllowNoIcons=yes
OutputDir=..\dist_setup
OutputBaseFilename=TradosKiller_Setup_v1.0.0
SetupIconFile=..\assets\app_icon.ico
Compression=lzma
SolidCompression=yes
WizardStyle=modern

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; Inclui os arquivos compilados da pasta dist/TradosKiller
Source: "..\dist\TradosKiller\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\assets\app_icon.ico"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\assets\app_icon.ico"; Tasks: desktopicon

[Registry]
; Associacao de extensao de arquivo .catproj
Root: HKA; Subkey: "Software\Classes\.catproj"; ValueType: string; ValueName: ""; ValueData: "TradosKiller.Project"; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\TradosKiller.Project"; ValueType: string; ValueName: ""; ValueData: "Projeto TradosKiller"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\TradosKiller.Project\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\assets\app_icon.ico,0"
Root: HKA; Subkey: "Software\Classes\TradosKiller.Project\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#MyAppExeName}"" ""%1"""

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

