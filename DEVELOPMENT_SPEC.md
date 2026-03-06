# plugin-3kHz 仕様書（開発向け）

このドキュメントは、現在実装されている Chrome 拡張（`extension/content.js`）の処理仕様をまとめたものです。

## 1. 概要

- 正式名称: **麻雀参加型メンバーを管理するやーつ**
- 対象: YouTube ライブ配信ページ上のチャット
- 目的: チャット内の「参加希望」を自動検知し、参加者管理と次回対局候補の可視化を行う
- 実行形態: Content Script としてページ内で動作
- 配布形態: **Chrome 拡張アプリとして配布する**
- 開発スコープ: 今後の開発・再集計は **Chrome 拡張アプリとして完結**する

## 2. 定数・基本ルール

- 検知キーワード: `参加希望`
- 1回あたりの候補人数: `3名`
- 候補表示範囲: 「次回」「次々回」の2枠（計最大6名）

## 3. 管理データ（状態）

拡張は以下の状態をメモリ上で保持する。

- `participants`（`Map`）
  - キー: ユーザー名
  - 値: `{ joinNo, count }`
  - `joinNo`: 初回登録順の番号（1始まり）
  - `count`: 対局参加回数（`+1`操作で増加）
- `joinOrder`（配列）
  - 参加登録順のユーザー名リスト
- `nextRounds`（二次元配列）
  - `nextRounds[0]`: 次回候補3名
  - `nextRounds[1]`: 次々回候補3名
- `processedMessageKeys`（`Set`）
  - DOM / API の両経路で共通利用する重複排除キー集合
- `chatObserver`
  - チャット監視用 `MutationObserver`
- `domSourceHealthy` / `apiSourceHealthy`
  - 各取得経路の稼働状態（UI表示にも反映）

## 4. 処理フロー

### 4.1 初期化

1. 画面右上に管理UI（`#yt-join-manager`）をマウント
2. API補助経路（`chat_api_source.js`）のポーリングを開始
3. チャット監視（DOM通常経路）の接続を試行
   - 監視対象がまだ存在しない場合は、2秒ごとに再試行

### 4.2 通常経路（DOM監視）

- `yt-live-chat-app` または `#chat` に対して `MutationObserver` を設定
- 追加されたノードから以下を検知し、メッセージ処理を実行
  - `yt-live-chat-text-message-renderer`
  - `yt-live-chat-paid-message-renderer`
- 既存ノードの初回走査（再同期）も実施

### 4.3 補助経路（Live Chat APIポーリング）

- `https://www.youtube.com/youtubei/v1/live_chat/get_live_chat` を定期呼び出し
- `chat_api_source.js` が `author / authorId(channelId) / message / timestamp` を抽出
- APIレスポンスの `timeoutMs` を優先し、未取得時は 5 秒間隔で再試行
- APIキーや continuation が取得できない場合は失敗扱いにし、再試行を継続

### 4.4 メッセージ統合と重複排除

1. DOM / API どちらのメッセージも `ingestMessage` に集約
2. 重複排除キーを以下で生成
   - `authorId(なければauthorName)` + `publishedAt(秒バケット)` + `message`
3. 既処理キーはスキップし、新規のみ登録判定へ進む
4. 本文に `参加希望` を含む場合に参加者登録

## 5. フェイルオーバー方針

- **API失敗時**
  - `apiSourceHealthy = false` としつつ、DOM経路は継続
- **DOM失敗時**
  - `domSourceHealthy = false` としつつ、API経路は継続
- **両方失敗時**
  - UIは「再同期待ち」を表示し、各経路の再試行ループで復旧を待機

## 6. 再同期タイミング

- DOM: `MutationObserver` 接続直後に既存チャットノードを全走査
- API: 初回 continuation 取得後に即時 1 回目を実行
- セットサイズ上限到達時: `processedMessageKeys` を間引いてメモリ使用量を抑制

## 7. 参加者登録・更新仕様

### 7.1 参加者登録

- 条件
  - ユーザー名が空でない
  - まだ `participants` に存在しない
- 登録内容
  - `joinNo = joinOrder.length + 1`
  - `count = 0`
- 登録後処理
  - 候補枠を再計算
  - UI再描画

### 7.2 参加回数加算（`+1` ボタン）

- 対象ユーザーの `count` を `+1`
- 加算後に候補枠を再計算し、UI再描画

### 7.3 配信リセット

- `participants` / `joinOrder` / `nextRounds` / `processedMessageKeys` を初期化
- 初期化後にUI再描画

## 8. 候補選出ロジック

候補は以下の優先順でソートして選ぶ。

1. `count` が少ない順
2. `count` が同じ場合は `joinNo` が小さい順

ソート後の並びから:

- 先頭3名 → 「次回」
- 4〜6番目 → 「次々回」

## 9. UI仕様

管理UIはページ右上に固定表示され、以下を提供する。

- ヘッダー
  - タイトル: 麻雀参加型メンバーを管理するやーつ
  - ボタン: `配信リセット`
- 参加者一覧テーブル
  - 列: `No` / `ユーザー名` / `回数` / `操作(+1)`
- 参加予定表示
  - 「次回」「次々回」を各3枠で表示
  - 空き枠は `-` 表示
- 取得経路表示
  - `通常+補助（DOM+API）` / `通常（DOM）` / `補助（API）` / `再同期待ち`

また、ユーザー名は HTML エスケープして表示し、UI埋め込み時の文字列崩れや注入リスクを軽減する。

## 10. 権限・設定方針

- `permissions`
  - `storage`: API設定値（将来追加）や経路状態の保存に限定して使用
- `host_permissions`
  - `https://www.youtube.com/*`: 対象ページへの挿入に必須
  - `https://www.youtube.com/youtubei/v1/live_chat/*`: Live Chat API補助経路に限定
- 方針
  - 取得対象は `author/channelId/message/timestamp` に限定
  - 参加管理用途に不要なデータは保持しない（最小権限・最小収集）

## 11. 制約・注意事項

- 状態はメモリのみで保持されるため、ページ再読み込みで消える
- キーワードは現時点で固定（`参加希望`）
- 同一配信中の同一ユーザー重複登録は行わない
- YouTube 側レスポンス仕様変更時は API補助経路のみ影響する可能性がある

## 12. 更新履歴

- 2026-03-06: DOM通常経路 + API補助経路の併用、重複排除、フェイルオーバー、再同期方針を追記
- 2026-03-04: 配布形態を Chrome 拡張アプリに確定し、正式名称を「麻雀参加型メンバーを管理するやーつ」に変更
- 2026-03-04: 実装済み処理に合わせて仕様書化（チャット検知、参加者管理、候補算出、UI仕様を明記）
