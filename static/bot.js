(() => {
  const el = id => document.getElementById(id);
  let current, busy = false, autoAuthUntil = 0, nextAuthProbe = 0, stopEpoch = 0;
  async function call(path, value) {
    const response = await fetch('/api/bot' + path, {signal:AbortSignal.timeout(60000), ...(value === undefined ? {} : {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(value)})});
    const data = await response.json();
    if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : '設定内容を確認してください');
    return data;
  }
  function status(s) {
    current = s;
    el('bot-start').disabled = s.ready;
    el('bot-connect').hidden = s.authenticated;
    el('bot-connect').disabled = s.auth_state === 'preparing';
    el('bot-connect').textContent = s.has_connection_key ? '認証を再開・やり直す' : '配信チャンネルを接続';
    el('bot-status-check').hidden = !s.has_connection_key;
    el('bot-reauth-open').hidden = !s.has_connection_key;
    el('bot-reauth-open').disabled = s.auth_state === 'preparing';
    if (s.auth_state === 'pending' && !s.authenticated) {
      // Only while the authentication page is visible, for at most ten minutes.
      if (!autoAuthUntil) autoAuthUntil = Date.now() + 600000;
    } else autoAuthUntil = 0;
    for (const id of ['bot-check','bot-start','bot-stop','bot-test']) el(id).hidden = !s.authenticated;
    el('bot-notification-fields').disabled = !s.authenticated;
    el('bot-notifications-hint').hidden = s.authenticated;
    el('bot-stop').disabled = !s.ready;
    el('bot-test').disabled = !s.test_available;
    el('bot-erase-open').disabled = !s.authenticated || !s.deletion_available;
    el('bot-name').textContent = '共通Bot：' + (s.account?.name || 'JoinQueueBot');
    const icon = el('bot-icon'), url = s.account?.icon;
    icon.hidden = true;
    if (typeof url === 'string' && /^https:\/\/([\w-]+\.)?(ggpht\.com|googleusercontent\.com)\//.test(url)) {
      if (icon.src !== url) icon.src = url;
      icon.hidden = false; icon.onerror = () => { icon.hidden = true; };
    }
    const authLabels = {preparing:'チャンネル認証を準備中', expired:'認証が失効しています。認証をやり直してください。',
      pending:'チャンネル認証待ち。「認証を再開・やり直す」でリンクを発行してください。',
      unverified:'保存済み接続の認証状態を確認してください。'};
    el('bot-status').textContent = s.error || (s.ready ? 'Bot稼働中' : s.authenticated ? 'チャンネル接続済み／停止中' : s.login_pending ? 'チャンネル認証待ち' : authLabels[s.auth_state] || 'Bot停止中／未接続');
    el('bot-running-status').textContent = el('bot-status').textContent;
    el('bot-status').title = s.channel_id ? '配信チャンネル ' + s.channel_id : '';
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
  async function checkAuthentication() {
    nextAuthProbe = Date.now() + 10000;
    try {
      const updated = await call('/connection', {action:'status'});
      status(updated);
      if (updated.authenticated) el('bot-auth-result').textContent = 'チャンネル認証が完了しました。通知を選んで「Botを起動」を押してください。';
    } catch (error) {
      nextAuthProbe = Date.now() + 60000;
      el('bot-auth-result').textContent = error.message;
    }
  }
  call('').then(async s => {
    el('bot-now').checked = s.settings.announce_now; el('bot-reply').checked = s.settings.reply_position;
    el('bot-periodic').checked = s.settings.periodic; el('bot-interval').value = String(s.settings.interval_minutes);
    el('bot-initial-delay').value = String(s.settings.initial_delay_minutes ?? 30);
    interval(); status(s);
    if (s.has_connection_key && !s.authenticated && s.auth_state && !busy) {
      busy = true;
      try { await checkAuthentication(); }
      finally { busy = false; }
    }
  }).catch(e => { el('bot-status').textContent = e.message; });
  const settingsPayload = () => ({enabled: current.ready, announce_now: el('bot-now').checked,
    reply_position: el('bot-reply').checked, periodic: el('bot-periodic').checked,
    interval_minutes: Number(el('bot-interval').value), initial_delay_minutes: Number(el('bot-initial-delay').value)});
  async function persistSettings(skipUnchanged = false) {
    const payload = settingsPayload();
    const saved = {...current.settings, enabled:!!current.settings.enabled,
      initial_delay_minutes:current.settings.initial_delay_minutes ?? 30};
    if (!skipUnchanged || Object.entries(payload).some(([key, value]) => saved[key] !== value))
      status(await call('/settings', payload));
    el('bot-save-result').textContent = '保存しました。';
  }
  window.saveBotSettings = async () => {
    if (busy || !current) return false; busy = true;
    try {
      await persistSettings();
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
      if (action === 'stop') stopEpoch += 1;
      const epoch = stopEpoch;
      if (action === 'start' && (!current?.authenticated || current.ready)) {
        if (!current?.authenticated) el('bot-start-result').textContent = 'Botは起動していません。チャンネル認証を完了してください。';
        return;
      }
      busy = true;
      const result = el(['connect','status'].includes(action) ? 'bot-auth-result' : ['start','stop'].includes(action) ? 'bot-start-result' : 'bot-login-result');
      result.textContent = '確認中…';
      try {
        if (action === 'start') {
          await persistSettings(true);
          if (epoch !== stopEpoch) throw new Error('停止操作のため起動を取り消しました。');
        }
        const updated = await call('/connection', {action});
        if (action === 'start' && epoch !== stopEpoch) throw new Error('停止操作のため起動を取り消しました。');
        status(updated);
        if (['connect','status'].includes(action)) nextAuthProbe = Date.now() + 10000;
        result.textContent = action === 'connect' ? (updated.authenticated ? 'チャンネル認証が完了しています。接続を維持しました。' : updated.login_pending ? '認証の準備ができました。認証リンクを開いてください。' : '認証結果を確認してください。')
          : action === 'status' ? (updated.authenticated ? 'チャンネル認証が完了しました。通知を選んで「Botを起動」を押してください。' : updated.auth_state === 'pending' ? '認証待ちです。ブラウザーで認証を完了してください。結果は自動で確認します。' : '認証は未完了です。「認証を再開・やり直す」でリンクを発行してください。')
          : action === 'check' ? (updated.authenticated ? '対象配信の接続確認が完了しました。チャットには投稿していません。' : 'チャンネル認証を完了してください。')
          : action === 'start' ? (updated.ready ? 'Botを起動しました。選択した通知を送信します。' : 'Botは起動していません。チャンネル認証と接続状態を確認してください。') : 'Botを停止しました。';
      }
      catch (error) { result.textContent = error.message; }
      finally { busy = false; }
    });
  }
  el('bot-reauth-open').onclick = () => {
    if (busy || !current?.has_connection_key) return;
    el('bot-reauth-confirm').disabled = false;
    el('bot-reauth-dialog').showModal();
  };
  el('bot-reauth-cancel').onclick = () => el('bot-reauth-dialog').close();
  el('bot-reauth-confirm').onclick = async () => {
    if (busy || !el('bot-reauth-dialog').open) return;
    busy = true; el('bot-reauth-confirm').disabled = true;
    const result = el('bot-auth-result');
    result.textContent = '接続を解除して認証を準備中…';
    try {
      const disconnected = await call('/disconnect', {confirmation:'接続を解除'});
      status(disconnected);
      if (disconnected.has_connection_key || disconnected.authenticated) throw new Error('接続解除を確認できません。認証結果を確認してください。');
      const updated = await call('/connection', {action:'connect'});
      status(updated); nextAuthProbe = Date.now() + 10000;
      result.textContent = updated.login_pending ? '新しい認証リンクを開いて、配信チャンネルを認証してください。' : '認証結果を確認してください。';
    } catch (error) {
      result.textContent = error.message + ' 接続状態を確認し、通信復旧後に再試行してください。';
    } finally {
      busy = false; el('bot-reauth-confirm').disabled = false; el('bot-reauth-dialog').close();
    }
  };
  el('bot-disconnect-confirm').addEventListener('change', () => { el('bot-disconnect').disabled = !el('bot-disconnect-confirm').checked; });
  el('bot-erase-open').onclick = () => {
    if (busy || !current?.authenticated || !current?.deletion_available) return;
    el('bot-erase-text').value = ''; el('bot-erase-confirm').disabled = true;
    el('bot-erase-dialog').showModal();
  };
  el('bot-erase-text').addEventListener('input', () => { el('bot-erase-confirm').disabled = busy || el('bot-erase-text').value !== 'サーバー記録を削除'; });
  el('bot-erase-cancel').onclick = () => el('bot-erase-dialog').close();
  el('bot-erase-confirm').onclick = async () => {
    if (busy || el('bot-erase-text').value !== 'サーバー記録を削除') return;
    busy = true; el('bot-erase-confirm').disabled = true;
    try { status(await call('/erase', {confirmation:'サーバー記録を削除'})); el('bot-start-result').textContent = current.last_result; }
    catch(e) { el('bot-start-result').textContent = e.message + ' 接続キーは保持しています。削除結果が不明な場合は運営へ確認してください。'; }
    finally { busy = false; el('bot-erase-dialog').close(); }
  };
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
    try {
      status(await call(''));
      if (!current.authenticated && current.has_connection_key && current.auth_state === 'pending'
          && Date.now() < autoAuthUntil && Date.now() >= nextAuthProbe) await checkAuthentication();
    } catch (_) { el('bot-status').textContent = 'アプリへの接続が切れています'; }
    finally { busy = false; }
  }, 3000);
})();
