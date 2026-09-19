# 外部コメント入力の境界

外部製品は未指定。アプリは配信サイトAPIへ直接接続しません。以下は製品に依存しない入力契約で、特定製品との互換性を保証しません。

`POST http://127.0.0.1:8080/api/comments/receive`

- `Content-Type: application/json`
- `Authorization: Bearer <受信キー>`（OBS導入画面でコピー）
- source: 1～64文字。製品/取得元を安定した値で識別。
- externalMessageId: 省略可能、最大512文字。同一sourceの同一IDは直近1000件で重複除外。再起動時にキャッシュは消える。
- receivedAt: 必須、1～64文字。アダプターはISO8601のUTC時刻を送る。
- displayName: 必須、1～200文字。
- userKey: 必須、1～512文字。取得元内で一意かつ安定した値。表示名で代用しない。
- message: 必須、最大4096文字。
- badges: owner/moderator/memberの真偽値、省略可。初期版OBSには表示しない。
- 本文全体はUTF-8で64 KiB以下。

成功は200で `status=accepted`。重複は `duplicate=true, command=ignore`。acceptedは待機列変更の保証ではなく、受付終了・40秒ロックなら変更されない。401はキー、403はOrigin、413はサイズ、422は内容を確認する。

外部サイトからのブラウザ送信は許可しない。ローカルアダプターはOriginヘッダーを付けず、HTTPクライアントで送信する。受信キーでは管理状態の読取・リセット・終了はできない。
本文・userKey生値・メッセージID・キーはSQLite/診断ログに保存しない。IDなし入力を推測で重複排除しない。製品選定後に再送・欠落・順序・再接続を検証する。


## YouTubeのハンドルとニックネーム（preview.8）
受信JSONに任意項目 `youtubeHandle`（例 `@sample`）、`youtubeNickname`（例 `あおい`）を追加しました。`displayName` は従来どおり必須。`source: "youtube"` またはyoutubeHandleがある場合、youtubeNicknameが省略されればdisplayNameをニックネームとして使います。本人識別のuserKeyはハンドルや名前ではなく安定したIDを渡してください。
YouTubeのハンドルを推測・直接取得する機能はありません。外部製品/アダプターが両方の値を取得して渡す必要があります。ハンドルがない場合は従来displayNameをアカウント名表示の代わりに使います。申告名は配信者の編集を優先し、それがなければ「参加希望 『名前』」の指定、次にニックネームを採用します。非YouTubeの旧入力は参加希望コメントの名前パーサーを維持します。
例: `{"source":"youtube","receivedAt":"2026-09-19T00:00:00Z","externalMessageId":"example-1","displayName":"あおい","youtubeHandle":"@sample","youtubeNickname":"あおい","userKey":"stable-channel-id","message":"参加希望"}`
