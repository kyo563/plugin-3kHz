# 待機列整理アプリ（わんコメ版）

今後はこちらのわんコメプラグイン版を更新します。独立版1.1.3は変更せず維持します。

## 共通Bot版0.1.2

[0.1.2 検証版をダウンロード](https://github.com/kyo563/plugin-3kHz/releases/tag/onecomme-v0.1.2)。Assets の `Taikiretsu-Seiri-App-OneComme-0.1.2-windows-x64.zip` を使用してください。

ユーザー指定の番号0.1.2で、利用者個別OAuthを共通Bot方式へ置き換えました。NOW呼出し・本人の順番返信・15/30分の人数/組数案内を個別に切り替えられます。[接続・動作・制約](docs/BOT.md)。既存の待機列・OBS表示・プラグインUID・保存先は維持します。Bot投稿は運営側の有効化が必要で、実配信者認証と実投稿は未検証です。

以下の1.0.0/1.1.0は以前の配布記録です。旧リリースと添付は変更していません。

**[Bot追加版1.1.0（検証版）](https://github.com/kyo563/plugin-3kHz/releases/tag/onecomme-v1.1.0)**：入室案内・本人への順位返信・参加方法の定期投稿を追加しました。[OAuthの準備と使い方](docs/BOT.md)。実アカウントでの投稿は未検証です。

**[わんコメ版1.0.0をダウンロード](https://github.com/kyo563/plugin-3kHz/releases/tag/onecomme-v1.0.0)**

Assetsの `Taikiretsu-Seiri-App-OneComme-1.0.0-windows-x64.zip` をすべて展開し、`sankagata-seiretsu` フォルダをわんコメのプラグインフォルダへ入れて有効にしてください。「Source code」は利用者向けではありません。

プラグインのURLボタンから管理画面を開き、ライブ連携で対象配信を選びます。同梱の `Taikiretsu-Template.zip` をわんコメのテンプレート一覧に追加し、そこからOBSへドラッグします。ブラウザソースは幅1200・高さ600以上にしてください。以降の表示設定は管理画面で保存します。

Windows x64・YouTube対応。わんコメ本体が必要です。APIキー・Python・Chromeの追加インストールは不要です。管理画面は専用ページからブラウザで開く方式です。

**[導入・更新・完全削除の手順](onecomme/README.txt)** ／ [設計・ビルド手順](docs/ONECOMME_EDITION.md)

試作版0.1.xの設定・累計は同じ保存先から引き継ぎます。独立版のデータは自動移行せず、必要な場合のみJSONバックアップを復元してください。

自動テストとブラウザの表示切り替えを確認済みです。実YouTubeライブ受信・限定配信・OBS実機へのドラッグ操作は未検証です。

---

## 以下は独立版1.1.3の旧資料です（わんコメ版の導入には使いません）

Windows用の参加型配信向け待機列管理アプリです。視聴者3人を1グループとして整理し、OBSに現在・次回の参加者と待機人数を透過表示します。

## ダウンロード

[GitHub Releases](https://github.com/kyo563/plugin-3kHz/releases) の **Assets → Sankagata-Seiretsu-Plugin-…-windows-x64.zip** を選び、ZIPの「プロパティ」に「許可する」があれば適用してから、すべて展開して「参加型整列プラグイン.exe」を起動してください。「Source code」のZIPは実行用ではありません。

Windows 11 x64向けの未署名の正式版です。Chrome・Python・OBS追加プラグインは利用者には不要です。Microsoft Edge WebView2 Runtimeを使用します。

**まずは [導入・利用ガイド](docs/USER_GUIDE.md) をお読みください。配布ZIPには初めて使う方向けのガイドをREADME.txtとして収録しています。**

## 1.1.3の追加機能

NOWのコメント辞退禁止、管理者削除後の自動補充、参加・辞退文言の複数設定、待機者アイコンを追加しました。[変更内容と導入手順](docs/RELEASE_1.1.3.md)をご覧ください。

## できること

- 手動参加者追加、3人ずつの対戦進行、順番調整、参加回数・総対戦回数の管理
- OBSの縦横配置、行編集、名前・フォント・文字サイズの変更
- 概要欄用文章の編集・保存・コピー、JSONバックアップ・復元
- 外部アプリからの参加／辞退コメントの受信API

**1.1.0ではYouTube公式APIのコメント受信を追加しました。** 管理画面で配信URLとAPIキーを指定します。[設定・制約](docs/YOUTUBE_CHAT.md)を確認してください。公開済み1.0.0にはこの機能はありません。外部アプリからの[受信API](docs/EXTERNAL_INPUT.md)も引き続き利用できます。

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
