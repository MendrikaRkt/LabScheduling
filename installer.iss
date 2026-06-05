; ============================================================
;  installer.iss - Windows installer for Lab Scheduling
;  Produces a classic setup wizard:
;    Welcome -> License -> Install folder -> Start Menu folder
;    -> Extra tasks (desktop/quick launch) -> Ready -> Progress
;    -> Finish (with "launch now" checkbox)
;
;  Build:  open in Inno Setup Compiler and press Compile
;     or:  "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer.iss
;  Output: Output\LabScheduling_Setup_v1.0.0.exe
; ============================================================

#define MyAppName "Lab Scheduling Automation"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "Universidad Loyola Sevilla"
#define MyAppExeName "LabScheduling.exe"
#define MyAppId "4927CCA1-2521-414E-AFA1-80A83BACD2AC"

[Setup]
AppId={{{#MyAppId}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
VersionInfoVersion={#MyAppVersion}
VersionInfoProductName={#MyAppName}

DefaultDirName={autopf}\LabScheduling
DefaultGroupName=Lab Scheduling
DisableProgramGroupPage=no
DisableWelcomePage=no
AllowNoIcons=yes

OutputDir=Output
OutputBaseFilename=LabScheduling_Setup_v{#MyAppVersion}
SetupIconFile=assets\app_icon.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName}

Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
WizardResizable=no

; Per-user install by default -> no admin rights, %APPDATA% always writable.
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"
Name: "french";  MessagesFile: "compiler:Languages\French.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: checkedonce
Name: "quicklaunchicon"; Description: "{cm:CreateQuickLaunchIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked; OnlyBelowVersion: 6.1

[Files]
; PyInstaller one-folder output -> install everything under {app}
Source: "dist\LabScheduling\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
; Bundle the build's version marker so the updater can compare versions
Source: "VERSION.txt"; DestDir: "{app}"; Flags: ignoreversion skipifsourcedoesntexist

[Dirs]
Name: "{userappdata}\LabScheduling"

[Icons]
Name: "{group}\Lab Scheduling";            Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\{#MyAppExeName}"
Name: "{group}\Uninstall Lab Scheduling";  Filename: "{uninstallexe}"
Name: "{autodesktop}\Lab Scheduling";      Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon; IconFilename: "{app}\{#MyAppExeName}"
Name: "{userappdata}\Microsoft\Internet Explorer\Quick Launch\Lab Scheduling"; Filename: "{app}\{#MyAppExeName}"; Tasks: quicklaunchicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,Lab Scheduling}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Leave user data (%APPDATA%\LabScheduling) intact on uninstall by default.
; To also remove it, uncomment the next line:
; Type: filesandordirs; Name: "{userappdata}\LabScheduling"
