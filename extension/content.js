(() => {
  const MAX_PLAYERS = 3;
  const STORAGE_KEY = "ytJoinManagerState";
  const DEFAULT_KEYWORDS = ["参加希望", "参加きぼう", "参加希望です", "参加したい", "さんか希望"];
  const DEFAULT_SETTINGS = {
    greenScreen: false,
    fontFamily: "default",
    keywordInput: DEFAULT_KEYWORDS.join("\n"),
  };

  const state = {
    participants: new Map(), // username => { joinNo, count }
    joinOrder: [],
    nextRounds: [[], []],
    chatObserver: null,
    lastProcessedMessageIds: new Set(),
    settings: { ...DEFAULT_SETTINGS },
    keywords: [...DEFAULT_KEYWORDS],
  };

  let ui = null;

  function getStorageArea() {
    return typeof chrome !== "undefined" && chrome.storage?.local ? chrome.storage.local : null;
  }

  function normalizeText(text) {
    return (text || "")
      .trim()
      .toLowerCase()
      .replaceAll(/[\s　]+/g, "")
      .replaceAll("ｻﾝｶ", "さんか");
  }

  function parseKeywords(text) {
    const list = text
      .split(/\n|,|、/)
      .map((item) => normalizeText(item))
      .filter(Boolean);
    return [...new Set(list)];
  }

  function serializeState() {
    return {
      participants: state.joinOrder
        .map((username) => {
          const info = state.participants.get(username);
          if (!info) return null;
          return { username, joinNo: info.joinNo, count: info.count };
        })
        .filter(Boolean),
      settings: { ...state.settings },
    };
  }

  async function persistState() {
    const storage = getStorageArea();
    if (!storage) return;
    await storage.set({ [STORAGE_KEY]: serializeState() });
  }

  async function loadState() {
    const storage = getStorageArea();
    if (!storage) return;

    const result = await storage.get(STORAGE_KEY);
    const saved = result?.[STORAGE_KEY];
    if (!saved) return;

    state.participants.clear();
    state.joinOrder = [];

    (saved.participants || []).forEach((item, index) => {
      const username = item?.username?.trim();
      if (!username) return;
      const joinNo = Number.isFinite(item.joinNo) ? item.joinNo : index + 1;
      const count = Number.isFinite(item.count) ? Math.max(0, item.count) : 0;
      state.participants.set(username, { joinNo, count });
      state.joinOrder.push(username);
    });

    state.settings = {
      ...DEFAULT_SETTINGS,
      ...(saved.settings || {}),
    };

    state.keywords = parseKeywords(state.settings.keywordInput);
    if (state.keywords.length === 0) {
      state.keywords = [...DEFAULT_KEYWORDS];
      state.settings.keywordInput = DEFAULT_KEYWORDS.join("\n");
    }

    normalizeJoinNo();
    computeNextRounds();
  }

  function normalizeJoinNo() {
    state.joinOrder = state.joinOrder.filter((username) => state.participants.has(username));
    state.joinOrder.forEach((username, index) => {
      const participant = state.participants.get(username);
      if (!participant) return;
      participant.joinNo = index + 1;
    });
  }

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

  async function registerParticipant(username) {
    if (!username || state.participants.has(username)) return false;

    const joinNo = state.joinOrder.length + 1;
    state.participants.set(username, { joinNo, count: 0 });
    state.joinOrder.push(username);
    computeNextRounds();
    render();
    await persistState();
    return true;
  }

  async function incrementCount(username, delta = 1) {
    const participant = state.participants.get(username);
    if (!participant) return;

    participant.count = Math.max(0, participant.count + delta);
    computeNextRounds();
    render();
    await persistState();
  }

  async function removeParticipant(username) {
    if (!state.participants.has(username)) return;
    state.participants.delete(username);
    state.joinOrder = state.joinOrder.filter((item) => item !== username);
    normalizeJoinNo();
    computeNextRounds();
    render();
    await persistState();
  }

  async function resetSession() {
    state.participants.clear();
    state.joinOrder = [];
    state.nextRounds = [[], []];
    state.lastProcessedMessageIds.clear();
    render();
    await persistState();
  }

  function escapeHtml(text) {
    return text
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#39;");
  }

  function fontClassName() {
    if (state.settings.fontFamily === "gothic") return "yt-font-gothic";
    if (state.settings.fontFamily === "mincho") return "yt-font-mincho";
    if (state.settings.fontFamily === "mono") return "yt-font-mono";
    return "yt-font-default";
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
            <td class="yt-join-actions">
              <button class="yt-join-btn yt-join-plus1" data-username="${escapeHtml(
                p.username
              )}" data-delta="1">+1</button>
              <button class="yt-join-btn yt-join-minus1" data-username="${escapeHtml(
                p.username
              )}" data-delta="-1">-1</button>
              <button class="yt-join-btn yt-join-remove" data-remove-username="${escapeHtml(
                p.username
              )}">削除</button>
            </td>
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
    const keywordPreview = state.keywords.join(" / ") || "(未設定)";
    const greenClass = state.settings.greenScreen ? "yt-green-screen" : "";

    ui.className = `${fontClassName()} ${greenClass}`.trim();
    ui.innerHTML = `
      <div class="yt-join-layout">
        <div class="yt-join-main">
          <div class="yt-join-header">
            <h3>参加者マネージャー</h3>
            <button id="yt-join-reset" class="yt-join-btn">配信リセット</button>
          </div>
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
        </div>
        <aside class="yt-join-settings">
          <h4>設定</h4>
          <div class="yt-setting-block">
            <label for="yt-font-family">フォント</label>
            <select id="yt-font-family">
              <option value="default" ${
                state.settings.fontFamily === "default" ? "selected" : ""
              }>デフォルト</option>
              <option value="gothic" ${
                state.settings.fontFamily === "gothic" ? "selected" : ""
              }>ゴシック</option>
              <option value="mincho" ${
                state.settings.fontFamily === "mincho" ? "selected" : ""
              }>明朝</option>
              <option value="mono" ${
                state.settings.fontFamily === "mono" ? "selected" : ""
              }>等幅</option>
            </select>
          </div>
          <div class="yt-setting-block">
            <button id="yt-toggle-green" class="yt-join-btn">
              ${state.settings.greenScreen ? "通常背景に戻す" : "背景をグリーンバック化"}
            </button>
          </div>
          <div class="yt-setting-block">
            <label for="yt-keywords">検知ワード（改行・カンマ区切り）</label>
            <textarea id="yt-keywords" rows="6">${escapeHtml(state.settings.keywordInput)}</textarea>
            <button id="yt-save-keywords" class="yt-join-btn">検知ワードを保存</button>
          </div>
          <div class="yt-join-keyword">現在の検知: <strong>${escapeHtml(keywordPreview)}</strong></div>
        </aside>
      </div>
    `;

    ui.querySelector("#yt-join-reset")?.addEventListener("click", () => {
      resetSession();
    });

    ui.querySelectorAll("button[data-username]").forEach((button) => {
      button.addEventListener("click", () => {
        const username = button.getAttribute("data-username");
        const delta = Number(button.getAttribute("data-delta") || "1");
        if (username) incrementCount(username, delta);
      });
    });

    ui.querySelectorAll("button[data-remove-username]").forEach((button) => {
      button.addEventListener("click", () => {
        const username = button.getAttribute("data-remove-username");
        if (username) removeParticipant(username);
      });
    });

    ui.querySelector("#yt-toggle-green")?.addEventListener("click", async () => {
      state.settings.greenScreen = !state.settings.greenScreen;
      render();
      await persistState();
    });

    ui.querySelector("#yt-font-family")?.addEventListener("change", async (event) => {
      const value = event.target?.value || "default";
      state.settings.fontFamily = value;
      render();
      await persistState();
    });

    ui.querySelector("#yt-save-keywords")?.addEventListener("click", async () => {
      const input = ui.querySelector("#yt-keywords")?.value || "";
      const parsed = parseKeywords(input);
      if (parsed.length === 0) {
        state.keywords = [...DEFAULT_KEYWORDS];
        state.settings.keywordInput = DEFAULT_KEYWORDS.join("\n");
      } else {
        state.keywords = parsed;
        state.settings.keywordInput = input;
      }
      render();
      await persistState();
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

  function shouldRegisterByText(text) {
    const normalizedText = normalizeText(text);
    if (!normalizedText) return false;
    return state.keywords.some((keyword) => normalizedText.includes(keyword));
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
    if (!shouldRegisterByText(text)) return;

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

  async function init() {
    await loadState();
    computeNextRounds();
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
    document.addEventListener("DOMContentLoaded", () => {
      init();
    });
  } else {
    init();
  }
})();
