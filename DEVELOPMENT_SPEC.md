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
- 重複排除キー: `authorId + publishedAt + message`

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
  - DOM経路とAPI経路をまたいだ重複排除キー集合
- `chatObserver`
  - チャット監視用 `MutationObserver`
- `apiPoller`
  - Live Chat API 定期取得用ポーラー
- `domMonitoringHealthy` / `apiMonitoringHealthy`
  - 各経路の生存状態フラグ

## 4. 処理フロー

### 4.1 初期化

1. 画面右上に管理UI（`#yt-join-manager`）をマウント
2. 通常経路として DOM 監視の接続を試行
   - 監視対象がまだ存在しない場合は、2秒ごとに再試行
3. 補助経路として Live Chat API ポーリングを起動
   - `chrome.storage.local` の `YT_LIVE_CHAT_API_KEY` / `YT_LIVE_CHAT_ID` を優先
   - 未設定時は URL クエリ（`apiKey`, `liveChatId`）を参照
   - どちらも未設定なら DOM 経路のみで継続

### 4.2 通常経路（DOM監視）

- `yt-live-chat-app` または `#chat` に対して `MutationObserver` を設定
- 追加されたノードから以下を検知し、メッセージ処理を実行
  - `yt-live-chat-text-message-renderer`
  - `yt-live-chat-paid-message-renderer`
- 取得項目
  - `authorName`
  - `authorId`（取得できる場合のみ）
  - `message`
  - `publishedAt`（タイムスタンプ属性）

### 4.3 補助経路（Live Chat API）

- エンドポイント
  - `GET https://www.googleapis.com/youtube/v3/liveChat/messages`
- `part=snippet,authorDetails` で定期取得
- 取得項目
  - `author/channelId`
  - `author/displayName`
  - `message`（`snippet.displayMessage`）
  - `timestamp`（`snippet.publishedAt`）
- `pollingIntervalMillis` を優先して次回ポーリング間隔を決定

### 4.4 統合処理（重複排除 + 登録）

1. 受信データ（DOM/API）から `authorId + publishedAt + message` を組み立て
2. 既処理キーならスキップ
3. 未処理キーを保存（上限超過時は古い要素を間引き）
4. メッセージ本文に `参加希望` が含まれるか判定
5. 投稿者名を決定して参加者登録（未登録時のみ）

## 5. 参加者登録・更新仕様

### 5.1 参加者登録

- 条件
  - ユーザー名が空でない
  - まだ `participants` に存在しない
- 登録内容
  - `joinNo = joinOrder.length + 1`
  - `count = 0`
- 登録後処理
  - 候補枠を再計算
  - UI再描画

### 5.2 参加回数加算（`+1` ボタン）

- 対象ユーザーの `count` を `+1`
- 加算後に候補枠を再計算し、UI再描画

### 5.3 配信リセット

- `participants` / `joinOrder` / `nextRounds` / `processedMessageKeys` を初期化
- 初期化後にUI再描画

## 6. 候補選出ロジック

候補は以下の優先順でソートして選ぶ。

1. `count` が少ない順
2. `count` が同じ場合は `joinNo` が小さい順

ソート後の並びから:

- 先頭3名 → 「次回」
- 4〜6番目 → 「次々回」

## 7. UI仕様

管理UIはページ右上に固定表示され、以下を提供する。

- ヘッダー
  - タイトル: 麻雀参加型メンバーを管理するやーつ
  - ボタン: `配信リセット`
- 参加者一覧テーブル
  - 列: `No` / `ユーザー名` / `回数` / `操作(+1)`
- 参加予定表示
  - 「次回」「次々回」を各3枠で表示
  - 空き枠は `-` 表示

また、ユーザー名は HTML エスケープして表示し、UI埋め込み時の文字列崩れや注入リスクを軽減する。

## 8. 障害時挙動・フェイルオーバー

- API経路が失敗しても DOM経路は継続
  - APIポーラーはエラー時にログ出力し、一定間隔で再試行
- DOM経路が接続できなくても API経路は継続
  - DOM監視は2秒周期で再接続を試行
- どちらか片系が生きていれば参加者登録を継続できる

## 9. 再同期タイミング

- 初回起動時
  - DOM監視接続とAPIポーリングを同時開始
- APIポーリング時
  - `nextPageToken` と `pollingIntervalMillis` を使って継続取得
- DOM再接続時
  - 監視開始後に受信した新規メッセージを統合処理へ投入

## 10. manifest 権限方針（最小化）

- `permissions`
  - `storage` のみ（APIキーとライブチャットID設定の読み出し用途）
- `host_permissions`
  - `https://www.youtube.com/*`（画面上DOM監視）
  - `https://www.googleapis.com/*`（Live Chat API 呼び出し）
- 追加権限は不要なものを持たない方針とする

## 11. 制約・注意事項

- 状態はメモリのみで保持されるため、ページ再読み込みで消える
- キーワードは現時点で固定（`参加希望`）
- 同一配信中の同一ユーザー重複登録は行わない
- API補助経路の利用には `apiKey/liveChatId` の設定が必要

## 12. 更新履歴

- 2026-03-06: DOM通常経路 + Live Chat API補助経路の二重化、重複排除キー、フェイルオーバー方針を追記
- 2026-03-04: 配布形態を Chrome 拡張アプリに確定し、正式名称を「麻雀参加型メンバーを管理するやーつ」に変更
- 2026-03-04: 実装済み処理に合わせて仕様書化（チャット検知、参加者管理、候補算出、UI仕様を明記）
