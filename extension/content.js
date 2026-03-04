(() => {
  const KEYWORD = "参加希望";
  const MAX_PLAYERS = 3;

  const state = {
    participants: new Map(), // username => { joinNo, count }
    joinOrder: [],
    nextRounds: [[], []],
    chatObserver: null,
    lastProcessedMessageIds: new Set(),
  };

  let ui = null;

  function getSortedParticipants() {
    return [...state.participants.entries()]
      .map(([username, info]) => ({ username, ...info }))
      .sort((a, b) => {
        if (a.count !== b.count) return a.count - b.count;
        return a.joinNo - b.joinNo;
      });
  }

  function computeNextRounds() {
    const sorted = getSortedParticipants().map((item) => item.username);
    state.nextRounds = [
      sorted.slice(0, MAX_PLAYERS),
      sorted.slice(MAX_PLAYERS, MAX_PLAYERS * 2),
    ];
  }

  function registerParticipant(username) {
    if (!username || state.participants.has(username)) return false;

    const joinNo = state.joinOrder.length + 1;
    state.participants.set(username, { joinNo, count: 0 });
    state.joinOrder.push(username);
    computeNextRounds();
    render();
    return true;
  }

  function incrementCount(username) {
    const participant = state.participants.get(username);
    if (!participant) return;

    participant.count += 1;
    computeNextRounds();
    render();
  }

  function resetSession() {
    state.participants.clear();
    state.joinOrder = [];
    state.nextRounds = [[], []];
    state.lastProcessedMessageIds.clear();
    render();
  }

  function escapeHtml(text) {
    return text
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#39;");
  }

  function renderParticipantsTable() {
    const sorted = getSortedParticipants();

    if (sorted.length === 0) {
      return '<div class="yt-join-empty">参加者はまだいません</div>';
    }

    const rows = sorted
      .map(
        (p) => `
          <tr>
            <td>${p.joinNo}</td>
            <td title="${escapeHtml(p.username)}">${escapeHtml(p.username)}</td>
            <td>${p.count}</td>
            <td><button class="yt-join-plus1" data-username="${escapeHtml(p.username)}">+1</button></td>
          </tr>
        `
      )
      .join("");

    return `
      <table class="yt-join-table">
        <thead>
          <tr><th>No</th><th>ユーザー名</th><th>回数</th><th>操作</th></tr>
        </thead>
        <tbody>${rows}</tbody>
      </table>
    `;
  }

  function renderRound(round, title) {
    const cells = Array.from({ length: MAX_PLAYERS }, (_, i) => {
      const username = round[i] || "-";
      return `<li><span class="slot">${i + 1}</span><span class="name">${escapeHtml(username)}</span></li>`;
    }).join("");

    return `
      <div class="yt-join-round">
        <h4>${title}</h4>
        <ul>${cells}</ul>
      </div>
    `;
  }

  function render() {
    if (!ui) return;

    const [nextRound, nextNextRound] = state.nextRounds;

    ui.innerHTML = `
      <div class="yt-join-header">
        <h3>参加者マネージャー</h3>
        <button id="yt-join-reset">配信リセット</button>
      </div>
      <div class="yt-join-keyword">検知キーワード: <strong>${KEYWORD}</strong></div>
      <section>
        <h4>参加者一覧</h4>
        ${renderParticipantsTable()}
      </section>
      <section class="yt-join-schedule">
        <h4>参加予定（2回先まで）</h4>
        <div class="yt-join-rounds">
          ${renderRound(nextRound, "次回")}
          ${renderRound(nextNextRound, "次々回")}
        </div>
      </section>
    `;

    ui.querySelector("#yt-join-reset")?.addEventListener("click", resetSession);
    ui.querySelectorAll(".yt-join-plus1").forEach((button) => {
      button.addEventListener("click", () => {
        const username = button.getAttribute("data-username");
        if (username) incrementCount(username);
      });
    });
  }

  function getMessageText(node) {
    const messageNode = node.querySelector("#message") || node.querySelector(".message");
    return messageNode?.textContent?.trim() || "";
  }

  function getAuthorName(node) {
    const authorNode = node.querySelector("#author-name") || node.querySelector(".author-name");
    return authorNode?.textContent?.trim() || "";
  }

  function processChatNode(node) {
    if (!(node instanceof HTMLElement)) return;

    const id = node.getAttribute("id") || "";
    const key = `${id}:${node.textContent?.slice(0, 80) || ""}`;
    if (state.lastProcessedMessageIds.has(key)) return;
    state.lastProcessedMessageIds.add(key);

    if (state.lastProcessedMessageIds.size > 1000) {
      const arr = [...state.lastProcessedMessageIds].slice(-500);
      state.lastProcessedMessageIds = new Set(arr);
    }

    const text = getMessageText(node);
    if (!text.includes(KEYWORD)) return;

    const username = getAuthorName(node);
    if (!username) return;

    registerParticipant(username);
  }

  function attachChatObserver() {
    const chatApp = document.querySelector("yt-live-chat-app") || document.querySelector("#chat");
    if (!chatApp) return false;

    const observer = new MutationObserver((mutations) => {
      mutations.forEach((mutation) => {
        mutation.addedNodes.forEach((node) => {
          if (!(node instanceof HTMLElement)) return;

          const isChatMessage =
            node.matches?.("yt-live-chat-text-message-renderer") ||
            node.matches?.("yt-live-chat-paid-message-renderer") ||
            node.id === "message";

          if (isChatMessage) {
            processChatNode(node);
            return;
          }

          node
            .querySelectorAll?.(
              "yt-live-chat-text-message-renderer, yt-live-chat-paid-message-renderer"
            )
            .forEach((messageNode) => processChatNode(messageNode));
        });
      });
    });

    observer.observe(chatApp, { childList: true, subtree: true });
    state.chatObserver = observer;
    return true;
  }

  function mountUi() {
    if (document.getElementById("yt-join-manager")) {
      ui = document.getElementById("yt-join-manager");
      return;
    }

    ui = document.createElement("div");
    ui.id = "yt-join-manager";
    document.body.appendChild(ui);
    render();
  }

  function init() {
    mountUi();

    if (!attachChatObserver()) {
      const interval = setInterval(() => {
        if (attachChatObserver()) {
          clearInterval(interval);
        }
      }, 2000);
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
