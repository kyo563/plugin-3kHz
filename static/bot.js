(() => {
  const el = id => document.getElementById(id);
  let current, busy = false;
  async function call(path, value) {
    const response = await fetch('/api/bot' + path, value === undefined ? {} : {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(value)});
    const data = await response.json();
    if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : '設定内容を確認してください');
    return data;
  }
  function status(s) {
    current = s;
    el('bot-start').disabled = s.ready;
    el('bot-status').textContent = s.error || (s.ready ? 'Bot稼働中' : s.authenticated ? 'チャンネル接続済み／停止中' : s.login_pending ? 'チャンネル認証待ち' : 'Bot停止中／未接続');
    if (s.channel_id) el('bot-status').textContent += ' · 配信チャンネル ' + s.channel_id;
    el('bot-last').textContent = s.last_result || '';
    el('bot-next').textContent = !s.settings.periodic ? '定期案内：オフ' : s.next_announcement_seconds === null ? '定期案内：停止中' : '次の定期案内まで約' + Math.ceil(s.next_announcement_seconds / 60) + '分';
    const link = el('bot-login-link');
    link.hidden = true; link.removeAttribute('href');
    if (s.authorization_url) {
      const url = new URL(s.authorization_url);
      if (url.origin === 'https://joinqueue-bot-backend.joinqueue.workers.dev' && url.pathname === '/connect' && !url.username && !url.password && !url.hash) {
        link.href = url.href; link.hidden = false;
      }
    }
    el('bot-confirmation').textContent = s.confirmation ? '照合番号：' + s.confirmation : '';
  }
  const interval = () => { el('bot-interval').disabled = !el('bot-periodic').checked; };
  el('bot-periodic').addEventListener('change', interval);
  call('').then(s => {
    el('bot-now').checked = s.settings.announce_now; el('bot-reply').checked = s.settings.reply_position;
    el('bot-periodic').checked = s.settings.periodic; el('bot-interval').value = String(s.settings.interval_minutes);
    interval(); status(s);
  }).catch(e => { el('bot-status').textContent = e.message; });
  el('bot-form').addEventListener('submit', async e => {
    e.preventDefault(); if (busy || !current) return; busy = true;
    try {
      status(await call('/settings', {enabled: current.ready, announce_now: el('bot-now').checked,
        reply_position: el('bot-reply').checked, periodic: el('bot-periodic').checked, interval_minutes: Number(el('bot-interval').value)}));
      el('bot-save-result').textContent = '保存しました。';
    } catch (error) { el('bot-save-result').textContent = error.message; }
    finally { busy = false; }
  });
  for (const [id, action] of Object.entries({'bot-connect':'connect', 'bot-status-check':'status', 'bot-check':'check', 'bot-start':'start', 'bot-stop':'stop'})) {
    el(id).addEventListener('click', async () => {
      if (busy && action !== 'stop') return;
      busy = true;
      try { status(await call('/connection', {action})); el('bot-login-result').textContent = '操作を反映しました。'; }
      catch (error) { el('bot-login-result').textContent = error.message; }
      finally { busy = false; }
    });
  }
  el('bot-disconnect-confirm').addEventListener('change', () => { el('bot-disconnect').disabled = !el('bot-disconnect-confirm').checked; });
  el('bot-disconnect').addEventListener('click', async () => {
    if (busy || !el('bot-disconnect-confirm').checked) return;
    busy = true;
    try { status(await call('/disconnect', {confirmation: '接続を解除'})); el('bot-disconnect-confirm').checked = false; el('bot-disconnect').disabled = true; }
    catch (error) { el('bot-login-result').textContent = error.message; }
    finally { busy = false; }
  });
  setInterval(async () => {
    if (busy || document.hidden) return;
    busy = true;
    try { status(await call('')); } catch (_) { el('bot-status').textContent = 'アプリへの接続が切れています'; }
    finally { busy = false; }
  }, 3000);
})();
