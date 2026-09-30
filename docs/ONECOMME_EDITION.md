# 待機列整理アプリ わんコメ版

## 共通Bot統合 0.1.2（2026-09-22）

利用者ごとのBot OAuthを廃止し、Cloudflare共通バックエンド経由へ変更。プラグイン設定から配信チャンネルの接続、確認、Botの起動・停止を行う。BotのGoogle認証情報はサーバーだけで保持する。

通知は「次グループNOW呼出し」「@JoinQueueBotへの本人順番返信」「15/30分の待機人数・組数案内」の3種類。個別チェックボックスを保存し、起動時は必ず投稿停止。UID・既存SQLite・OBSを引き継ぎ、独立版と過去のリリースは変更しない。

Python 336件、プラグインJavaScript 24件、共通バックエンド34件のテスト成功。Windowsワーカーのビルドと隔離保存先での起動・コメント受信・OBS・停止を確認。設定UIの保存・再読込・個別切替も確認。実配信への投稿は未実施であり、共通サーバーの投稿停止は別途承認まで維持する。検証版として公開する。詳細は [BOT.md](BOT.md)。

以下の1.0.0/1.1.0の記述は履歴。現在のBot仕様は0.1.2を優先する。

## 正式版1.0.0（2026-09-21）

ユーザー指定により今後の開発対象をわんコメ版に統一し、名称を「待機列整理アプリ」とする。正式公開の指示済み。専用タグonecomme-v1.0.0を使用し、独立版1.1.3のタグ・Release・添付・保存先は維持する。mainへはマージしない。

表示用Taikiretsu-Template.zipを配布ZIPと管理画面から提供する。読み取り専用/onecomme-overlayをiframeで描画し、既存レンダラーを共用。cross-site iframe許可とframe-ancestors例外はこのルートのみ。管理APIの認証・Origin検証を維持する。

OBS共通枠は1200×600以上。管理画面で縦480×600・横1200×240を切り替え、保存すると自由編集・フォント・色も反映される。カスタム寸法が共通枠を超える場合はOBS側の寸法変更が必要。

Python318件・JavaScript24件成功。ブラウザで同一iframe内の縦横切り替えと6名表示を確認。実OneCommeでのライブ受信・限定配信・OBS実機へのドラッグ操作は未検証。正式版という名称と実機確認済みを混同しない。

以下は試作時点からの設計・検証記録。

## Bot追加版1.1.0

ユーザー指定で専用YouTubeアカウントによる任意の自動投稿を追加。受信はわんコメ、投稿のみYouTube公式APIとデスクトップOAuth/PKCEを使用。詳細はBOT.md。
初期無効・通知個別切替・10/30分・本人IDによる順位・Botチャンネル除外・接続状態を実装。認証は専用bot.sqlite3へWindows DPAPIで暗号化して保存。既存キューDBと独立版は保全。
全体Python325件成功後、追加の競合・送信曖昧失敗を含むBot10件成功。JavaScript24件成功。ブラウザで30分設定・個別オフ・再読込保存を確認。実OAuth/実配信投稿は未検証のため、このBot追加版はPre-releaseとして扱う。

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
# 管理画面の可変幅・表示項目（2026-09-24、未配布）

2026-09-24 導入済みプラグインへ反映済み（GitHub公開ZIPは変更なし）。`dist/onecomme-control-display-20260924/sankagata-seiretsu` に専用ビルドを作成し、隔離保存先で起動・設定保存・再起動復元・コメント受信・OBSデータ・テンプレート取得を確認後、わんコメ停止中に配置した。配置後の実行ファイルでも同じ試験が成功。元の待機列・設定・認証ファイルはハッシュ一致で変更がないことを確認。旧プラグインと保存データの退避先は `%LOCALAPPDATA%/WaitingListAppOneComme-backups/control-display-20260924-215857`。プラグイン管理上のバージョンは0.1.3のまま。

