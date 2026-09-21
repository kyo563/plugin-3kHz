# 待機列整理アプリ わんコメ版

## 正式版1.0.0（2026-09-21）

ユーザー指定により今後の開発対象をわんコメ版に統一し、名称を「待機列整理アプリ」とする。正式公開の指示済み。専用タグonecomme-v1.0.0を使用し、独立版1.1.3のタグ・Release・添付・保存先は維持する。mainへはマージしない。

表示用Taikiretsu-Template.zipを配布ZIPと管理画面から提供する。読み取り専用/onecomme-overlayをiframeで描画し、既存レンダラーを共用。cross-site iframe許可とframe-ancestors例外はこのルートのみ。管理APIの認証・Origin検証を維持する。

OBS共通枠は1200×600以上。管理画面で縦480×600・横1200×240を切り替え、保存すると自由編集・フォント・色も反映される。カスタム寸法が共通枠を超える場合はOBS側の寸法変更が必要。

Python318件・JavaScript24件成功。ブラウザで同一iframe内の縦横切り替えと6名表示を確認。実OneCommeでのライブ受信・限定配信・OBS実機へのドラッグ操作は未検証。正式版という名称と実機確認済みを混同しない。

以下は試作時点からの設計・検証記録。

2026-09-21のユーザー指定による別系統。独立版1.1.3のRelease・タグ・保存先は変更しない。
ブランチ codex/onecomme-edition。配布手順は onecomme/README.txt。

## 実装

- 公開プラグインのinit/destroy/filterComment/requestと専用ページを使用。
- Node.jsプラグインが同梱の軽量Python HTTPワーカーを自動起動。専用GUI/.NET/WebView2不要。
- 子プロセスの標準入力切断で自動終了。強制終了は自分が起動した子だけ。
- 管理画面は公式のプラグインURLからブラウザで開く。本体メイン画面への埋め込みではない。
- キュー・名前・累計・履歴・設定・バックアップ・OBS表示は既存Python処理を共用。
- 別SQLite保存先WaitingListAppOneCommeと別ポート18765。独立版への自動移行/逆移行なし。
- コメントは同期でそのままわんコメへ返す。送信待ち500件、直列送信、3秒タイムアウト。
- 配信を明示選択し、開始以前のコメントを除外。最大32配信の候補。YouTube UCチャンネルID必須。
- 公式APIと同じsource/userKeyで本人識別。名前をID代用しない。既存JSONバックアップを復元可能。
- APIキー不要。限定配信の可否はわんコメの取得結果に依存する。

## 未確認・制約

わんコメ9.1.1の実プラグイン読込、実YouTubeコメントのID/HTML/ハンドル形式、限定配信は未確認。
対応はYouTubeのみ。わんコメAPI標準ポート11180前提。正式公開後も未確認事項は明記する。
ポート18765競合は起動失敗として扱い、既存アプリを停止しない。
初回過去コメント除外は配信選択時刻と公開timestampで判定。Windowsの時刻分解能差として境界の20msだけ許容する。PC時計が大幅にずれている場合は登録できない。
プラグイン停止中のコメントは遡って登録しない。受信キュー上限超過は管理ページに警告件数を表示。
起動時は常に配信未選択。プラグインが無効ならOBS表示は更新できない。
OneCommeプラグインURLから管理キー付きページへ遷移するため、OneCommeのAPIアクセスを外部へ公開しない。
コメント本文・ログイン情報は外部送信せず、通常コメントはSQLiteへ記録しない。
SDK/わんコメ本体バイナリは同梱しない。プラグインコードは独自実装。

## 根拠

- https://onecomme.com/docs/developer/plugin/
- https://onecomme.com/docs/developer/onesdk-js/ （Comment/CommentData公開型）
- https://onecomme.com/docs/feature/plugins/
- https://github.com/OneComme/OneCommeOrderSpeechPlugin （専用ページ・REST responseラッパー）
- https://onecomme.com/terms/

## ビルド

`.venv/Scripts/python.exe -m PyInstaller --noconfirm --distpath dist/onecomme-worker --workpath build/onecomme-worker onecomme-worker.spec`

`.venv/Scripts/python.exe scripts/package_onecomme.py`

独立版のpackage_release.py・dist/releaseは使わない。

## 検証結果

Python全体314件成功後、追加の旧版バックアップ移行を含むわんコメ関連3件成功。JavaScript全体23件成功。
配布ワーカーのプラグイン経由起動、選択前コメント除外、参加登録、OBS投影、別DB保存、停止でHTTPとプロセスが終了することを隔離環境で確認。
元の独立版DBを変更せず累計11回をバックアップ経由で引き継ぐテスト成功。
実際のOneComme本体内での読込とライブ配信受信は未確認。

最終ZIPを展開して3回連続で起動・参加・OBS・終了に成功。時刻境界の20ms許容を回帰検証。
試作ZIP SHA256: f32158320d75a8dbcd1f139a938ddb9f959aed4a7bd2335dea39751ef07f7465

## 0.1.1 管理ページ遷移修正
わんコメlocalhostからワーカー127.0.0.1への遷移がcross-siteで拒否される問題を修正。わんコメ版のGET /control、navigate/documentのみ例外としAPI・Origin・iframe・fetchの制限は維持。独立版の動作変更なし。関連Python25/Node2と別ポートでの実HTTP遷移・API認証確認成功。利用中ワーカーを保全したため新版ワーカーの同ポート起動は未実施。Windows再ビルド済み。
