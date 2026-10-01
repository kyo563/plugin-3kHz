(() => {
  fetch('/api/setup', {signal:AbortSignal.timeout(5000)}).then(r => {
    if (!r.ok) throw new Error();
    return r.json();
  }).then(s => {
    if (!s.completed && !s.deferred) location.replace('/settings?setup=1');
  }).catch(() => { /* Keep management usable; setup can be opened in settings. */ });
})();
