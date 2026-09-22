# 0.1.2 共通Bot統合・検証版

- 次グループのNOW呼出し、@JoinQueueBotへの本人順番返信、15/30分ごとの待機人数・組数案内を個別に切り替えられます。
- 参加希望・辞退・初回NOW補充には返信しません。
- コメント取得はわんコメ、待機列・OBSは既存アプリ、投稿はCloudflare共通Bot。利用者ごとのBot OAuthは不要です。
- プラグイン設定から配信チャンネル接続と起動・停止ができます。通知設定は保存し、再起動時は安全のためBot停止から開始します。
- 既存UID・待機列・履歴・OBS設定を維持。旧Google認証レコードは読み取り・送信・自動削除しません。

## 検証

Python 336件、JavaScript 24件、共通バックエンド34件成功。Windows x64ワーカーをビルドし、配布ZIPを展開した状態で隔離保存先への起動、管理画面、コメント受信、表示、停止を確認。設定UIの個別切替・再読込保存も確認。

Cloudflare本番Workerへ配置済み。公開URLでhealthと一時ペアリングの開始・画面・状態取得・解除を確認。Bot投稿は503 SERVICE_DISABLED、運営者用Bot再認証入口は404で停止を確認。既存Secret・Durable Objectは保持し、課金設定は変更していません。

Google OAuthに読み取り専用scopeと配信者用callbackを追加済み。ただしGoogleアプリはテスト中で、配信者アカウントのテストユーザー登録と本人による認証が必要です。Bot投稿の運営側有効化・実配信投稿は未実施です。この版を一般利用可能・実配信確認済みとは扱いません。

## 配布物

`Taikiretsu-Seiri-App-OneComme-0.1.2-windows-x64.zip`

SHA256: `6dc50e2600de6c37a90e64c4cbc8e576ab684255a6f0f431c3bf36d5405ff288`

更新時はわんコメを閉じ、旧プログラムフォルダをプラグイン一覧の外へバックアップして入れ替えます。`%LOCALAPPDATA%\WaitingListAppOneComme` は削除しないでください。独立版・旧Release・タグは変更しません。
