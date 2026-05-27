# 待機列整理アプリ 開発仕様

## 1. この文書の位置づけ

この文書は、ローカルWebアプリ版の開発仕様です。
正本仕様は `仕様書/待機列整理アプリ_仕様書_v0.1.md` とします。

## 2. 現行アーキテクチャ（MVP）

- ローカルWebアプリ
- OBSブラウザソース（`/overlay`）
- 管理画面（`/control`）
- 設定画面（`/settings`）
- SQLite保存（再起動復元）
- チャット入力口は `ChatProvider`（`ExternalChatProvider` / `ManualTestProvider`）

> 本アプリは待機列整理アプリであり、配信サイトAPIへの直接接続はMVPの主対象にしません。

## 3. 主要画面・経路

- `/control`: 管理画面
- `/overlay`: OBS表示画面
- `/settings`: 設定画面
- `/api/*`: 操作用API
- `/ws`: 状態同期用WebSocket（または同等経路）

## 4. コンポーネント責務

| コンポーネント | 役割 |
|---|---|
| ExternalChatProvider | 外部チャット取得アプリケーションからコメントデータを受け取る |
| CommentNormalizer | 受信コメントを内部形式に正規化する |
| CommandDetector | 参加希望・取消などのワードを判定する |
| QueueService | NOW / NEXT / QUEUE を管理する |
| OverlayStateService | OBS表示用状態を生成する |
| PersistenceService | 設定・状態・操作ログを保存する |
| ControlApi | 管理画面からの操作を受け付ける |

## 5. ChatProvider再定義

```text
ChatProvider
├─ ExternalChatProvider
└─ ManualTestProvider
```

- `ExternalChatProvider`: 外部チャット取得アプリケーションから正規化済みまたは準正規化コメントを受け取る入力口
- `ManualTestProvider`: 開発・デモ・OBS確認用に手動/テストデータを投入する

## 6. 受信コメント内部形式

```json
{
  "source": "external",
  "externalMessageId": "optional",
  "receivedAt": "2026-01-01T00:00:00Z",
  "displayName": "視聴者名",
  "userKey": "temporary-or-provider-user-key",
  "message": "参加希望",
  "badges": {
    "owner": false,
    "moderator": false,
    "member": false
  }
}
```

- `userKey` は外部取得元が一意識別子を提供する場合のみ使用
- 一意識別子がない場合、同一ユーザー判定精度は低下しうる
- `externalMessageId` は重複処理用の一時データ
- `message` は判定後に長期保存しない


## 6.1 コメント受信API仕様（固定）

### POST /api/comments/receive
外部チャット取得アプリケーションからコメントを受け取る入口。

### POST /api/comments/manual
開発・検証・デモ用に手動コメントを投入する入口。

受信payload（`ReceivedComment`）:
- `source`
- `externalMessageId`
- `receivedAt`
- `displayName`
- `userKey`
- `message`
- `badges.owner` / `badges.moderator` / `badges.member`

運用ルール:
- duplicate時レスポンスは `{"status": "accepted", "duplicate": true}` を維持する
- `message` は判定用の一時利用のみ
- `externalMessageId` は重複除外用の一時利用のみ
- `userKey` は将来の同一ユーザー判定用だが、生値を長期保存しない
- `badges` は判定補助用であり、MVPでは長期保存しない
- コメント本文 / `externalMessageId` / `userKey` 生値はSQLiteへ長期保存しない

## 7. データ保存方針

SQLiteには、運用上必要なデータを保存します。

保存対象:
- アプリ設定
- 検知ワード設定
- 受付状態
- 表示設定
- 一時的な待機列状態
- 参加回数
- 操作ログ

長期保存しない対象（原則）:
- コメント本文
- チャットログ全文
- ユーザー名履歴
- ユーザーID生値
- アイコンURL
- メッセージID
- 投稿時刻の詳細ログ
- ギフト情報

外部チャット取得アプリケーション由来のコメント生データは、待機列整理に必要な範囲で一時利用のみとし、二次利用目的で保存しません。

