"""Read-only official YouTube API connector; credentials live only in memory."""
import asyncio
from collections import OrderedDict
from datetime import datetime, timezone
import re
from urllib.parse import urlsplit, parse_qs

import httpx
from pydantic import ValidationError
from app.schemas.comment import ReceivedComment
from app.services.command_detector import CommandDetector
from app.services.comment_normalizer import CommentNormalizer


def video_id(value):
    value = value.strip()
    if re.fullmatch(r"[A-Za-z0-9_-]{11}", value):
        return value
    url = urlsplit(value)
    if url.scheme != "https" or url.username or url.password or url.port not in (None, 443):
        raise ValueError("YouTubeの配信URLまたは11文字の動画IDを入力してください")
    host = url.hostname
    parts = url.path.strip("/").split("/")
    candidate = ""
    if host == "youtu.be" and len(parts) == 1:
        candidate = parts[0]
    elif host in {"youtube.com", "www.youtube.com", "m.youtube.com"}:
        if url.path == "/watch":
            candidate = parse_qs(url.query).get("v", [""])[0]
        elif len(parts) == 2 and parts[0] in {"live", "shorts", "embed"}:
            candidate = parts[1]
    if not re.fullmatch(r"[A-Za-z0-9_-]{11}", candidate):
        raise ValueError("動画単体のYouTube配信URLを入力してください")
    return candidate


class ChatError(Exception):
    def __init__(self, message, retry=False):
        super().__init__(message)
        self.retry = retry


