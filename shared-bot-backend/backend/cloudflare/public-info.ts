import { AUTH_ORIGIN } from './bot-auth';

/** Public documentation only; the verification tag is intentionally public, NOT an API credential. */
export function publicInfo(request: Request): Response | undefined {
  const url = new URL(request.url);
  if (url.origin !== AUTH_ORIGIN || url.pathname !== '/' || url.search || request.method !== 'GET') return;
  return new Response(`<!doctype html><html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
    <meta name="author" content="kyo563"><meta name="google-site-verification" content="J_XsuQSdaCNaTeq4zMP2S6SCpn0tTiYmX0sQfXyWqEk">
    <title>JoinQueue Bot 接続サーバー</title></head><body><h1>JoinQueue Bot 接続サーバー</h1><p>待機列整理アプリ（わんコメ連携版）の共通Botバックエンドです。作者・運営：kyo563。</p>
    <p><a href="https://kyo563.github.io/">アプリの紹介</a> ／ <a href="https://kyo563.github.io/privacy.html">プライバシーポリシー</a> ／ <a href="https://kyo563.github.io/terms.html">利用に関するご案内</a></p>
    <p>チャンネル接続はプラグインの設定画面から開始してください。このページでは認証情報や保存データを表示しません。</p></body></html>`,
    {headers:{'Content-Type':'text/html; charset=utf-8','Cache-Control':'public, max-age=300','X-Content-Type-Options':'nosniff',
      'Referrer-Policy':'no-referrer', 'Content-Security-Policy':"default-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"}});
}
