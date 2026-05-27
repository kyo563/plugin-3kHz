const statusEl = document.querySelector('#overlay-player-name-status');
const button = document.querySelector('#toggle-overlay-player-name');

async function refresh() {
  const res = await fetch('/api/state');
  const state = await res.json();
  statusEl.textContent = state.show_declared_player_name_on_overlay ? 'ON' : 'OFF';
}

button.addEventListener('click', async () => {
  await fetch('/api/settings/toggle-overlay-player-name', { method: 'POST' });
  await refresh();
});

refresh();
