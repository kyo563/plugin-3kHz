const statusEl = document.querySelector('#overlay-player-name-status');
const button = document.querySelector('#toggle-overlay-player-name');
let currentAction = 'refresh';

function setUiState(label, className, buttonText, disabled, action) {
  statusEl.textContent = label;
  statusEl.className = `status ${className}`;
  button.textContent = buttonText;
  button.disabled = disabled;
  if (action) {
    currentAction = action;
  }
}

function applyOverlayPlayerNameState(enabled) {
  if (enabled) {
    setUiState('ON', 'on', 'OFFにする', false, 'toggle');
    return;
  }
  setUiState('OFF', 'off', 'ONにする', false, 'toggle');
}

async function refresh() {
  setUiState('読込中', 'loading', '読込中', true, 'refresh');

  try {
    const res = await fetch('/api/state');
    if (!res.ok) {
      throw new Error(`Failed to fetch state: ${res.status}`);
    }

    const state = await res.json();
    applyOverlayPlayerNameState(Boolean(state.show_declared_player_name_on_overlay));
  } catch (error) {
    console.error(error);
    setUiState('取得失敗', 'error', '再読み込み', false, 'refresh');
  }
}

button.addEventListener('click', async () => {
  if (currentAction === 'refresh') {
    await refresh();
    return;
  }

  setUiState('読込中', 'loading', '切り替え中', true, 'toggle');

  try {
    const res = await fetch('/api/settings/toggle-overlay-player-name', { method: 'POST' });
    if (!res.ok) {
      throw new Error(`Failed to toggle setting: ${res.status}`);
    }
  } catch (error) {
    console.error(error);
    setUiState('取得失敗', 'error', '再試行', false, 'toggle');
    return;
  }

  await refresh();
});

refresh();
