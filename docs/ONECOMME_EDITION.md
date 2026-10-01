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

## 0.1.4 OBS背景・フォントサイズ追加更新（2026-09-30）

ユーザー指定により0.1.4を維持。`background_color`（初期黒）・`background_transparency`（整数0～100、初期100）・`auto_fit_font`（初期true）を表示設定へ追加。背景はパネル領域にRGBAとして適用し、文字のopacityは1を維持。文字サイズは従来の12～96px、自動縮小をOFFにすると指定pxを優先する。枠外はクリップするため画面の案内で領域の調整を説明。SQLite保存、既存バックアップの初期値補完、バックアップ復元、表示設定リセットに対応。

Python 380件・JavaScript 41件成功。IABの分離保存先で、縦／横、背景#123456・透過35％（rgba alpha0.65）、透過0／100％、56px固定、自動縮小28.5714px、保存後の再読込復元を実測。配布ファイルと導入先ファイルの両方で起動・終了・再起動・背景設定保存・既存機能のスモーク試験が成功。確認サーバーは終了。ユーザーの実データは変更しない。

追加更新ZIP: `dist/onecomme-release-0.1.4-obs-style/Taikiretsu-Seiri-App-OneComme-0.1.4-windows-x64.zip`、SHA256 `dcac28640dc8513a23a1cd3cbd031a6d1d67e30f22fc727aa4e7c8ae433b0a5b`。導入先201ファイルのハッシュ一致と元データ不変を確認。バックアップ: `%LOCALAPPDATA%/WaitingListAppOneComme-backups/release-0.1.4-obs-style-20260930`。GitHub添付の初回版は名前を変更して保管し、初回タグは移動せず、追加更新のソースコミットを公開説明に明記する。Botサーバー・Google・課金設定は変更しない。

追加更新の公開完了: Release ID 400028895を正式版のまま更新。本体ZIP・SHA256SUMS.txtの通常名は追加更新版へ切替済み。初回本体は `Taikiretsu-Seiri-App-OneComme-0.1.4-windows-x64-initial.zip`、初回チェックサムは `SHA256SUMS-initial.txt` として削除せず保持。テンプレートZIPと初回タグは変更なし。更新ソースは `13522b3542a22cef7b79370eb12755395c04860b`。通常URLから匿名ダウンロードした本体ZIP・チェックサムがローカル成果物と一致することを確認。導入済みファイルでの試験後も元データのハッシュ不変を再確認。

ユーザーの追加指示「差し替えてください。更新前のものはもう誰も使いません」に従い、上記の初回本体ZIP（asset 600884978）と初回チェックサム（asset 600885063）を公開添付から削除。公開説明から保管用添付の案内を除いた。正式版0.1.4には更新版本体ZIP・テンプレートZIP・SHA256SUMS.txtの3添付のみ残り、本体のSHA256が検証済み追加更新版と一致することを再確認。ローカルの初回配布ファイル・バックアップ、既存タグ、他のリリースは変更していない。

## PC内フォント選択（2026-09-30、未公開・未導入）

設定の「OBS全体のフォント」にPC内フォントの検索付き一覧・文字見本を追加。WindowsのEnumFontFamiliesExWで名前と日本語文字セット対応を読み取り、ファイルパスやフォント本体は公開しない。管理者認証が必要なGET /api/fonts/systemでのみ一覧を返す。独立版には新しいUIと一覧APIを提供しない。

選択はfonts.obs_allへ永続保存し、優先順はOBS個別指定→OBS一括→既存の全体一括。OBS一括の選び直しでOBSの個別指定だけを解除し、管理画面の指定は保持する。既存の個別指定・ファイル追加は折り畳みの詳細設定へ移動。system:接頭辞のUTF-8 hex識別子を検証し、CSSでは全コードポイントをエスケープする。PCフォント本体のコピーやOSフォントの変更はしない。別PCにフォントがない場合は標準フォントへフォールバックする。ファイル追加方式は従来どおり。

Python 392件・JavaScript 47件成功（直前に追加した待機60人・メンバーフラグの回帰テストを含む）。隔離したブラウザーで327書体の列挙、日本語検索、游明朝の見本描画、保存・再読込復元を確認。実際のOBS描画は未検証。配布実行ファイルでもフォント一覧・設定保存・再起動復元と既存の起動終了・コメント・テンプレート取得試験が成功。ユーザーの実データ・導入済みプラグイン・公開リリース・Botサーバーは変更していない。

