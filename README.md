# 参加型整列プラグイン

Windows用の参加型配信向け待機列管理アプリです。視聴者3人を1グループとして整理し、OBSに現在・次回の参加者と待機人数を透過表示します。

## ダウンロード

[GitHub Releases](https://github.com/kyo563/plugin-3kHz/releases) の **Assets → Sankagata-Seiretsu-Plugin-…-windows-x64.zip** を選び、ZIPの「プロパティ」に「許可する」があれば適用してから、すべて展開して「参加型整列プラグイン.exe」を起動してください。「Source code」のZIPは実行用ではありません。

Windows 11 x64向けの未署名の正式版です。Chrome・Python・OBS追加プラグインは利用者には不要です。Microsoft Edge WebView2 Runtimeを使用します。

**まずは [導入・利用ガイド](docs/USER_GUIDE.md) をお読みください。配布ZIPには初めて使う方向けのガイドをREADME.txtとして収録しています。**

## できること

- 手動参加者追加、3人ずつの対戦進行、順番調整、参加回数・総対戦回数の管理
- OBSの縦横配置、行編集、名前・フォント・文字サイズの変更
- 概要欄用文章の編集・保存・コピー、JSONバックアップ・復元
- 外部アプリからの参加／辞退コメントの受信API

**開発版1.1.0ではYouTube公式APIのコメント受信を追加しました。** 管理画面で配信URLとAPIキーを指定します。[設定・制約](docs/YOUTUBE_CHAT.md)を確認してください。公開済み1.0.0にはこの機能はありません。外部アプリからの[受信API](docs/EXTERNAL_INPUT.md)も引き続き利用できます。

## 開発・検証

FastAPI + SQLite + pywebview（Windows WebView2）で構成しています。旧extensionフォルダーは参考資料で、現行アプリでは使いません。

```powershell
./setup-desktop.ps1
./.venv/Scripts/python.exe -m pytest -q
node --test tests/control_ui.test.cjs tests/overlay_text.test.cjs
./.venv/Scripts/python.exe scripts/smoke_http.py
./build-windows.ps1
./.venv/Scripts/python.exe scripts/package_release.py --version 1.0.0
```

詳細は [開発仕様](DEVELOPMENT_SPEC.md)、[開発ルール](AGENTS.md)、[配布前の確認事項](docs/DISTRIBUTION_STATUS.md) を参照してください。

インストーラー、署名、OBS/Edge長時間併用・クリーンPCの受入試験は未完了です。内部の保存先・所有識別子は既存データ互換のためWaitingListAppを維持します。
