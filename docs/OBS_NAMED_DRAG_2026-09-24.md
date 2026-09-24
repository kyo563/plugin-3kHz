# OBSへの名前付き追加（2026-09-24）

設定画面・管理画面の「OBSに追加する」から、専用リンクをOBSへドラッグして追加できる。

- ソース名：待機列表示
- 幅1200、高さ600
- 表示専用の `/onecomme-overlay` を使用。管理URL・認証キーは渡さない。
- 既存テンプレートZIPとわんコメ一覧からの追加方法は維持。そちらの初期ソース名はindex.htmlのまま。
- 既存ソースは自動変更・削除しない。同名ソースがあるとOBSが別名に調整する場合がある。
- URL方式は先にわんコメとプラグインを起動する。起動前の接続失敗時はOBSのソースプロパティからページを更新する。

[OBS公式ドラッグ＆ドロップ仕様](https://obsproject.com/tools/browser-drag-and-drop) の `layer-name`、`layer-width`、`layer-height` と `text/uri-list` に準拠。

## 反映

変更は `onecomme-obs-setup.html`、同 `.js`、新規 `.css` の3ファイル。導入済みプラグインの `runtime/_internal/static` と前回の配布用ステージ・ビルド内のstaticへ反映。本体exe・実データ・OBS設定は変更しない。

変更前のファイルは `%LOCALAPPDATA%/JoinQueuePluginBackups/before-obs-drag-20260924-210825` に保存。

## 検証

- Pythonのテンプレート関連3件成功。表示URLが管理トークンなしで取得でき、管理APIは引き続き401となることを確認。
- JavaScriptでドラッグデータの名前・サイズ・URL・認証キー非混入、クリックで画面遷移しないことを検証。
- 導入済み実行ファイルを隔離データで起動し、追加ページ、表示URL、CSS、ZIPと画像、コメント受信、終了を確認。
- 実際のOBSへのドラッグ操作とブラウザーでの視覚確認は未実施。
- 公開Release・独立版・Cloudflare・Bot投稿設定は変更しない。
