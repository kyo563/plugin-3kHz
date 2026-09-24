# 0.1.2 不具合修正

公開済みonecomme-v0.1.2のタグ・添付ZIPは上書きしない。独立版1.1.3の受信仕様は維持する。

## 修正内容

1. 接続開始の全利用者共通20件/日を撤廃。Cloudflareが付与する接続元からサーバー秘密でHMACを生成し、接続元ごと20件/日、入口60件/分。IPv6は/64単位。クライアントが送る独自ヘッダーは上書きし、DO側では欠落を拒否する。YouTube照会の共通200件/日はGoogle認証成功後にのみ消費する。未完了申請だけで他の接続元の認証枠を使い切れない。
2. わんコメ版の自己申告名は参加キーワード直後の『名前』に限定。名前未申告なら後の参加時に初めて登録でき、登録後はコメントから上書きできない。独立版の旧構文は維持。
3. 投稿用の名前を45 UTF-16単位以内に整形。長いハンドルを途中で切ってメンションしない。単発のINVALID_MESSAGE/REQUEST_EXPIRED/DUPLICATE_CONFLICTでBot全体を停止しない。再送は行わない。
4. わんコメ提供userIdを、UC形式に限定せずそのまま使用。既存IDとsource+IDのハッシュ方式を維持。表示名やハンドル一致で別人を統合しない。
5. filterCommentの第3引数UserNameDataから、idとserviceが一致する利用者のmemoを受信。SQLite・バックアップへ保存し、管理画面にtextContentで表示。未取得なら前回メモを保持し、明示的空文字なら消去。次の受信コメントで更新する。OBS・共通Botには送らず、わんコメへの書き戻しもしない。
6. Bot設定値・JSON・DBの異常はBotだけ停止。元のファイル/レコードと待機列データを保全。
7. 同じ配信で稼働中のstartは冪等。タイマー、世代、未送信通知を維持し、画面の起動ボタンを無効化。

わんコメ連携の参照: [公式プラグインAPI](https://onecomme.com/en/docs/developer/plugin/)、[公式UserNameData型](https://onecomme.com/sdk/interfaces/types_UserData.UserNameData)。メモ編集直後の即時同期ではなく、次のコメント受信時に反映する。

## 検証

- Python 350件、JavaScript 27件、共通バックエンド38件、計415件成功。Pythonの依存ライブラリの非推奨警告2件。
- 型検査・Workerビルド成功。Miniflare/workerdの実ランタイム上でも、外部Google応答を模擬してOAuth・SQLite・停止設定を検証。
- 新規Windows実行ファイルと導入後のファイル双方で、隔離保存先の起動、コメント受信、opaque ID、引用名制限、メモ保存、OBS非公開、終了を確認。
- ブラウザーの架空データ画面でメモの文字表示と、稼働中の起動ボタン無効化・停止後の再有効化を確認。
- 実YouTubeコメント受信・配信者Google認証・Bot実投稿・OBS実機操作は今回実施していない。

## 運用上の残りの制約

接続元別制限は共有回線（NAT）の利用者間で共有される。複数接続元を使う分散攻撃への完全な対策ではない。一般公開の規模拡大時はTurnstile等の検証・監視の追加を検討する。現在のGoogle OAuthテストユーザー制限とBot投稿停止は維持する。

## 適用先

- 導入済みプラグインを更新。前の本体は `%LOCALAPPDATA%/JoinQueuePluginBackups/before-audit-fixes-20260923` に退避。実利用のWaitingListAppOneComme内の待機列・認証データは操作していない。
- Cloudflare Quick Editへ検証済みWorkerを反映し、Active版 `b05ade34` を確認。既存DOの名前とnamespaceは維持。
- 本番のhealthと一時的な未認証接続の開始・状態確認・失効を1件だけ検証して成功。Bot投稿停止による拒否も確認。BOT_POSTING_ENABLED/BOT_AUTH_ENABLEDはfalse、CHANNEL_CONNECT_ENABLEDはtrueで、既存4シークレットは暗号化状態のまま維持。
- Worker bundle SHA256: `60cf9768b83caf8d6ea25bc37f16917d0581059ecae3925385149cae4fd88966`。
- 公開GitHub Releaseの更新、mainへのマージ、課金設定変更は実施しない。
