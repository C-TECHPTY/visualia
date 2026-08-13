#define MyAppName "Visualia - Generador de Imágenes por Lote"
#define MyAppVersion "1.3.3"
#define MyAppPublisher "Nelson Sanchez Dillon"
#define MyAppExeName "VISUALIA - Nelson Sanchez Dillon.exe"
#define MyAppId "{{D9C71C62-54A4-48DE-B5C5-6357C5C9B4A2}"

[Setup]
AppId={#MyAppId}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
VersionInfoVersion=1.3.3.0
VersionInfoCompany={#MyAppPublisher}
VersionInfoDescription={#MyAppName}
VersionInfoProductName={#MyAppName}
DefaultDirName={autopf}\Visualia
DefaultGroupName=Visualia
DisableProgramGroupPage=yes
LicenseFile=LICENSE.txt
InfoBeforeFile=README-INSTALLER.txt
OutputDir=..\dist\installer
OutputBaseFilename=Instalador_VISUALIA_1.3.3
SetupIconFile=..\assets\visualia.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes
RestartApplications=no
SetupLogging=yes
ChangesEnvironment=no
UsePreviousAppDir=yes
UsePreviousTasks=yes
AppMutex=VisualiaNelsonSanchezDillonMutex
WizardImageFile=wizard-large.bmp
WizardSmallImageFile=wizard-small.bmp

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "desktopicon"; Description: "Crear un acceso directo en el escritorio"; GroupDescription: "Accesos directos adicionales:"; Flags: unchecked

[Files]
Source: "..\dist\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\.env.example"; DestDir: "{app}"; DestName: ".env.example"; Flags: ignoreversion
Source: "README-INSTALLER.txt"; DestDir: "{app}"; DestName: "LEEME.txt"; Flags: ignoreversion
Source: "LICENSE.txt"; DestDir: "{app}"; DestName: "LICENCIA.txt"; Flags: ignoreversion

[Icons]
Name: "{group}\Visualia"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; IconFilename: "{app}\{#MyAppExeName}"
Name: "{group}\Desinstalar Visualia"; Filename: "{uninstallexe}"
Name: "{autodesktop}\Visualia"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; IconFilename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Abrir Visualia"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}"

[Code]
function InitializeSetup(): Boolean;
begin
  Result := True;
end;
