const q = (selector) => document.querySelector(selector);

function setConnectionError(message) {
    q("#conn").textContent = `接続状態: ${message}`;
}

function renderList(selector, users, withCount) {
    const el = q(selector);
    el.innerHTML = "";

    users.forEach((user) => {
        const li = document.createElement("li");
        const name = user.display_name ?? "";

        if (withCount && !user.is_placeholder && user.participation_count !== undefined) {
            li.textContent = `${name} [参加: ${user.participation_count}回]`;
        } else {
            li.textContent = name;
        }

        el.appendChild(li);
    });
}

async function fetchState() {
    try {
        const response = await fetch("/api/state");
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }

        setConnectionError("Mock Provider connected");
        return await response.json();
    } catch (error) {
        console.error(error);
        setConnectionError("状態取得に失敗しました");
        return null;
    }
}

function renderState(state) {
    q("#open").textContent = `受付状態: ${state.is_open ? "受付中" : "受付終了"}`;
    q("#priority").textContent = `低消化回数優先モード: ${state.priority_mode ? "ON" : "OFF"}`;

    renderList("#now", state.now_view, true);
    renderList("#next", state.next_view, true);
    renderList("#queue", state.queue_view, true);

    const logs = [...state.logs].reverse().map((text) => ({ display_name: text }));
    renderList("#logs", logs, false);
}

async function refresh() {
    const state = await fetchState();
    if (!state) {
        return;
    }

    renderState(state);
}

async function post(api) {
    try {
        const response = await fetch(api, { method: "POST" });
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }
        await refresh();
    } catch (error) {
        console.error(error);
        setConnectionError("操作に失敗しました");
    }
}

document
    .querySelectorAll("button[data-api]")
    .forEach((button) => button.addEventListener("click", () => post(button.dataset.api)));

refresh();
setInterval(refresh, 2000);