候補ZIP: dist/onecomme-release-0.1.4-font-picker/Taikiretsu-Seiri-App-OneComme-0.1.4-windows-x64.zip。SHA256: 8595285a311737ed0e04eb43d94dba7c4c3996e991564f08f819e098f4580637。202ファイルのアーカイブ検証成功。

## OBSの太字・影切り替え（2026-09-30、未公開・未導入）

「OBSの文字・背景・サイズ」に「太字で強調する」「文字に影を付ける」を追加。別々にON/OFFでき、保存前に文字見本とOBSプレビューで確認できる。text_bold / text_shadow は初期true、OFF時はfont-weight:400 / text-shadow:none。管理画面の文字装飾・フォント指定・背景色・透過度は変更しない。SQLite保存、再起動、バックアップ復元、旧バックアップの初期値補完、設定リセットに対応。独立版には新しいチェックボックスを表示しない。

Python 401件・JavaScript 49件成功。隔離ブラウザーで縦横、太字のみON、影のみON、両方OFF、保存・再読込を確認。実行ファイルでも両方OFFの保存・再起動復元および既存機能のスモーク試験が成功。実際のOBS描画は未検証。ユーザーの実データ、導入済みプラグイン、GitHub公開版、Bot設定は変更していない。

フォント選択の更新も含む候補ZIP: dist/onecomme-release-0.1.4-text-effects/Taikiretsu-Seiri-App-OneComme-0.1.4-windows-x64.zip。SHA256: 6febcd3aa62bf278e648d3f156c43a4fb15cc7337f07208a8c35c0a8ea792f92。202ファイルのアーカイブ検証成功。

## 導入・設定の再設計（2026-10-01、ローカル実装・未導入・未公開）

### 調査結果と変更分類

| 対象 | 既存構造・保存先 | 今回の扱い |
| --- | --- | --- |
| 管理画面 /control | JSからFastAPIを2秒間隔で取得。SQLiteの待機列を描画 | UI変更。接続操作を設定へ移動、一覧20/128人 |
| 設定 /settings、/bot | 既存は一般・Botタブ。Bot URLは既に転送 | 3タブへ整理、フォームとAPIは再利用 |
| OBS導入 /obs-setup | ドラッグ追加、ZIP取得、管理URLコピー | OBS設定へ統合、旧URLは307転送 |
| 表示 /overlay、/onecomme-overlay | 同じ表示サービス・読取専用データ | 維持。管理用URLと分離 |
| 設定・参加者・履歴 | waiting_list.sqlite3のapp_state等、フォント・管理表示は専用テーブル | 維持。新しい端末用setup_preferencesテーブルのみ追加 |
| わんコメ接続 | plugin.js filterComment→ローカル認証付きAPI→OneCommeBridge | 取得処理は維持。選択配信の保存・復元と除外理由カウンターを追加 |
| 待機列/NOW/NEXT/優先・スキップ・Undo | ApplicationServices・QueueService。NOW3人、waiting先頭3人がNEXT | ロジック変更なし。全件の順序情報を保持 |
| Bot認証・識別 | サーバーOAuth。Bot channels.list(mine=true)の固定ID照合。配信者はreadonly OAuth | 維持。個人Bot方式に変更しない |
| Bot投稿 | ローカルbot.sqlite3の通知設定とDPAPI端末キー→共通サーバー→YouTube | 固定文テストと検証済みBotプロフィール取得を追加 |
| 初回案内 | 独立版desktop_configの案内はOneComme起動では利用されない | 専用ウィザードを追加 |
| メンバー限定 | メンバーフラグ・公開区分を理由に除外する条件は見つからない | 診断追加。実障害原因・実配信対応は未確定 |

廃止した待機列機能はない。専用画面の役割だけを集約した。実装順は画面統合→セットアップ→Bot拡張→表示制限→OBS案内・受信診断→回帰試験。

### 1. 変更したファイル / 2. 各ファイルの変更内容

