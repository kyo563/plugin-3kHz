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

- `/control`: 実運用の配信者操作画面
- `/overlay`: OBS表示画面
- `/settings`: 設定画面
- `/api/control/*`: `/control` の実運用操作API
- `/api/mock/*`: 開発・テスト用API（後方互換と既存テスト維持のため削除しない）
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
- 次の対戦に移る（参加回数+1）
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

### 12.1 現在地（実装済み）

以下は実装済み。

- `QueueService` / `OverlayStateService` 導入
- SQLite保存・再起動復元
- 外部コメント受信口（`POST /api/comments/receive` / `POST /api/comments/manual`）
- join / cancel の待機列反映
- `declared_player_name` の保存・表示
- 再join時の waiting 最後尾移動
- `/control` による手動調整UI/API（並び替え・末尾移動・削除・申告名編集/削除）
- 40秒状態変更ロック
  - コメント由来の join / cancel / rejoin のみ対象
  - `/control` 手動操作は対象外
  - user_id 単位で管理
  - declared_player_name は判定に使わない
  - userKey生値は保存しない
  - cooldown_seconds を使用
- 参加回数管理
  - move_next 時に current 参加者の参加回数を +1
  - user_id 単位で `participation_counts` に保存
  - 再起動後も復元
  - コメント由来の再参加時に保存済み回数を反映
  - userKey生値は保存しない


### 12.2 次の実装候補

- 参加回数の配信またぎ恒久管理は将来検討
- OBS表示の省略・視認性調整
- 設定画面の実用化
- 実配信前テスト
- 配布準備