- わんコメ版の管理画面はウィンドウ幅に追従。NOW・待機列を1行36pxに揃え、長文は省略表示し、各欄のツールチップで全文を確認する。
- アイコン → ユーザー名（@ハンドル、取得できない場合は表示名）→ 申告名（未登録ならYouTubeニックネーム）→ わんコメのメモ → 参加回数の順。待機順は先頭に付く。
- NOW・待機列の上のチェックボックスで上記6項目を個別に表示／非表示。初期値は全表示。未取得の申告名・メモは「—」。名前編集・削除とドラッグ並べ替えは維持。
- 表示選択は管理者認証の必要な `/api/settings/control-display` から、既存SQLite内の独立した `control_display` テーブルへ保存。待機列のrevision・Undo・OBS設定は変更しない。キューのJSONバックアップ対象外で、復元・キューリセットでも表示選択を保持する。
- 保存失敗・応答不明時は保存済み表示へ戻して再読み込みを促す。読込失敗時は設定の上書きを防ぐためチェック操作を無効化する。
- Python 353件・JavaScript 35件成功。隔離DB・専用ポートのブラウザーで幅320/640/1280px、36pxの行高、横はみ出しなし、チェック切替と再読込復元を確認。実参加者データ・Bot接続・既存配布物は変更していない。

## 0.1.4 正式公開（2026-09-30）

GitHub Release `onecomme-v0.1.4`（ID 400028895）をdraft=false・prerelease=false・Latestとして公開。タグは `01e8a85161fc10fa54e29f0a355f00e90fee7870`。本体ZIP・テンプレートZIP・SHA256SUMS.txtの3添付を匿名でダウンロードし、サイズとSHA256がローカルの検証済み成果物と一致することを確認。旧リリース・タグは変更していない。

管理画面改善、NEXT保護、OBS参加回数、共通バックエンドの認証フォーム修正を含む新版を準備。Python 369件・JavaScript 38件成功、バックエンドは前回39件成功。最新Windows x64 ZIPは `dist/onecomme-release-0.1.4-priority/Taikiretsu-Seiri-App-OneComme-0.1.4-windows-x64.zip`、SHA256 `d5a1019efb8302942f68763fc74bba07cc9764d075146f88a96ac1f29879703b`。アーカイブ検証成功。旧候補 `dist/onecomme-release-0.1.4` は今回の追加機能を含まないため公開に使用しない。ビルド出力の置換がWindowsで拒否されたため、新しい出力先で再ビルド・パッケージ化した。

2026-09-30 わんコメ終了後、配布実行ファイルと導入先の実行ファイルの両方で隔離保存先による起動・終了・再起動復元・コメント受信・NEXT保護・OBS参加回数・テンプレートZIP取得の試験に成功。導入先201ファイルは配布候補とハッシュ一致、元の待機列・設定・認証ファイルのハッシュ不変を確認。旧プラグインと保存データの退避先は `%LOCALAPPDATA%/WaitingListAppOneComme-backups/release-0.1.4-20260930`。

本番バックエンドはCloudflare版 `a26512e6` へ更新。使い捨て接続のネイティブフォーム操作でGoogleアカウント選択画面へ到達し、NOT_FOUNDの修正を確認。テスト接続は失効済み。Google承認・チャット実投稿は実施しない。公開説明は `docs/RELEASE_ONECOMME_0.1.4.md`。確認用の分離HTTPサーバー（18876）はChromeがERR_BLOCKED_BY_CLIENTで拒否したため追加した表示項目の実画面確認は未完了。確認サーバーは終了済み。参加回数の保存・復元・リセット・プレビューは自動テストで確認した。

### NEXT保護・回数表示

- わんコメ版だけ `QueueService.protect_next` を有効化。NOWが満員の場合、NEXT3名より後ろのうち参加回数が多い人の直前へ挿入する。既存NEXTと同じ優先度の先着順を維持する。比較する回数の基準自体は従来どおり。
- OBS表示設定 `show_participation_number`（初期false）は既存のSQLite表示設定へ保存し、JSONバックアップにも含む。出力は既存display_nameへ文字列として付記し、利用者IDや内部履歴をOBSへ追加公開しない。
- 回数はユーザー確認により現在の配信履歴の対戦済み回数+1。募集枠へは付けない。名前表示4方式と縦横の共通処理に適用。チェックボックスの保存・再読込・リセット、元に戻す・配信切替・再起動・バックアップ復元を検証。
