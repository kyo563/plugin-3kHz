export function createLiveChatApiPoller(config) {
  const {
    apiKey,
    liveChatId,
    intervalMs = 5000,
    onMessages,
    onError,
  } = config;

  if (!apiKey || !liveChatId) {
    throw new Error("Live Chat API の設定が不足しています");
  }

  let timerId = null;
  let stopped = false;
  let nextPageToken = "";

  async function pollOnce() {
    if (stopped) return;

    const params = new URLSearchParams({
      part: "snippet,authorDetails",
      liveChatId,
      maxResults: "200",
      key: apiKey,
    });

    if (nextPageToken) {
      params.set("pageToken", nextPageToken);
    }

    const response = await fetch(
      `https://www.googleapis.com/youtube/v3/liveChat/messages?${params.toString()}`
    );

    if (!response.ok) {
      throw new Error(`Live Chat API error: ${response.status}`);
    }

    const payload = await response.json();
    nextPageToken = payload.nextPageToken || nextPageToken;

    const messages = (payload.items || []).map((item) => ({
      source: "api",
      authorId: item.authorDetails?.channelId || "",
      authorName: item.authorDetails?.displayName || "",
      message: item.snippet?.displayMessage || "",
      publishedAt: item.snippet?.publishedAt || "",
    }));

    onMessages(messages);

    const nextInterval = Number(payload.pollingIntervalMillis) || intervalMs;
    timerId = window.setTimeout(runLoop, nextInterval);
  }

  async function runLoop() {
    if (stopped) return;

    try {
      await pollOnce();
    } catch (error) {
      onError(error);
      timerId = window.setTimeout(runLoop, intervalMs);
    }
  }

  runLoop();

  return {
    stop() {
      stopped = true;
      if (timerId) {
        clearTimeout(timerId);
      }
    },
  };
}
