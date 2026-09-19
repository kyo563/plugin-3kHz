#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif
#ifndef FileVersion
  #define FileVersion "1.0.0"
#endif
[Setup]
AppId={{9C11E16E-225D-4951-BC78-5811C194C981}
AppName=参加型整列プラグイン
AppVersion={#AppVersion}
VersionInfoVersion={#FileVersion}
DefaultDirName={localappdata}\Programs\WaitingListApp
DisableDirPage=yes
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\dist\release
OutputBaseFilename=参加型整列プラグイン-{#AppVersion}-windows-x64-setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\参加型整列プラグイン.exe
CloseApplications=no
RestartApplications=no
UsePreviousAppDir=no
MinVersion=10.0.22000
SetupLogging=yes
[Languages]
Name: "japanese"; MessagesFile: "compiler:Languages\Japanese.isl"
[Files]
Source: "..\dist\参加型整列プラグイン\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
[Icons]
Name: "{userprograms}\参加型整列プラグイン"; Filename: "{app}\参加型整列プラグイン.exe"
[Run]
Filename: "{app}\参加型整列プラグイン.exe"; Description: "参加型整列プラグインを起動する"; Flags: nowait postinstall skipifsilent
[UninstallDelete]
Type: dirifempty; Name: "{app}"
[Code]
function RunAppTool(Arguments: String): Boolean;
var Code: Integer;
begin
  Result := Exec(ExpandConstant('{app}\参加型整列プラグイン.exe'), Arguments, '', SW_HIDE, ewWaitUntilTerminated, Code);
  if Result then Result := Code = 0;
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  Result := '';
  if FileExists(ExpandConstant('{app}\参加型整列プラグイン.exe')) then
    if not RunAppTool('--prepare-uninstall') then
      Result := '待機列アプリを終了できませんでした。アプリを閉じて再試行してください。';
end;

function InitializeUninstall: Boolean;
var Choice: Integer; KeepData: Boolean;
begin
  Result := False;
  KeepData := Pos('/KEEPDATA', Uppercase(GetCmdTail)) > 0;
  if not UninstallSilent then begin
    Choice := MsgBox('保存データも完全削除しますか？（既定: はい）' + #13#10 +
      '待機列・参加回数・設定・ログ・接続キー・専用キャッシュを削除します。' + #13#10 +
      '「いいえ」でデータを残せます。OBS・Edgeの設定や共有ランタイムは削除しません。' + #13#10 +
      'OBSに追加した待機列ソース・管理ドックは、ご自身で削除してください。', mbConfirmation, MB_YESNOCANCEL);
    if Choice = IDCANCEL then Exit;
    KeepData := Choice = IDNO;
  end;
  if not RunAppTool('--prepare-uninstall') then begin
    MsgBox('アプリを終了できません。アプリを閉じて再試行してください。削除は中止しました。', mbError, MB_OK);
    Exit;
  end;
  if not KeepData then begin
    if not RunAppTool('--uninstall-data') then begin
      MsgBox('保存データを完全に削除できませんでした。使用中のファイルや所有台帳を確認して再試行してください。本体の削除は中止しました。', mbError, MB_OK);
      Exit;
    end;
  end;
  Result := True;
end;
