(() => {
  const KEYWORD = "参加希望";
  const MAX_PLAYERS = 3;

  const state = {
    participants: new Map(), // normalizedUsername => { username, displayName, joinNo, count }
    joinOrder: [],
    nextRounds: [[], []],
    chatObserver: null,
    lastProcessedMessageIds: new Set(),
  };

  let ui = null;

  function getSortedParticipants() {
    return [...state.participants.values()]
      .map((info) => ({ ...info }))
      .sort((a, b) => {
        if (a.count !== b.count) return a.count - b.count;
        return a.joinNo - b.joinNo;
      });
  }

  function normalizeUsername(username) {
    return username.trim().replace(/\s+/g, " ").toLocaleLowerCase("ja-JP");
  }

  function computeNextRounds() {
    const sorted = getSortedParticipants().map((item) => item.displayName);
    state.nextRounds = [
      sorted.slice(0, MAX_PLAYERS),
      sorted.slice(MAX_PLAYERS, MAX_PLAYERS * 2),
    ];
  }

  function registerParticipant(username) {
    const normalizedUsername = normalizeUsername(username);
    if (!normalizedUsername || state.participants.has(normalizedUsername)) return false;

    const joinNo = state.joinOrder.length + 1;
    state.participants.set(normalizedUsername, {
      username: username.trim(),
      displayName: username.trim(),
      joinNo,
      count: 0,
    });
    state.joinOrder.push(normalizedUsername);
    computeNextRounds();
    render();
    return true;
  }

  function updateDisplayName(normalizedUsername, displayName) {
    const participant = state.participants.get(normalizedUsername);
    if (!participant) return;

    const trimmedName = displayName.trim();
    participant.displayName = trimmedName || participant.username;
    computeNextRounds();
    render();
  }

  function incrementCount(username) {
    const normalizedUsername = normalizeUsername(username);
    const participant = state.participants.get(normalizedUsername);
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
            <td>
              <input
                class="yt-join-display-name"
                type="text"
                value="${escapeHtml(p.displayName)}"
                data-normalized-username="${escapeHtml(normalizeUsername(p.username))}"
                title="元ユーザー名: ${escapeHtml(p.username)}"
              />
            </td>
            <td>${p.count}</td>
            <td><button class="yt-join-plus1" data-normalized-username="${escapeHtml(normalizeUsername(p.username))}">+1</button></td>
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
        const username = button.getAttribute("data-normalized-username");
        if (username) incrementCount(username);
      });
    });

    ui.querySelectorAll(".yt-join-display-name").forEach((input) => {
      input.addEventListener("change", () => {
        const username = input.getAttribute("data-normalized-username");
        if (username) updateDisplayName(username, input.value);
      });
      input.addEventListener("blur", () => {
        const username = input.getAttribute("data-normalized-username");
        if (username) updateDisplayName(username, input.value);
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

  function normalizeMessageText(text) {
    return text.trim().replace(/\s+/g, " ");
  }

  function getNodeUniqueToken(node) {
    return (
      node.getAttribute("id") ||
      node.getAttribute("data-message-id") ||
      node.getAttribute("data-item-id") ||
      node.querySelector("#timestamp")?.getAttribute("aria-label") ||
      node.querySelector("#timestamp")?.textContent?.trim() ||
      ""
    );
  }

  function processChatNode(node) {
    if (!(node instanceof HTMLElement)) return;

    const username = getAuthorName(node);
    if (!username) return;

    const text = getMessageText(node);
    const normalizedAuthor = normalizeUsername(username);
    const normalizedText = normalizeMessageText(text);
    const uniqueToken = getNodeUniqueToken(node);
    const receivedAtBucket = Math.floor(Date.now() / 5000);

    // 同一ユーザー + 同一文面の短時間連投は同じ key になり、重複として除外される。
    // 投稿者名を key に含めるため、別ユーザーが同文面を送った場合は別 key で登録される。
    const key = uniqueToken
      ? `${normalizedAuthor}:${normalizedText}:${uniqueToken}`
      : `${normalizedAuthor}:${normalizedText}:bucket-${receivedAtBucket}`;

    if (state.lastProcessedMessageIds.has(key)) return;
    state.lastProcessedMessageIds.add(key);

    if (state.lastProcessedMessageIds.size > 1000) {
      const arr = [...state.lastProcessedMessageIds].slice(-500);
      state.lastProcessedMessageIds = new Set(arr);
    }

    if (!text.includes(KEYWORD)) return;

    registerParticipant(username);
  }

  function syncExistingChatNodes(root) {
    root
      .querySelectorAll(
        "yt-live-chat-text-message-renderer, yt-live-chat-paid-message-renderer"
      )
      .forEach((node) => processChatNode(node));
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
    syncExistingChatNodes(chatApp);
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
