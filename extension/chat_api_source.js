(() => {
  const DEFAULT_POLL_INTERVAL_MS = 5000;

  function readYtcfgValue(name) {
    const fromWindow = window.ytcfg?.data_?.[name];
    if (fromWindow) return fromWindow;

    const html = document.documentElement?.innerHTML || "";
    const match = html.match(new RegExp(`\"${name}\":\"([^\"]+)\"`));
    return match?.[1] || "";
  }

  function decodeContinuationToken(token) {
    try {
      return token.replace(/\\u003d/g, "=");
    } catch {
      return token;
    }
  }

  function findInitialContinuation() {
    const html = document.documentElement?.innerHTML || "";
    const patterns = [
      /"continuation":"([^"]+)"/,
      /"reloadContinuationData":\{"continuation":"([^"]+)"/,
      /"timedContinuationData":\{"continuation":"([^"]+)"/,
    ];

    for (const pattern of patterns) {
      const match = html.match(pattern);
      if (match?.[1]) {
        return decodeContinuationToken(match[1]);
      }
    }

    return "";
  }

  function findApiKey() {
    return readYtcfgValue("INNERTUBE_API_KEY");
  }

  function findClientVersion() {
    return readYtcfgValue("INNERTUBE_CLIENT_VERSION") || "2.20240301.00.00";
  }

  function toChatMessage(item) {
    const renderer =
      item?.liveChatTextMessageRenderer || item?.liveChatPaidMessageRenderer || null;
    if (!renderer) return null;

    const author = renderer.authorName?.simpleText || "";
    const authorId = renderer.authorExternalChannelId || "";
    const message = (renderer.message?.runs || []).map((run) => run.text || "").join("");
    const publishedAt = Number(renderer.timestampUsec || 0);

    if (!author || !message) return null;

    return {
      author,
      authorId,
      message,
      publishedAt,
    };
  }

  function extractFromActions(actions) {
    if (!Array.isArray(actions)) return [];

    return actions
      .map((action) => {
        const addItem = action?.addChatItemAction?.item;
        const replayItem = action?.addLiveChatTickerItemAction?.item;
        return toChatMessage(addItem || replayItem);
      })
      .filter(Boolean);
  }

  function nextContinuation(response) {
    const continuations = response?.continuationContents?.liveChatContinuation?.continuations || [];
    for (const cont of continuations) {
      const token =
        cont?.invalidationContinuationData?.continuation ||
        cont?.timedContinuationData?.continuation ||
        cont?.reloadContinuationData?.continuation;
      if (token) return token;
    }
    return "";
  }

  function nextTimeoutMs(response) {
    const continuations = response?.continuationContents?.liveChatContinuation?.continuations || [];
    for (const cont of continuations) {
      const timeout =
        cont?.invalidationContinuationData?.timeoutMs ||
        cont?.timedContinuationData?.timeoutMs ||
        cont?.reloadContinuationData?.timeoutMs;
      if (typeof timeout === "number") return timeout;
    }
    return DEFAULT_POLL_INTERVAL_MS;
  }

  function createYoutubeLiveChatApiSource({ onMessages, onStatus }) {
    let apiKey = "";
    let continuation = "";
    let timer = null;
    let isRunning = false;

    async function poll() {
      if (!isRunning) return;

      if (!apiKey || !continuation) {
        onStatus?.({ ok: false, reason: "missing-api-settings" });
        schedule(DEFAULT_POLL_INTERVAL_MS);
        return;
      }

      try {
        const response = await fetch(
          `https://www.youtube.com/youtubei/v1/live_chat/get_live_chat?key=${encodeURIComponent(apiKey)}`,
          {
            method: "POST",
            credentials: "include",
            headers: { "content-type": "application/json" },
            body: JSON.stringify({
              context: {
                client: {
                  clientName: "WEB",
                  clientVersion: findClientVersion(),
                },
              },
              continuation,
            }),
          }
        );

        if (!response.ok) {
          onStatus?.({ ok: false, reason: `http-${response.status}` });
          schedule(DEFAULT_POLL_INTERVAL_MS);
          return;
        }

        const data = await response.json();
        const actions = data?.continuationContents?.liveChatContinuation?.actions || [];
        const messages = extractFromActions(actions);
        if (messages.length > 0) {
          onMessages?.(messages);
        }

        continuation = nextContinuation(data) || continuation;
        onStatus?.({ ok: true });
        schedule(nextTimeoutMs(data));
      } catch (error) {
        onStatus?.({ ok: false, reason: error instanceof Error ? error.message : "unknown" });
        schedule(DEFAULT_POLL_INTERVAL_MS);
      }
    }

    function schedule(ms) {
      clearTimeout(timer);
      timer = setTimeout(poll, Math.max(1000, ms));
    }

    function start() {
      if (isRunning) return;
      apiKey = findApiKey();
      continuation = findInitialContinuation();
      isRunning = true;
      poll();
    }

    function stop() {
      isRunning = false;
      clearTimeout(timer);
      timer = null;
    }

    return { start, stop };
  }

  window.YtJoinApiSource = { createYoutubeLiveChatApiSource };
})();
