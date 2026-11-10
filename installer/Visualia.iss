#define MyAppName "Visualia - Generador de Imágenes por Lote"
#define MyAppVersion "1.4.4"
#define MyAppPublisher "Nelson Sanchez Dillon"
#define MyAppExeName "VISUALIA - Nelson Sanchez Dillon.exe"
#define MyAppExeSource "..\dist\1.4.4\VISUALIA 1.4.4 - Nelson Sanchez Dillon.exe"
#define MyAppId "{{D9C71C62-54A4-48DE-B5C5-6357C5C9B4A2}"

[Setup]
AppId={#MyAppId}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
VersionInfoVersion=1.4.4.0
VersionInfoCompany={#MyAppPublisher}
VersionInfoDescription={#MyAppName}
VersionInfoProductName={#MyAppName}
DefaultDirName={autopf}\Visualia
DefaultGroupName=Visualia
DisableProgramGroupPage=yes
LicenseFile=LICENSE.txt
InfoBeforeFile=README-INSTALLER.txt
OutputDir=..\dist\installer
OutputBaseFilename=Instalador_VISUALIA_1.4.4
SetupIconFile=..\assets\visualia.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
DisableDirPage=no
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
Source: "{#MyAppExeSource}"; DestDir: "{app}"; DestName: "{#MyAppExeName}"; Flags: ignoreversion
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
var
  PrivacyPage: TWizardPage;
  PrivacyAcknowledgement: TNewCheckBox;

procedure InitializeWizard;
var
  PrivacyNotice: TNewMemo;
begin
  PrivacyPage := CreateCustomPage(
    wpWelcome,
    'Privacidad y avisos importantes',
    'Lee esta información antes de aceptar la licencia y continuar.'
  );

  PrivacyNotice := TNewMemo.Create(PrivacyPage);
  PrivacyNotice.Parent := PrivacyPage.Surface;
  PrivacyNotice.Left := 0;
  PrivacyNotice.Top := 0;
  PrivacyNotice.Width := PrivacyPage.SurfaceWidth;
  PrivacyNotice.Height := PrivacyPage.SurfaceHeight - ScaleY(42);
  PrivacyNotice.ReadOnly := True;
  PrivacyNotice.ScrollBars := ssVertical;
  PrivacyNotice.WordWrap := True;
  PrivacyNotice.Text :=
    'DATOS Y PRIVACIDAD' + #13#10 + #13#10 +
    'Visualia no incorpora analítica ni envía datos al creador. Al pedir una imagen, el prompt y las imágenes seleccionadas se envían a OpenAI mediante la API y se rigen por sus políticas. No incluyas datos personales que no quieras enviar.' + #13#10 + #13#10 +
    'La clave API se guarda localmente en %LOCALAPPDATA%\Visualia\.env. Al iniciar, Visualia consulta GitHub para buscar actualizaciones; esos servicios reciben los datos técnicos normales de conexión.' + #13#10 + #13#10 +
    'El uso de la API puede generar cargos de OpenAI a cargo del usuario.';

  PrivacyAcknowledgement := TNewCheckBox.Create(PrivacyPage);
  PrivacyAcknowledgement.Parent := PrivacyPage.Surface;
  PrivacyAcknowledgement.Left := 0;
  PrivacyAcknowledgement.Top := PrivacyPage.SurfaceHeight - ScaleY(30);
  PrivacyAcknowledgement.Width := PrivacyPage.SurfaceWidth;
  PrivacyAcknowledgement.Height := ScaleY(28);
  PrivacyAcknowledgement.Caption := 'He leído y comprendido el aviso de privacidad y las advertencias.';
  PrivacyAcknowledgement.Checked := False;
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if (CurPageID = PrivacyPage.ID) and not PrivacyAcknowledgement.Checked then
  begin
    MsgBox('Debes leer y aceptar el aviso de privacidad para continuar.', mbError, MB_OK);
    Result := False;
  end;
end;
