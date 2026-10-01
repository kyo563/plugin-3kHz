(() => {
  const el = id => document.getElementById(id);
  let current, busy = false;
  async function call(path, value) {
    const response = await fetch('/api/bot' + path, {signal:AbortSignal.timeout(60000), ...(value === undefined ? {} : {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(value)})});
    const data = await response.json();
    if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : '設定内容を確認してください');
    return data;
  }
  function status(s) {
    current = s;
    el('bot-start').disabled = s.ready;
    el('bot-connect').hidden = s.has_connection_key;
    el('bot-status-check').hidden = !s.has_connection_key;
    for (const id of ['bot-check','bot-start','bot-stop','bot-test']) el(id).hidden = !s.authenticated;
    el('bot-notification-fields').disabled = !s.authenticated;
    el('bot-notifications-hint').hidden = s.authenticated;
    el('bot-stop').disabled = !s.ready;
    el('bot-test').disabled = !s.test_available;
    el('bot-name').textContent = '共通Bot：' + (s.account?.name || 'JoinQueueBot');
    const icon = el('bot-icon'), url = s.account?.icon;
    icon.hidden = true;
    if (typeof url === 'string' && /^https:\/\/([\w-]+\.)?(ggpht\.com|googleusercontent\.com)\//.test(url)) {
      if (icon.src !== url) icon.src = url;
      icon.hidden = false; icon.onerror = () => { icon.hidden = true; };
    }
    el('bot-status').textContent = s.error || (s.ready ? 'Bot稼働中' : s.authenticated ? 'チャンネル接続済み／停止中' : s.login_pending ? 'チャンネル認証待ち' : 'Bot停止中／未接続');
    el('bot-running-status').textContent = el('bot-status').textContent;
    if (s.channel_id) el('bot-status').title = '配信チャンネル ' + s.channel_id;
    el('bot-last').textContent = s.last_result || '';
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
  const interval = () => {
    for (const id of ['bot-interval', 'bot-initial-delay']) el(id).disabled = !el('bot-periodic').checked;
  };
  el('bot-periodic').addEventListener('change', interval);
  call('').then(s => {
    el('bot-now').checked = s.settings.announce_now; el('bot-reply').checked = s.settings.reply_position;
    el('bot-periodic').checked = s.settings.periodic; el('bot-interval').value = String(s.settings.interval_minutes);
    el('bot-initial-delay').value = String(s.settings.initial_delay_minutes ?? 30);
    interval(); status(s);
  }).catch(e => { el('bot-status').textContent = e.message; });
  window.saveBotSettings = async () => {
    if (busy || !current) return false; busy = true;
    try {
      status(await call('/settings', {enabled: current.ready, announce_now: el('bot-now').checked,
        reply_position: el('bot-reply').checked, periodic: el('bot-periodic').checked, interval_minutes: Number(el('bot-interval').value),
        initial_delay_minutes: Number(el('bot-initial-delay').value)}));
      el('bot-save-result').textContent = '保存しました。';
      return true;
    } catch (error) { el('bot-save-result').textContent = error.message; return false; }
    finally { busy = false; }
  };
  el('bot-form').addEventListener('submit', async e => {
    e.preventDefault(); await window.saveBotSettings();
  });
  for (const [id, action] of Object.entries({'bot-connect':'connect', 'bot-status-check':'status', 'bot-check':'check', 'bot-start':'start', 'bot-stop':'stop'})) {
    el(id).addEventListener('click', async () => {
      if (busy && action !== 'stop') return;
      busy = true;
      const result = el(['connect','status'].includes(action) ? 'bot-auth-result' : ['start','stop'].includes(action) ? 'bot-start-result' : 'bot-login-result');
      result.textContent = '確認中…';
      try {
        const updated = await call('/connection', {action});
        status(updated);
        result.textContent = action === 'connect' ? '認証の準備ができました。認証リンクを開いてください。'
          : action === 'status' ? (updated.authenticated ? 'チャンネル認証が完了しました。対象配信の接続確認へ進んでください。' : '認証待ちです。ブラウザーでの認証を完了してから、もう一度確認してください。')
          : action === 'check' ? '対象配信の接続確認が完了しました。チャットには投稿していません。'
          : action === 'start' ? 'Botを起動しました。選択した通知を送信します。' : 'Botを停止しました。';
      }
      catch (error) { result.textContent = error.message; }
      finally { busy = false; }
    });
  }
  el('bot-disconnect-confirm').addEventListener('change', () => { el('bot-disconnect').disabled = !el('bot-disconnect-confirm').checked; });
  el('bot-test').onclick = () => { if (!busy) el('bot-test-dialog').showModal(); };
  el('bot-test-cancel').onclick = () => el('bot-test-dialog').close();
  el('bot-test-confirm').onclick = async () => {
    if (busy) return;
    busy = true; el('bot-test-confirm').disabled = true;
    try { status(await call('/connection', {action:'test'})); el('bot-start-result').textContent = 'テストコメントを投稿しました。'; }
    catch(e) { el('bot-start-result').textContent = e.message + ' 投稿結果が不明な場合はチャットを確認し、連打しないでください。'; }
    finally { busy = false; el('bot-test-confirm').disabled = false; el('bot-test-dialog').close(); }
  };
  el('bot-disconnect').addEventListener('click', async () => {
    if (busy || !el('bot-disconnect-confirm').checked) return;
    busy = true;
    try { status(await call('/disconnect', {confirmation: '接続を解除'})); el('bot-disconnect-confirm').checked = false; el('bot-disconnect').disabled = true; }
    catch (error) { el('bot-start-result').textContent = error.message; }
    finally { busy = false; }
  });
  setInterval(async () => {
    if (busy || document.hidden) return;
    busy = true;
    try { status(await call('')); } catch (_) { el('bot-status').textContent = 'アプリへの接続が切れています'; }
    finally { busy = false; }
  }, 3000);
})();
