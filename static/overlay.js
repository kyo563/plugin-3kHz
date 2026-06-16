const q = (selector) => document.querySelector(selector);

function drawUsers(selector, users) {
    const el = q(selector);
    el.innerHTML = "";

    users.forEach((user) => {
        const li = document.createElement("li");
        li.className = "name";
        if (user.is_placeholder) {
            li.classList.add("placeholder");
        }
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
    const open = q("#open");
    open.textContent = state.is_open ? "受付中" : "受付終了";
    open.className = state.is_open ? "status-open" : "status-closed";

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
