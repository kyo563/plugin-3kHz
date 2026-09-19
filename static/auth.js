(() => {
  const params = new URLSearchParams(location.hash.slice(1));
  const supplied = params.get('key');
  if (supplied) {
    sessionStorage.setItem('waiting-list-key', supplied);
    history.replaceState(null, '', location.pathname + location.search);
  }
  const originalFetch = window.fetch.bind(window);
  function showLogin() {
    if (document.querySelector('#connect-dialog')) return;
    const dialog = document.createElement('dialog');
    dialog.id = 'connect-dialog';
    const form = document.createElement('form');
    const label = document.createElement('label');
    label.textContent = '管理画面に接続：アプリの「他の画面で管理」から接続URLを開くか、管理キーを入力してください。';
    const input = document.createElement('input');
    input.type = 'password'; input.autocomplete = 'off'; input.required = true;
    input.setAttribute('aria-label', '管理キー');
    const button = document.createElement('button'); button.textContent = '接続';
    const feedback = document.createElement('p'); feedback.setAttribute('role', 'status');
    form.append(label, input, button, feedback); dialog.append(form); document.body.append(dialog);
    dialog.addEventListener('cancel', event => event.preventDefault());
    form.addEventListener('submit', async event => {
      event.preventDefault(); button.disabled = true;
      try {
        const key = input.value.trim();
        const response = await originalFetch('/api/capabilities', {headers: {Authorization: `Bearer ${key}`}});
        if (!response.ok) throw new Error();
        sessionStorage.setItem('waiting-list-key', key); location.reload();
      } catch (_) { feedback.textContent = '接続できません。アプリの起動と管理キーを確認してください。'; }
      finally { button.disabled = false; }
    });
    dialog.showModal();
  }
  window.fetch = async (resource, options = {}) => {
    const url = new URL(typeof resource === 'string' ? resource : resource.url, location.href);
    if (url.origin === location.origin && url.pathname.startsWith('/api/') && url.pathname !== '/api/overlay-state') {
      const headers = new Headers(options.headers || (resource instanceof Request ? resource.headers : undefined));
      const key = sessionStorage.getItem('waiting-list-key');
      if (key) headers.set('Authorization', `Bearer ${key}`);
      const response = await originalFetch(resource, {...options, headers});
      if (response.status === 401) showLogin();
      return response;
    }
    return originalFetch(resource, options);
  };
})();
