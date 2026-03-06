import { createLiveChatApiPoller } from "./chatApiClient.js";

(() => {
  const KEYWORD = "参加希望";
  const MAX_PLAYERS = 3;
  const DEDUP_LIMIT = 2000;
  const DEDUP_RETAIN = 1000;

  const state = {
    participants: new Map(), // normalizedUsername => { username, displayName, joinNo, count }
    joinOrder: [],
    nextRounds: [[], []],
    chatObserver: null,
    processedMessageKeys: new Set(),
    domMonitoringHealthy: false,
    apiMonitoringHealthy: false,
    apiPoller: null,
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

  function makeDedupKey({ authorId, publishedAt, message }) {
    return `${authorId}::${publishedAt}::${message.trim()}`;
  }

  function rememberProcessedKey(key) {
    state.processedMessageKeys.add(key);
    if (state.processedMessageKeys.size > DEDUP_LIMIT) {
      const recent = [...state.processedMessageKeys].slice(-DEDUP_RETAIN);
      state.processedMessageKeys = new Set(recent);
    }
  }

  function processMessagePayload(payload) {
    const message = payload.message?.trim() || "";
    const authorId = payload.authorId?.trim() || "unknown-author";
    const publishedAt = payload.publishedAt?.trim() || "unknown-time";
    const authorName = payload.authorName?.trim() || payload.authorId?.trim() || "";

    const dedupKey = makeDedupKey({ authorId, publishedAt, message });
    if (state.processedMessageKeys.has(dedupKey)) return;
    rememberProcessedKey(dedupKey);

    if (!message.includes(KEYWORD)) return;
    if (!authorName) return;

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

  function getAuthorChannelId(node) {
    const authorNode = node.querySelector("#author-name") || node.querySelector(".author-name");
    return authorNode?.getAttribute("data-author-id") || "";
  }

  function getPublishedAt(node) {
    return (
      node.getAttribute("timestamp-usec") ||
      node.getAttribute("data-timestamp-usec") ||
      node.getAttribute("data-timestamp") ||
      ""
    );
  }

  function processChatNode(node) {
    if (!(node instanceof HTMLElement)) return;

    processMessagePayload({
      source: "dom",
      authorId: getAuthorChannelId(node),
      authorName: getAuthorName(node),
      message: getMessageText(node),
      publishedAt: getPublishedAt(node),
    });
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
    state.domMonitoringHealthy = true;
    return true;
  }

  function readStorage(keys) {
    if (!chrome?.storage?.local) {
      return Promise.resolve({});
    }

    return new Promise((resolve) => {
      chrome.storage.local.get(keys, (result) => {
        resolve(result || {});
      });
    });
  }

  async function startApiPolling() {
    try {
      const config = await readStorage(["YT_LIVE_CHAT_API_KEY", "YT_LIVE_CHAT_ID"]);
      const liveChatId =
        config.YT_LIVE_CHAT_ID || new URLSearchParams(window.location.search).get("liveChatId");
      const apiKey =
        config.YT_LIVE_CHAT_API_KEY || new URLSearchParams(window.location.search).get("apiKey");

      if (!liveChatId || !apiKey) {
        console.info("[yt-join-manager] Live Chat API 設定がないためDOM監視のみで継続します");
        return;
      }

      state.apiPoller = createLiveChatApiPoller({
        apiKey,
        liveChatId,
        onMessages: (messages) => {
          state.apiMonitoringHealthy = true;
          messages.forEach((message) => processMessagePayload(message));
        },
        onError: (error) => {
          state.apiMonitoringHealthy = false;
          console.warn("[yt-join-manager] API補助経路でエラー", error);
        },
      });
    } catch (error) {
      state.apiMonitoringHealthy = false;
      console.warn("[yt-join-manager] API補助経路の初期化に失敗", error);
    }
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

  function initDomMonitoringWithRetry() {
    if (!attachChatObserver()) {
      state.domMonitoringHealthy = false;
      const interval = setInterval(() => {
        if (attachChatObserver()) {
          clearInterval(interval);
        }
      }, 2000);
    }
  }

  function init() {
    mountUi();
    initDomMonitoringWithRetry();
    startApiPolling();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
