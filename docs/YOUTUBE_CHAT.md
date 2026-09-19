# YouTubeコメント受信（1.1.0）

管理画面上部に配信URL、YouTube Data API v3 APIキーを入力し「コメント受信を開始」を押します。「受信中」を確認して参加受付を開始し、その後の「参加希望」「参加希望 『名前』」「参加辞退」「参加を辞退」を取り込みます。

## キーの準備
Google CloudのプロジェクトでYouTube Data API v3を有効化し、認証情報でAPIキーを作成します。APIの制限はYouTube Data API v3。アプリはPythonのHTTPクライアントから接続するため、ブラウザのHTTPリファラー制限は使用できません。
キーはメモリのみ。ログ・SQLite・バックアップ・ブラウザの保存領域には書きません。停止・終了後は再入力します。外部送信先は固定のGoogle API HTTPSエンドポイントだけです。

## 動作と制約
- 公式videos.listでactiveLiveChatIdを取得し、liveChatMessages.listを継続取得します。指定間隔と最低10秒を守ります。API利用上限があるため、長時間の連続運用時間は割当に依存します。
- 初回ページは履歴として無視。手動再接続後も同様で、停止中のコメントを遡って全件復元する機能ではありません。
- 一時障害はページトークンを維持して最大5回再接続。上限・権限・配信終了は停止理由を表示します。自動で別の配信へ切り替えません。
- 参加受付終了、重複、設定した秒数の状態変更ロック（初期値40秒）は従来どおり。受信件数やコマンド件数は参加人数ではありません。
- 本人識別はチャンネルID。参加希望時にchannels.listでハンドルを取得・最大512人分をメモリにキャッシュ。取得できない場合は表示名を使用。
- 公開ライブのテキストコメントが対象。非公開配信のOAuth認証、チャット投稿、アーカイブのリプレイは含みません。
- 追加のブラウザプロセスやChromeは不要。アプリ終了時にHTTP通信・受信タスクを停止します。

## 検証範囲
モックHTTPによる履歴除外、参加・指定名・辞退、重複、受付終了、通信再試行、APIエラー、停止中通信のキャンセル、管理キー権限を自動検証。実際のAPIキーとライブ配信を使った動作確認は利用者の設定後に必要です。1.1.0の正式配布に含まれます。1.0.0にはこの機能はありません。

## 公式仕様
- https://developers.google.com/youtube/v3/getting-started
- https://developers.google.com/youtube/v3/live/docs/liveChatMessages/list
- https://developers.google.com/youtube/v3/docs/videos
- https://developers.google.com/youtube/v3/docs/channels
