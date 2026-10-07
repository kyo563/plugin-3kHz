(() => {
  const el = id => document.getElementById(id);
  const tabs = ['general','general','bot','obs','general'];
  const titles = ['対象配信を確認','参加キーワード・表示文言を設定','Botの設定を進めます。','OBS表示の利用を選択','設定内容を確認'];
  const instructions = ['このプラグインでは、わんコメがコメントを受信している配信に自動で接続します。\n下記の「接続先の配信」に、利用する配信が表示されていれば接続完了です。「次へ」で進んでください。\n未接続、または別の配信が表示されている場合は、「別の配信に連携し直す」から接続先を選び直してください。',
    '参加・辞退に使う文言と、OBSの表示文言を確認してください。「次へ」で保存します。',
    'Botを標準モデレーターに設定し、対象の配信を選択することで利用可能になります。',
    'OBS表示用の設定を編集します。',
    '設定内容を確認し、「次へ」でセットアップを完了してください。\nこの初回セットアップは設定から再度行うことができます。'];
  let prefs, busy = false;
  async function api(path, value) {
    const r = await fetch(path, {signal:AbortSignal.timeout(10000), ...(value === undefined ? {} : {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(value)})});
    if (!r.ok) throw new Error('保存・接続を確認できません。入力内容を確認して再試行してください。');
    return r.json();
  }
  const persist = async next => { prefs = await api('/api/setup', next); };
  function placeConnection(inBot) {
    // Move the existing controls, retaining their event handlers and selected stream.
    if (inBot) el('bot-stream-picker').append(el('setup-connection'));
    else el('settings-general-panel').prepend(el('setup-connection'));
    el('bot-stream-settings-link').hidden = inBot;
  }
  for (const [buttonId, statusId, saveId] of [
    ['setup-reset-commands','commands-result','save-commands'],
    ['setup-reset-labels','display-labels-result','save-display-labels'],
  ]) {
    el(buttonId).onclick = () => {
      if (busy || prefs?.step !== 1) return;
      if (el(saveId).disabled) {
        el(statusId).textContent = '設定を読み込み中です。読み込めない場合はページを開き直してください。';
        return;
      }
      // Reset only this section's draft. Persist with Next, never clear operational data.
      for (const [id, value] of Object.entries(JSON.parse(el(buttonId).dataset.defaults))) {
        el(id).value = value;
        el(id).dispatchEvent(new Event('input', {bubbles:true}));
      }
      el(statusId).textContent = '初期値に戻しました。「次へ」で保存します。';
    };
  }
  function optionalPanel() {
    if (prefs?.step === 2) el('settings-bot-panel').hidden = !el('setup-use-bot').checked;
    if (prefs?.step === 3) {
      el('settings-obs-panel').hidden = !el('setup-use-obs').checked;
      window.dispatchEvent(new Event('resize'));
    }
  }
  el('setup-use-bot').onchange = optionalPanel;
  el('setup-use-obs').onchange = optionalPanel;
  el('setup-obs-details').ontoggle = () => {
    if (el('setup-obs-details').open) window.dispatchEvent(new Event('resize'));
  };
  function show() {
    document.body.classList.add('setup-active');
    document.body.dataset.setupStep = String(prefs.step);
    el('setup-wizard').hidden = false;
    el('setup-progress').textContent = `${prefs.step + 1} / 5　${titles[prefs.step]}`;
    el('setup-instruction').textContent = instructions[prefs.step];
    el('setup-bot-choice').hidden = prefs.step !== 2;
    el('setup-obs-choice').hidden = prefs.step !== 3;
    el('setup-use-bot').checked = prefs.use_bot;
    el('setup-use-obs').checked = prefs.use_obs;
    el('setup-back').disabled = prefs.step === 0;
    el('setup-next').textContent = '次へ';
    el('setup-summary').hidden = prefs.step !== 4;
    window.selectSettingsTab(tabs[prefs.step]);
    placeConnection(prefs.step === 2);
    optionalPanel();
    el('setup-obs-details').open = true;
    el('setup-title').focus();
    if (prefs.step === 4) {
      el('setup-summary').textContent = '状態を確認中…';
      Promise.all([api('/api/onecomme/status'), api('/api/bot'), api('/api/obs-status')]).then(([stream,bot,obs]) => {
        el('setup-summary').textContent = `わんコメ：${stream.connected ? '接続済み' : '未接続'}\n配信：${stream.selected_name || stream.selected || (stream.ready_to_receive ? '接続枠と連動中・コメント待ち' : '未接続')}\nBot：${prefs.use_bot ? (bot.authenticated ? 'チャンネル接続済み' : '認証が必要') : '使用しない'}${bot.ready ? '・稼働中' : '・停止中'}\nOBS：${prefs.use_obs ? (obs.last_access_seconds !== null && obs.last_access_seconds < 10 ? '表示ページ接続あり' : '利用準備済み・表示未確認') : '使用しない'}`;
      }).catch(e => {el('setup-summary').textContent = e.message;});
    }
  }
  async function run(action) {
    if (busy || !prefs) return;
    busy = true;
    for (const id of ['setup-next','setup-back','setup-restart']) el(id).disabled = true;
    el('setup-result').textContent = '';
    try { await action(); }
    catch(e) { el('setup-result').textContent = e.message; }
    finally {
      busy = false;
      for (const id of ['setup-next','setup-restart']) el(id).disabled = false;
      el('setup-back').disabled = prefs.step === 0;
    }
  }
  el('setup-restart').onclick = () => run(async () => {await persist({...prefs, step:0}); show();});
  el('setup-back').onclick = () => run(async () => {await persist({...prefs,step:Math.max(0,prefs.step-1)}); show();});
  async function next() {
    let nextPrefs = {...prefs};
    if (prefs.step === 0) {
      const s = await api('/api/onecomme/status');
      if (!s.connected || s.pending || s.selection_reason === 'stopped') throw new Error('わんコメのプラグインを有効にしてください。連携停止中・配信切り替え確認待ちの場合は連携を再開してください。');
    }
    if (prefs.step === 1) {
      if (el('join-commands').disabled || el('cancel-commands').disabled) throw new Error('設定を読み込み中です。読み込めない場合はページを開き直してください。');
      const lines = id => el(id).value.split(/\r?\n/).map(s=>s.trim()).filter(Boolean);
      await api('/api/settings/commands', {join:lines('join-commands'),cancel:lines('cancel-commands')});
      el('commands-result').textContent = '保存しました。';
      if (!(await window.saveOverlaySettings())) throw new Error('表示文言を保存できません。読み込み状態・入力値を確認して再試行してください。');
    }
    if (prefs.step === 2) {
      nextPrefs.use_bot = el('setup-use-bot').checked;
      if (nextPrefs.use_bot && !(await api('/api/bot')).authenticated) throw new Error('チャンネルを接続し「認証結果を確認」を押してください。Botを使用しない場合はチェックを外して「次へ」を押してください。');
      if (nextPrefs.use_bot && !(await window.saveBotSettings())) throw new Error('Bot通知設定を保存できません。しばらく待ってから再試行してください。');
      if (!nextPrefs.use_bot) await api('/api/bot/connection', {action:'stop'});
    }
    if (prefs.step === 3) {
      nextPrefs.use_obs = el('setup-use-obs').checked;
      if (nextPrefs.use_obs && !(await window.saveOverlaySettings())) throw new Error('OBS表示設定を保存できません。入力値を確認して再試行してください。');
    }
    if (prefs.step === 4) {
      await persist({...nextPrefs,completed:true,deferred:false});
      location.assign('/control'); return;
    }
    await persist({...nextPrefs,step:prefs.step+1}); show();
  }
  el('setup-next').onclick = () => run(() => next());
  // Explanations remain available, but no longer obscure everyday controls.
  for (const panel of document.querySelectorAll('#settings-general-panel section, #settings-obs-panel section, #settings-bot-panel section')) {
    for (const p of [...panel.querySelectorAll('p')]) {
      if (p.closest('details') || p.id || p.classList.contains('save-hint') || p.querySelector('input,button,a,label') || p.textContent.length < 75) continue;
      const details = document.createElement('details'), summary = document.createElement('summary');
      summary.textContent = '詳しい説明'; p.before(details); details.append(summary,p);
    }
  }
  el('command-settings-form').closest('section').classList.add('setup-commands');
  el('setup-restart').disabled = true;
  api('/api/setup').then(s => {
    prefs = s; el('setup-restart').disabled = false;
    el('setup-state').textContent = prefs.completed ? 'セットアップ完了' : '未完了・途中から再開できます';
    if (new URLSearchParams(location.search).get('setup') === '1') show();
  }).catch(e => {el('setup-state').textContent = e.message + ' ページを再読み込みしてください。';});
})();
