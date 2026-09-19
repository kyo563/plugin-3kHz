# Windowsデスクトップ開発

利用者向け手順は [USER_GUIDE.md](USER_GUIDE.md)。配布の制限は [DISTRIBUTION_STATUS.md](DISTRIBUTION_STATUS.md) を参照。

## 構成

pywebview（WebView2）+ FastAPI/Uvicorn + SQLite + PyInstaller onedir。
通常起動は127.0.0.1に限定し、管理と外部コメント受信のキーを分離します。Chromeやブラウザーエンジンの同梱はありません。
Astraは開発モデル指定であり、アプリにAI API依存はありません。

## 開発・ビルド

Windows 11 x64 / Python 3.12 x64で以下を実行します。

```powershell
./setup-desktop.ps1 -Python python
./run-desktop.bat
./.venv/Scripts/python.exe -m pytest -q
node --test tests/control_ui.test.cjs tests/overlay_text.test.cjs
./.venv/Scripts/python.exe scripts/smoke_http.py
./build-windows.ps1
./.venv/Scripts/python.exe scripts/package_release.py --version 1.0.0
```

`dist/参加型整列プラグイン/参加型整列プラグイン.exe` と `_internal` を含むフォルダー全体が実行物です。ZIPとSHA256SUMS.txtはdist/releaseに生成します。ビルドとパッケージ処理は公開を行いません。

開発用APIは通常起動で無効です。テストデータを使うときだけ `run-desktop.bat --development` を指定してください。

## 保存とアンインストールの境界

標準データ保存先は `%LOCALAPPDATA%/WaitingListApp`。名称変更後も内部識別子は維持します。
`desktop/ownership.py` が所有台帳・マーカーを使い、本アプリのファイルのみを削除します。指定ディレクトリ全体やOBS・Edge通常プロファイル・共有ランタイムを再帰削除しません。
未知のファイル・不一致マーカー・再解析ポイントでは削除を拒否します。所有台帳がない旧データはバックアップ後に `--adopt-existing-data` で明示的に引き継ぎます。

テストではWAITING_LIST_DATA_DIR・WAITING_LIST_DB_PATH・LOCALAPPDATAを検証用の独立フォルダーへ設定してください。実ユーザーの保存先に対して削除試験を実施しないでください。

## 配布状況

GitHubへは未署名ZIPの正式版を配布します。インストーラー定義はinstaller/WaitingListApp.issにありますが、ビルド・受入試験は未完了です。インストーラーの共通AppId/内部保存名を変更して既存データの所有関係を切らないでください。
Botは保留中。配信サイトAPIへ直接接続する機能はありません。
