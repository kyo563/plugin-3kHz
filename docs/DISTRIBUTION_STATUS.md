# 1.0.0の動作環境と対応範囲

参加型整列プラグイン 1.0.0は、現在の機能範囲を完成版とするユーザーの指定に基づく正式版です。

- Windows 11 x64向けのZIP配布。Microsoft Edge WebView2 Runtimeを使用します。
- Chrome・Python・OBS追加プラグインは利用者には不要です。
- 手動管理とOBS表示に対応。外部コメント入力APIはありますが、YouTubeコメント自動取得や特定製品アダプターは同梱していません。
- コード署名とWindowsインストーラーは含まれていません。
- 自動テスト・実HTTP確認・Windows exe起動終了は実施しています。
- OBS/Edge長時間併用・クリーンPC・全表示倍率・特定チャット製品接続の受入試験は未実施です。

## 保存と削除

既存データ互換のため内部の保存名WaitingListAppを維持しています。完全データ削除は所有台帳に基づき本アプリ所有のデータのみを対象とし、OBS/Edgeの設定や共有ランタイムを変更しません。手順はREADME.txtを参照してください。

## 配布物

README.md・README.txt、実行ファイル、_internal、BUILD_INFO.json、依存物のライセンス・通知を収録しています。認証キーや利用者のDBは含みません。
THIRD_PARTY_NOTICES.jsonとTHIRD_PARTY_LICENSESはビルド環境の配布物から収集した情報で、ビルド用パッケージの通知も含みます。本プロジェクト自身の再配布・改変ライセンスは未選定です。

## 再ビルド

Python 3.12 x64でsetup-desktop.ps1、build-windows.ps1を実行し、scripts/package_release.py --version 1.0.0でZIP・README・SHA256SUMSを生成できます。ビルド処理自体はGitHubへの公開を行いません。
インストーラー定義は開発資料として残していますが、ビルド・受入試験は未完了です。
