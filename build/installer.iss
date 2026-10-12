; ============================================================
;  Установщик J.A.R.V.I.S. для Windows (Inno Setup 6)
;  Сборка:  ISCC.exe /DAppVersion=1.1.0 build\installer.iss
;  Проще:   запустите build\build_windows.bat — он сделает всё сам
; ============================================================

#ifndef AppVersion
  #define AppVersion "1.1.0"
#endif

#define AppName        "J.A.R.V.I.S."
#define AppExeName     "JARVIS.exe"
#define AppPublisher   "Jarvis Project"
#define AppURL         "https://github.com/UsmanMusav/jarvis"

[Setup]
; GUID приложения — НЕ меняйте между версиями, иначе обновление поставится рядом,
; а не поверх предыдущей установки.
AppId={{7D3F1C62-9B4E-4A77-8E21-5C0A9F2E4D10}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}/issues
AppUpdatesURL={#AppURL}/releases
VersionInfoVersion={#AppVersion}

; Установка «для меня» — без запроса прав администратора.
; Это обязательное условие тихого автообновления: иначе каждое обновление
; вызывало бы окно UAC.
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog

DefaultDirName={autopf}\JARVIS
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
AllowNoIcons=yes
OutputDir=..\dist
OutputBaseFilename=JARVIS-Setup-{#AppVersion}
SetupIconFile=..\assets\icons\jarvis.ico
UninstallDisplayIcon={app}\{#AppExeName}
UninstallDisplayName={#AppName}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible

; Закрывать работающий Джарвис перед обновлением и запускать обратно после
CloseApplications=yes
CloseApplicationsFilter=*.exe
RestartApplications=yes

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[CustomMessages]
russian.CreateDesktopIcon=Создать значок на рабочем столе
russian.AutoStart=Запускать J.A.R.V.I.S. при входе в Windows
russian.LaunchApp=Запустить J.A.R.V.I.S.
russian.RemoveSettings=Удалить настройки и заметки
english.CreateDesktopIcon=Create a desktop shortcut
english.AutoStart=Start J.A.R.V.I.S. when Windows starts
english.LaunchApp=Launch J.A.R.V.I.S.
english.RemoveSettings=Delete settings and notes

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"
Name: "autostart";   Description: "{cm:AutoStart}";         GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; Содержимое папки dist\JARVIS, которую собрал PyInstaller
Source: "..\dist\JARVIS\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}";                   Filename: "{app}\{#AppExeName}"
Name: "{group}\{cm:UninstallProgram,{#AppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}";             Filename: "{app}\{#AppExeName}"; Tasks: desktopicon
Name: "{userstartup}\{#AppName}";             Filename: "{app}\{#AppExeName}"; Tasks: autostart

[Run]
Filename: "{app}\{#AppExeName}"; Description: "{cm:LaunchApp}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}\_internal\__pycache__"

[Code]
// При удалении спрашиваем, стирать ли настройки пользователя
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  DataDir: String;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    DataDir := ExpandConstant('{userappdata}\Jarvis');
    if DirExists(DataDir) then
      if MsgBox(ExpandConstant('{cm:RemoveSettings}') + '?',
                mbConfirmation, MB_YESNO) = IDYES then
        DelTree(DataDir, True, True, True);
  end;
end;