- app/main.py: OneComme起動時の設定ストア・ルーター接続。
- app/routes/pages.py: 既存HTMLフォームを保持したタブ構成・初回案内・旧URL転送。
- app/routes/setup_api.py（新規）: 管理者のみの初回設定GET/POST。
- app/services/setup_preferences.py（新規）: 厳密な型検証とSQLite保存。
- app/services/onecomme.py: 選択配信の再起動復元、受信の除外理由と件数。
- app/routes/bot_api.py、app/services/bot.py: 任意テスト操作、サーバー対応確認、連投防止、失敗時停止、プロフィール検証。
- static/settings-tabs.html、settings-tabs.js: 基本/OBS/Botの3タブ、キーボード操作維持。
- static/setup-general.html、setup-wizard.html、setup-wizard.js、setup-launch.js、setup.css（新規）: 初回導線・途中保存・確認・再実行・長文の詳細表示。
- static/obs-settings.html（新規）、onecomme-obs-setup.js: OBS導入画面の統合、表示URLコピー・アクセス確認。
- static/overlay-settings.js: 既存保存処理をウィザードでも再利用。
- static/bot.html、bot.js: 未接続時の簡略表示、共通Bot名・アイコン、再接続案内、二段階の投稿確認、通知保存の再利用。
- static/onecomme-panel.html、onecomme.js: 設定側の接続操作、管理側は状態のみ、除外理由と対処案内。
- static/control.js: 20人/128人の描画制御。並べ替え要求では非表示の末尾も保持。
- shared-bot-backend/src/contracts/bot-api.ts、backend/policy.ts: connection-test固定テンプレートと自由文拒否。
- shared-bot-backend/backend/service.ts、backend/youtube.ts、backend/cloudflare/channel-connect.ts: 検証済みBotプロフィールと対応機能を接続応答へ追加。
- tests/test_setup_redesign.py、tests/setup_wizard.test.cjs（新規）: 保存・再起動・初回フロー・20/21/128/129/150人の回帰。
- tests/test_onecomme.py、test_bot.py、control_ui.test.cjs、settings_tabs.test.cjs、shared-bot-backend/tests/backend.test.ts、youtube.test.ts: 既存動作・新UI・固定投稿・旧サーバー互換・取得プロフィールの検証。
- scripts/smoke_onecomme.cjs: 配布実行ファイルでも新ページ・初回設定・選択配信の復元を確認。
- AGENTS.md、本書: 仕様と検証範囲の記録。

### 3. 新しく追加した機能

5段階セットアップ（接続、文言、任意Bot、任意OBS、確認）、途中保存・後回し・再実行、20人以降の折り畳み、128人超の残人数、受信診断、任意のBot投稿テスト、Bot表示名・画像の自動取得。

### 4. 変更した既存機能

配信選択を基本設定へ移動し再起動時に復元。設定のタブ切替でも未保存入力を保持。Bot通知3種類の処理、キーワード判定、履歴、優先順位、NOW/NEXT保護、ドラッグ順序変更、取消・Undoは維持。自然言語全般を解析する機能は元々なく、問い合わせ応答は従来どおり@JoinQueueBotへの呼びかけを受けて本人の位置を返す。

### 5. 削除・統合した画面

OneComme版/obs-setupを/settings?tab=obsへ統合。/botは従来どおり/settings?tab=botへ転送。独立版のページは保持。OBS表示専用ページは削除しない。

### 6. 設定データへの影響

待機列・参加者・履歴・表示設定の形式を変えず、初回案内と選択配信を同じDB内の別テーブルへ保存。キューのUndo/リセット/JSONバックアップには端末の初回状態を含めない。既存利用者も新しい初回案内は一度表示されるが、保存済みの文言・OBS・Bot設定を読み込み再入力は不要。「あとで」で通常運用へ戻れる。Bot認証・Googleトークンの移行はしない。

### 7. OAuth関連の変更

ユーザー確認により共通@JoinQueueBotを維持。Bot自身のOAuth、配信者のreadonly OAuth、コールバック、スコープは変更なし。サーバーの既存Bot本人照合でchannels.listのsnippetも取得し名称・許可ドメインの画像を返す。Bot登録のためのコメントは不要。テスト投稿は任意で、固定文のみ・既存認証/チャンネル照合/レート制限を通す。旧サーバーはfeatures.connectionTestを返さないためボタンを無効にし、通常通知は保持。**今回のサーバーソースは未配置。Google公開・審査・テストユーザー設定も変更していない。**

### 8. OBS関連の変更

表示用の公開URLと管理ドック用の秘密付きURLを区別してコピーできる。既存のドラッグ追加とZIPを移動・再利用。管理画面は同一オリジンHTTPポーリングなので専用WebSocketは不要、わんコメ受信経路も変わらない。管理キーはURLフラグメントからsessionStorageへ取り込みURL表示から除く既存方式。OBSと通常ブラウザーは別セッションであり、OBSに保存する管理URLは秘密として扱う。ドックを開くだけでは停止中のworkerは起動できず、先にわんコメのプラグインを有効にする必要がある。

