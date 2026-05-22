const q = (selector) => document.querySelector(selector);

function drawUsers(selector, users) {
    const el = q(selector);
    el.innerHTML = "";

    users.forEach((user) => {
        const li = document.createElement("li");
        li.className = "name";
        li.textContent = user.display_name;
        el.appendChild(li);
    });
}

async function fetchOverlayState() {
    try {
        const response = await fetch("/api/overlay-state");
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }
        return await response.json();
    } catch (error) {
        console.error(error);
        return null;
    }
}

function renderOverlay(state) {
    q("#open").textContent = `受付状態: ${state.is_open ? "受付中" : "受付終了"}`;
    q("#wcount").textContent = `QUEUE人数: ${state.queue_count}人`;
    q("#gcount").textContent = `あと${state.queue_group_count}グループ`;
    q("#queue-summary").textContent = `あと${state.queue_group_count}グループ / ${state.queue_count}人`;

    drawUsers("#now", state.now_view);
    drawUsers("#next", state.next_view);
}

async function refresh() {
    const state = await fetchOverlayState();
    if (!state) {
        return;
    }

    renderOverlay(state);
}

refresh();
setInterval(refresh, 2000);
