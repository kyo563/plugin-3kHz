# 配布前の確認事項

0.1.0-preview.21はユーザーの公開指示に基づきGitHub Releasesで配布するWindows用ZIP検証版です。安定版ではありません。署名・インストーラー受入試験・外部チャット製品との接続は未完了です。

## 再現手順

1. Python 3.12 x64で `setup-desktop.ps1`。
2. `.venv/Scripts/python.exe -m pytest -q` と `scripts/smoke_http.py`。
3. `build-windows.ps1` でonedir exe作成。
4. `.venv/Scripts/python.exe scripts/package_release.py` で日本語ガイド・ライセンス一覧・ZIP・SHA256SUMS生成。
5. Inno Setup 6以降を用意し `build-installer.ps1 -Compiler <ISCC.exe>`。このPCではコンパイラー導入が自動承認レビューに拒否され、ビルド未検証。
6. 署名証明書が用意できたら、exe・同梱する自作バイナリ・インストーラーに `scripts/sign-artifact.ps1` を使う。秘密鍵/パスワードをソースへ含めない。署名後に再パッケージしチェックサムを更新する。
7. クリーンWindows、OBS/Edge同時起動、アンインストールを確認後、ユーザーの公開指示があってからGitHub Releasesへインストーラー・ZIP・SHA256SUMSを添付。Source code ZIPは実行用ZIPではない。

## ライセンス

`THIRD_PARTY_NOTICES.json` と `THIRD_PARTY_LICENSES` は検証環境のPython配布物から取得したライセンス本文/メタデータです。ビルド用パッケージも一覧に含みます。Python本体のライセンスも収録します。
このリポジトリ自身の公開ライセンスは未選定です。依存物の自動収集だけで、同梱ネイティブDLLを含む配布条件の確認完了とはしません。公開前に権利者の条件と実際の同梱内容を照合してください。

## メモリ/CPUの測定

`scripts/measure-resources.ps1 -AppProcessId <このアプリのPID> -Seconds 30 -Output report.json`。
本アプリの子プロセスを含むworking set/private bytes、OBS、Edgeの同時サンプルを記録します。既存プロセスの起動/終了/設定変更はしません。working setの単純合計は共有ページを二重計上し得るためprivate bytesも比較してください。CPUは全論理プロセッサーを100%とした差分です。OBS/Edgeが未起動なら0プロセスと記録され、併用試験をしたことにはなりません。

## アンインストール受入試験

隔離したWindowsユーザー/VMで、初回インストール、上書き更新、データ保持、完全削除、再インストールを順に確認します。稼働中は認証済みの本アプリだけに終了を要求し、停止できなければ削除を中止します。
OBS設定、Edge通常プロファイル、共有ランタイムは前後で比較。保存先変更、日本語/空白パス、読み取り専用/使用中、ジャンクション、所有マーカー不一致、中断後の再実行、未知のユーザーファイル保全も確認してください。

参考: https://obsproject.com/kb/browser-source 、https://jrsoftware.org/ishelp/topic_uninstalldeletesection.htm 、https://learn.microsoft.com/en-us/microsoft-edge/webview2/concepts/user-data-folder