[OBS公式実装](https://github.com/obsproject/obs-browser)でBrowser Docksを確認。構造上はローカル管理ページを載せられるが、実OBSのドック内ドラッグ・ファイル操作・セッション復元は未確認。Google認証は[OAuthポリシー](https://developers.google.com/identity/protocols/oauth2/policies)に従い通常の外部ブラウザーで実施する。埋込ブラウザーの制限を回避しない。「接続確認」は表示ページへの最近のアクセスを示すだけで実OBS描画の保証ではない。

### 9. メンバー限定配信対応状況

「わんコメには表示されるが待機列に入らない」という実障害の根因は、現在の実イベントを取得できておらず未確定。コードに公開配信だけを許可する条件はなく、メンバーフラグ付き通常コメントは試験で受理される。再起動で選択配信が失われる一般的な不具合を修正したが、それをメンバー限定の原因と断定しない。

切り分けは基本設定の接続/対象配信/受信件数/除外理由を見る。unselectedなら対象配信を選択、history/invalid_timestampなら取得時刻・履歴イベントを確認、ignoredならキーワード、droppedなら必須フィールドや転送件数を確認する。プラグインは公式フィールドの文字列id/liveId/userId/name/timestampを前提とする。実データで異なる形式なら、その匿名化した1イベントに基づき修正する。

Bot投稿は別経路。共通Botの権限でvideoIdの所有者・activeLiveChatIdを検証するため、配信者のわんコメが読めてもBotが参照できるとは限らない。[YouTube API](https://developers.google.com/youtube/v3/live/docs/liveChatMessages/insert)は権限不足・チャット無効/終了等を区別して失敗する。メンバー資格が必須か、モデレーター登録だけで十分かは当該配信で未確認。権限不足を回避してアクセスする実装はしない。[公開→メンバー限定へ切替える配信は別動画](https://support.google.com/youtube/answer/16399635?hl=en)となるため、新しい配信をわんコメで取得後に選び直す必要がある。旧配信の選択を復元するだけで自動追従するわけではない。

### 10. 既知の問題・検証範囲

- Python全体411件、JavaScript58件、共通バックエンド41件と型チェック成功。Google/YouTube応答はモック、Cloudflareは隔離ランタイムで検証。
- 隔離ブラウザーで初回未接続ガイド、キーワード保存、Botなし選択、OBS設定保存、確認・完了、再読込で案内が繰り返されないことを確認。3タブ・既存フォーム表示も確認。
- 150人待機のブラウザー実描画で20→128→20人、残り22人の表示を確認。OBS設定の折り畳みを開き直しても480×600px・scale(1)のプレビューを維持。配布実行ファイルの隔離スモーク試験で起動/終了/再起動、初回設定・選択配信の保存、コメント受信、NEXT保護、OBSデータ、テンプレートZIP取得が成功。
- 公開配信/メンバー限定配信の実受信、実Googleでの登録/変更/解除、Bot実投稿、OBS実機の描画/ドックは今回未確認。元データ・導入済み本体・公開Release・本番Cloudflareを変更していない。
- 投稿テスト・動的Bot画像はバックエンド新版配置が必要。Googleの公開範囲制限はアプリ更新だけで解消しない。既存依存ライブラリの非推奨警告2件あり、試験失敗ではない。

### 11. 今後改善できる点

実メンバー限定配信で除外理由を確認し、必要なら匿名化イベント1件で再現試験を追加する。OBSドック実機試験と外部ブラウザー認証導線を確認し、その後バックエンドの段階配置・任意テスト投稿を行う。Googleの一般公開準備は最後に実施する。別PC移行時の端末設定の扱い、128人超の検索による直接操作、旧HTMLの文字列結合のテンプレート化は別の小さな改修候補。

最終ローカル候補: `dist/onecomme-release-0.1.4-redesign-final/Taikiretsu-Seiri-App-OneComme-0.1.4-windows-x64.zip`。208ファイル、22,842,294 bytes、SHA256 `39746adefd113b80372625e89ef5cadad4cd7da329e7ae167aaa3fa773ba5653`。旧候補の再ビルドでWindowsのファイル置換が拒否されたため、新しい出力フォルダへ構築。公開・導入対象にする場合はこのfinal候補を使用する。ブラウザー検証用サーバーは停止済み。
