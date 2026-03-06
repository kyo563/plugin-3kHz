(() => {
  const KEYWORD = "参加希望";
  const MAX_PLAYERS = 3;

  const state = {
    participants: new Map(), // normalizedUsername => { username, displayName, joinNo, count }
    joinOrder: [],
    nextRounds: [[], []],
    chatObserver: null,
    processedMessageKeys: new Set(),
    domSourceHealthy: false,
    apiSourceHealthy: false,
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

  function normalizeMessageText(text) {
    return text.trim().replace(/\s+/g, " ");
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
    state.processedMessageKeys.clear();
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

  function currentPathLabel() {
    if (state.domSourceHealthy && state.apiSourceHealthy) return "通常+補助（DOM+API）";
    if (state.domSourceHealthy) return "通常（DOM）";
    if (state.apiSourceHealthy) return "補助（API）";
    return "再同期待ち";
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
      <div class="yt-join-keyword">取得経路: <strong>${currentPathLabel()}</strong></div>
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

  function buildDedupKey({ authorId, authorName, message, publishedAtMs }) {
    const safeAuthorId = normalizeUsername(authorId || authorName || "");
    const normalizedMessage = normalizeMessageText(message || "");
    const publishedBucket = Math.floor((publishedAtMs || Date.now()) / 1000);
    return `${safeAuthorId}:${publishedBucket}:${normalizedMessage}`;
  }

  function rememberDedupKey(key) {
    state.processedMessageKeys.add(key);
    if (state.processedMessageKeys.size > 2000) {
      state.processedMessageKeys = new Set([...state.processedMessageKeys].slice(-1000));
    }
  }

  function ingestMessage(messageEvent) {
    const authorName = messageEvent.authorName?.trim() || "";
    const text = messageEvent.message?.trim() || "";
    if (!authorName || !text) return;

    const dedupKey = buildDedupKey(messageEvent);
    if (state.processedMessageKeys.has(dedupKey)) return;
    rememberDedupKey(dedupKey);

    if (!text.includes(KEYWORD)) return;
    registerParticipant(authorName);
  }

  function getMessageText(node) {
    const messageNode = node.querySelector("#message") || node.querySelector(".message");
    return messageNode?.textContent?.trim() || "";
  }

  function getAuthorName(node) {
    const authorNode = node.querySelector("#author-name") || node.querySelector(".author-name");
    return authorNode?.textContent?.trim() || "";
  }

  function getDomPublishedAtMs(node) {
    const raw =
      node.getAttribute("data-timestamp-usec") ||
      node.querySelector("#timestamp")?.getAttribute("aria-label") ||
      node.querySelector("#timestamp")?.textContent?.trim() ||
      "";

    const usec = Number(raw);
    if (!Number.isNaN(usec) && usec > 0) return Math.floor(usec / 1000);
    return Date.now();
  }

  function processChatNode(node) {
    if (!(node instanceof HTMLElement)) return;

    const authorName = getAuthorName(node);
    const message = getMessageText(node);
    if (!authorName || !message) return;

    ingestMessage({
      authorName,
      authorId: node.getAttribute("author-external-channel-id") || "",
      message,
      publishedAtMs: getDomPublishedAtMs(node),
    });
  }

  function syncExistingChatNodes(root) {
    root
      .querySelectorAll(
        "yt-live-chat-text-message-renderer, yt-live-chat-paid-message-renderer"
      )
      .forEach((node) => processChatNode(node));
  }

  function setDomSourceStatus(healthy) {
    const changed = state.domSourceHealthy !== healthy;
    state.domSourceHealthy = healthy;
    if (changed) render();
  }

  function setApiSourceStatus(healthy) {
    const changed = state.apiSourceHealthy !== healthy;
    state.apiSourceHealthy = healthy;
    if (changed) render();
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
    setDomSourceStatus(true);
    return true;
  }

  function attachApiPolling() {
    const sourceFactory = window.YtJoinApiSource?.createYoutubeLiveChatApiSource;
    if (!sourceFactory) {
      setApiSourceStatus(false);
      return;
    }

    const source = sourceFactory({
      onMessages(messages) {
        messages.forEach((message) => {
          ingestMessage({
            authorName: message.author,
            authorId: message.authorId,
            message: message.message,
            publishedAtMs: Math.floor((message.publishedAt || 0) / 1000),
          });
        });
      },
      onStatus(status) {
        setApiSourceStatus(Boolean(status?.ok));
      },
    });

    source.start();
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
    attachApiPolling();

    if (!attachChatObserver()) {
      setDomSourceStatus(false);
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