## 8. 外部連携方式と禁止事項

外部チャット取得アプリケーションとの連携は、**公式に許可された方法のみ**を使います。
具体方式は対象アプリ仕様に合わせて決定します。

候補（一般論）:
- HTTP
- WebSocket
- ローカルAPI
- 公式プラグイン機構
- 公式に許可されたファイル出力
- その他、明示的に許可された方式

禁止事項:
- 外部アプリ本体の改造
- 内部DBの直接参照
- 内部設定ファイル解析
- 非公開API利用
- 通信内容解析
- リバースエンジニアリング
- 外部アプリ本体の同梱配布
- ロゴ/素材/ソースコード流用
- 公式と誤認させる表記
- 取得データの二次利用目的保存

## 9. MVP範囲

MVP必須:
- 外部チャット取得アプリケーションからコメントデータを受け取る
- 受信データを正規化する
- 参加希望ワードを判定する
- 取消ワードを判定する
- NOW / NEXT / QUEUE に反映する
- 管理画面に反映する
- OBS表示に反映する

MVP対象外（将来検討）:
- 配信サイトAPIへの直接接続
- 配信URLから直接取得
- 直接チャット取得方式の実装（必要時のみ将来検討）

## 10. 維持する既存仕様

- ローカルWebアプリ方式
- OBSブラウザソース
- `/control` `/overlay` `/settings`
- SQLite
- NOW / NEXT / QUEUE
- 視聴者3人固定
- 参加者募集中表示
- 受付開始・受付終了
- 次へ進める
- 手動追加/削除
- 簡易並び替え
- 参加回数管理
- 低消化回数優先モード

## 11. 未確定事項

- 外部チャット取得アプリケーションとの具体連携方式
- 外部由来の一意ユーザー識別子の取得可否
- 外部由来データの保存範囲
- 参加回数を配信をまたいで保持するか、同一配信内に限定するか

## 12. 開発ロードマップ

### 12.1 現在地

現在は、FastAPIベースの画面モックとWindows向け簡易起動導線が整った段階です。

完了済み:
- `/control` 管理画面モック
- `/overlay` OBS表示モック
- `/settings` 設定画面モック
- `/api/state`
- `/api/overlay-state`
- `QueueService` / `OverlayStateService` の分離
- `PersistenceService`（インメモリ境界）の導入
- `app/main.py` から `app/routes/` へのAPI・ページroute分離
- `start.bat` によるWindows簡易起動

この段階は、画面構成・操作感・OBS表示を確認するためのモック完成段階であり、MVP本実装完了ではありません。

### 12.2 今後の開発順序

MVP完成までは、以下の順序で進めます。

1. モック検証
   - `start.bat` による起動確認
   - `/control`、`/overlay`、`/settings` の表示確認
   - OBSブラウザソースでの表示確認
   - テスト参加者操作によるNOW / NEXT / QUEUEの挙動確認

2. 本実装の土台整理
   - `mock_state.py` に集中している責務を段階的に分離する
   - `QueueService` / `OverlayStateService` は完了
   - `PersistenceService` 境界（インメモリ）は完了
   - `ControlApi` 相当のroute分離は完了
   - APIの外部挙動はなるべく変えず、内部構造を整理する

3. SQLite保存（実装済み）
   - 受付状態、NOW、waiting、参加回数、設定、操作ログを保存する
   - 起動時に状態を復元する
   - `next` status は作らない
   - `waiting` 上位3件をNEXT、4件目以降をQUEUEとして扱う
   - 「参加者募集中」はDBに保存しない

4. 外部コメント受信口（実装済み）
   - 受信APIは `POST /api/comments/receive` と `POST /api/comments/manual` を提供済み
   - `ExternalChatProvider` は外部チャット取得アプリケーションからの入力を受ける
   - `ManualTestProvider` は開発・検証・デモ入力を受け、`source=manual` に補正する
   - `CommentReceiveService` は `externalMessageId` の重複除外（インメモリ、再起動非保持）を行う
   - レスポンスは `status` / `duplicate` / `command` を返す
   - join / cancel は待機列へ反映される
