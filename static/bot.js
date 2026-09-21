(() => {
  const el = id => document.getElementById(id);
  async function call(path, value) {
    const r = await fetch('/api/bot' + path, value === undefined ? {} : {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(value)});
    const data = await r.json();
    if (!r.ok) throw new Error(typeof data.detail === 'string' ? data.detail : '設定内容を確認してください');
    return data;
  }
  function status(s) {
    const name = s.account.name ? `${s.account.name} ${s.account.handle || ''}` : '未接続';
    el('bot-status').textContent = `${name}：${s.error || (s.ready ? '投稿準備OK' : s.authenticated ? (s.settings.enabled ? '配信の選択・接続を待っています' : 'ログイン済み／Bot無効') : s.login_pending ? 'Googleログイン待ち' : 'Googleログインが必要です')}`;
    el('bot-last').textContent = s.last_result || '';
    if (s.authenticated && !s.account.handle) el('bot-status').textContent += '。@ハンドルが確認できないため順位返信は利用できません。';
  }
  call('').then(s => {
    const c = s.settings;
    el('bot-enabled').checked = c.enabled;
    el('bot-now').checked = c.announce_now;
    el('bot-reply').checked = c.reply_position;
    el('bot-periodic').checked = c.periodic;
    el('bot-interval').value = String(c.interval_minutes);
    el('bot-guide').value = c.guide;
    status(s);
  }).catch(e => el('bot-status').textContent = e.message);
  el('bot-form').addEventListener('submit', async e => {
    e.preventDefault();
    try {
      status(await call('/settings', {enabled: el('bot-enabled').checked, announce_now: el('bot-now').checked,
        reply_position: el('bot-reply').checked, periodic: el('bot-periodic').checked,
        interval_minutes: Number(el('bot-interval').value), guide: el('bot-guide').value}));
      el('bot-save-result').textContent = '保存しました。';
    } catch (error) { el('bot-save-result').textContent = error.message; }
  });
  el('bot-login').addEventListener('click', async () => {
    el('bot-login').disabled = true;
    try {
      const file = el('bot-client').files[0];
      if (!file || file.size > 16384) throw new Error('OAuthクライアントJSONを選んでください（16KBまで）');
      const result = await call('/login', JSON.parse(await file.text()));
      const url = new URL(result.url);
      if (url.origin !== 'https://accounts.google.com') throw new Error('ログインURLが不正です');
      el('bot-login-link').href = url.href; el('bot-login-link').hidden = false;
      el('bot-client').value = '';
      el('bot-login-result').textContent = '上のリンクからBot専用アカウントでログインしてください。';
    } catch (error) { el('bot-login-result').textContent = error.message; }
    finally { el('bot-login').disabled = false; }
  });
  el('bot-disconnect').addEventListener('click', async () => {
    try { status(await call('/disconnect', {})); el('bot-login-link').hidden = true; }
    catch (error) { el('bot-login-result').textContent = error.message; }
  });
  let busy = false;
  setInterval(async () => {
    if (busy || document.hidden) return;
    busy = true;
    try { status(await call('')); } catch (_) { el('bot-status').textContent = 'アプリへの接続が切れています'; }
    finally { busy = false; }
  }, 3000);
})();
