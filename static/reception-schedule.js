(() => {
  const input = document.getElementById('reception-time');
  if (!input) return;
  const result = document.getElementById('reception-result');
  const endpoint = '/api/bot/reception-schedule';
  let timer, saving = false, dirty = false, version = 0, loaded = false;

  async function request(value) {
    const response = await fetch(endpoint, {
      ...(value === undefined ? {} : {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({enabled: value !== '', time: value || '23:00'})
      }), signal: AbortSignal.timeout(10000)
    });
    const data = await response.json();
    if (!response.ok) throw new Error('終了時刻を保存できませんでした');
    return data;
  }

  function render(state) {
    input.value = state.enabled ? state.time : '';
    result.textContent = '';
  }

  async function save() {
    clearTimeout(timer);
    if (!loaded || saving || !dirty) return;
    const value = input.value;
    if (value && !/^([01][0-9]|2[0-3]):[0-5][0-9]$/.test(value)) {
      result.textContent = '00:00〜23:59で入力してください。終了予約は変更していません。';
      return;
    }
    const edit = version;
    saving = true;
    result.textContent = '';
    try {
      const state = await request(value);
      if (edit === version) {
        dirty = false;
        render(state);
      }
    } catch (_) {
      if (edit === version) result.textContent = '保存を確認できません。接続を確認してEnterキーで再試行してください。';
    } finally {
      saving = false;
      if (edit !== version) save();
    }
  }

  input.addEventListener('input', () => {
    version += 1;
    dirty = true;
    result.textContent = '';
    clearTimeout(timer);
    timer = setTimeout(save, 600);
  });
  input.addEventListener('change', save);
  input.addEventListener('keydown', event => {
    if (event.key === 'Enter') { event.preventDefault(); save(); }
  });

  async function refresh() {
    if (saving || dirty || document.activeElement === input) return;
    const edit = version;
    try {
      const state = await request();
      if (edit !== version || saving || dirty || document.activeElement === input) return;
      render(state);
      loaded = true;
      input.disabled = false;
    } catch (_) {
      if (edit === version && !dirty) result.textContent = '終了予約を確認できません。接続を確認してください。';
    }
  }
  refresh();
  setInterval(() => { if (!document.hidden) refresh(); }, 3000);
})();