- 同一ユーザーが再度 join した場合、既存位置を削除して waiting 最後尾へ並び直す
- 再join時、declared_player_name が指定されていれば更新する
- 再join時、declared_player_name が指定されていなければ既存値を維持する
- 再join時、participation_count は維持する
- 受付停止中は新規joinも再joinも受け付けない（順番変更しない）


6. コメント正規化・コマンド判定（実装済み）
   - `CommentNormalizer` は前後空白除去、全角空白統一、連続空白圧縮、改行/タブ空白化、全角英数字半角化、英字小文字化を行う
   - joinは正規化後文字列に **`参加希望`**（連続4文字）が含まれる場合のみ
   - ただし join 除外は `参加希望者` / `参加希望順` のみ
   - cancelは `参加辞退` または `参加を辞退` を含む場合のみ
   - joinとcancelが同時に含まれる場合は cancel を優先
   - joinコメントで `参加希望 名前 <申告名>` を含む場合、`declared_player_name` をレスポンスへ返す
   - `declared_player_name` は待機列に反映され、OBS表示は設定値に応じて `display_name` を整形して返す
- `/api/overlay-state` は `show_declared_player_name_on_overlay` を返さない
   - コメント本文・正規化本文・`externalMessageId`・`userKey` 生値は保存しない
   - `declared_player_name` の実値もログ保存しない
6. 待機列本ロジック
   - NOWが3人未満で受付中の場合、新規参加希望者をNOWへ直接補充する
   - NOWが満員の場合はwaitingへ追加する
   - 取消、再参加、重複、次へ進める、手動追加、手動削除、上下移動を整理する
   - 低消化回数優先モードと40秒ロックを実装する

7. 管理画面の実用化
   - NOW / NEXT / QUEUEを明確に表示する
   - 参加回数を管理画面に表示する
   - 手動操作、操作ログ、エラー表示、接続状態表示を整える

8. OBS表示の仕上げ
   - OBS側には参加回数や内部情報を表示しない
   - `/api/overlay-state` は表示専用の最小レスポンスを維持する
   - 長い名前、省略表示、背景透過、視認性を確認する

9. 設定画面の最低限実装
   - 参加希望ワード
   - 取消ワード
   - 表示タイトル
   - 受付初期状態
   - 外部連携設定
   - OBS表示URLコピー
   - 設定保存・復元

10. 実配信前テスト
    - 参加、取消、再参加、重複、長い名前、絵文字、受付終了中の参加希望、QUEUE大量、再起動復元、OBS再読み込みを確認する
    - 1時間程度の疑似配信運用で破綻しないことを確認する

11. 配布準備
    - `start.bat` の安定化
    - README整備
    - OBS設定手順
    - トラブルシュート
    - exe化はMVP本実装が固まってから検討する

### 12.3 次に着手する推奨PR

次に着手するPRは、いきなりSQLite実装ではなく、サービス層分離を優先します。

推奨:
- `QueueService` の導入
- `OverlayStateService` の導入
- 現在の `mock_state.py` のロジックを段階的に移す
- API挙動は極力変えない
- 既存テストを維持する

理由:
SQLiteや外部コメント受信を先に入れると、`mock_state.py` に責務が集中し続け、後から分解しにくくなるためです。


## コメントコマンドの待機列反映（#32次段階）
- join / cancel の検出結果を待機列へ反映。
- join時に declared_player_name を participants へ保存。
- user_id は source + userKey のハッシュで保存し、生の userKey は保存しない。
- 管理画面は declared_player_name を常に併記。
- OBSは show_declared_player_name_on_overlay=true の場合のみ併記。
- /api/overlay-state は declared_player_name の個別フィールドを返さず、整形済み display_name のみ返す。
- コメント本文・正規化本文・externalMessageId・userKey生値・badges詳細は保存しない。