class YouTubeChat:
    def __init__(self, services, client_factory=None, sleep=asyncio.sleep):
        self.services = services
        self.client_factory = client_factory or (lambda: httpx.AsyncClient(timeout=15, follow_redirects=False, trust_env=False))
        self.sleep = sleep
        self.task = None
        self.lock = asyncio.Lock()
        self.state = dict(status="stopped", message="未接続", video_id="", received=0, commands=0, last_received=None)

    def snapshot(self):
        return dict(self.state)

    async def start(self, url, key):
        selected = video_id(url)
        if not re.fullmatch(r"[A-Za-z0-9_-]{20,200}", key):
            raise ValueError("APIキーの形式を確認してください")
        async with self.lock:
            await self._stop()
            self.state = dict(status="connecting", message="YouTubeに接続中", video_id=selected, received=0, commands=0, last_received=None)
            self.task = asyncio.create_task(self._run(selected, key))
        return self.snapshot()

    async def _stop(self):
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
            self.task = None
        self.state.update(status="stopped", message="受信を停止しました")

    async def stop(self):
        async with self.lock:
            await self._stop()
        return self.snapshot()

    async def _get(self, client, resource, key, **params):
        try:
            # Key is a header, never a query string (httpx logs request URLs).
            response = await client.get("https://www.googleapis.com/youtube/v3/" + resource,
                                        params=params, headers={"X-Goog-Api-Key": key})
        except httpx.HTTPError:
            raise ChatError("通信できません。回線を確認してください", retry=True) from None
        if response.status_code != 200:
            try:
                reason = response.json()["error"]["errors"][0]["reason"]
            except (ValueError, KeyError, IndexError, TypeError):
                reason = ""
            messages = {
                "quotaExceeded": "YouTube APIの利用上限です。Google Cloudで割当を確認してください",
                "dailyLimitExceeded": "YouTube APIの1日の利用上限です",
                "keyInvalid": "APIキーが無効です",
                "accessNotConfigured": "YouTube Data API v3を有効にしてください",
                "liveChatEnded": "配信が終了したため受信を停止しました",
                "liveChatDisabled": "この配信のチャットは無効です",
                "liveChatNotFound": "ライブチャットが見つかりません",
                "forbidden": "この配信を読み取る権限がありません。公開配信とキーの制限を確認してください",
            }
            retry = response.status_code >= 500 or response.status_code == 429 or reason == "rateLimitExceeded"
            raise ChatError(messages.get(reason, "YouTube APIへの接続に失敗しました。APIの有効化・キーの制限・配信状態を確認してください"), retry)
        try:
            data = response.json()
            if not isinstance(data, dict):
                raise ValueError()
            return data
        except ValueError:
            raise ChatError("YouTubeからの応答を読み取れません", retry=True) from None

    async def _run(self, selected, key):
        try:
            async with self.client_factory() as client:
                info = await self._get(client, "videos", key, part="liveStreamingDetails", id=selected)
                items = info.get("items", [])
                chat_id = items[0].get("liveStreamingDetails", {}).get("activeLiveChatId") if items else None
                if not chat_id:
                    raise ChatError("配信中のライブチャットが見つかりません。配信開始・公開状態・チャット有効化を確認してください")
                token = None
                failures = 0
                handles = OrderedDict()
                while True:
                    try:
                        params = dict(part="snippet,authorDetails", liveChatId=chat_id, maxResults=200)
                        if token:
                            params["pageToken"] = token
                        data = await self._get(client, "liveChat/messages", key, **params)
                        next_token = data.get("nextPageToken")
                        if not next_token:
                            if data.get("offlineAt"):
                                raise ChatError("配信が終了したため受信を停止しました")
                            raise ChatError("受信の継続情報がありません。接続し直してください")
                        # First page is history. Begin with the following page so old
                        # join/cancel messages are never replayed after reconnect/restart.
                        if token:
                            for item in data.get("items", []):
                                await self._consume(client, key, item, handles)
                        token = next_token
                        failures = 0
                        self.state.update(status="connected", message="受信中：この表示後のコメントから反映します（受付中にしてください）")
                        if data.get("offlineAt"):
                            raise ChatError("配信が終了したため受信を停止しました")
                        interval = max(10, float(data.get("pollingIntervalMillis", 10000)) / 1000)
                        await self.sleep(interval)
                    except ChatError as exc:
                        if not exc.retry or failures >= 5:
                            raise
                        failures += 1
                        self.state.update(status="retrying", message=f"通信待ち：{failures}/5回目の再接続")
                        await self.sleep(min(120, 10 * 2 ** failures))
        except asyncio.CancelledError:
            raise
        except ChatError as exc:
            self.state.update(status="error", message=str(exc))
        except Exception:
            # Never return external response bodies, URLs or credentials to the UI/log.
            self.state.update(status="error", message="コメント受信を停止しました。接続し直してください")

    async def _consume(self, client, key, item, handles):
        try:
            snippet = item["snippet"]
            author = item["authorDetails"]
            if snippet.get("type") != "textMessageEvent":
                return
            comment = ReceivedComment(source="youtube", externalMessageId=item["id"],
                receivedAt=snippet["publishedAt"], displayName=author["displayName"],
                youtubeNickname=author["displayName"], userKey=author["channelId"],
                avatarUrl=author.get("profileImageUrl"),
                message=snippet["textMessageDetails"]["messageText"])
        except (KeyError, TypeError, ValidationError):
            return
        self.state["received"] += 1
        self.state["last_received"] = datetime.now(timezone.utc).isoformat()
        command = CommandDetector().detect(CommentNormalizer().normalize(comment.message))
        if command == "ignore":
            return
        # Resolve the real handle only for participants; stable channel ID is identity.
        if command == "join" and comment.user_key not in handles:
            try:
                channels = await self._get(client, "channels", key, part="snippet", id=comment.user_key)
                custom = (channels.get("items") or [{}])[0].get("snippet", {}).get("customUrl", "")
                handles[comment.user_key] = custom if re.fullmatch(r"@[^\s]{1,199}", custom) else None
            except ChatError:
                handles[comment.user_key] = None
            if len(handles) > 512:
                handles.popitem(last=False)
        comment.youtube_handle = handles.get(comment.user_key)
        result = self.services.receive_comment(comment)
        if not result.duplicate:
            self.state["commands"] += 1
