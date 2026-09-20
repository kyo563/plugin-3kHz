"""Loopback API boundary: scoped bearer keys, origin/host checks, bounded bodies."""
from dataclasses import dataclass, field
import secrets
import json
import math
import re
from urllib.parse import urlsplit

from starlette.responses import JSONResponse



def validate_json_body(body: bytes) -> None:
    def reject_constant(value):
        raise ValueError("non-finite number")
    def visit(value, depth=0):
        if depth > 32:
            raise ValueError("JSON nesting limit")
        if isinstance(value, str):
            value.encode("utf-8", errors="strict")
        elif isinstance(value, float) and not math.isfinite(value):
            raise ValueError("non-finite number")
        elif isinstance(value, dict):
            for key, item in value.items():
                visit(key, depth + 1)
                visit(item, depth + 1)
        elif isinstance(value, list):
            for item in value:
                visit(item, depth + 1)
    visit(json.loads(body, parse_constant=reject_constant))


@dataclass
class AccessKeys:
    admin: str = field(default_factory=lambda: secrets.token_urlsafe(32))
    ingest: str = field(default_factory=lambda: secrets.token_urlsafe(32))


class LocalSecurityMiddleware:
    def __init__(self, app, keys: AccessKeys, max_body_bytes: int = 65536):
        self.app, self.keys, self.max_body_bytes = app, keys, max_body_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = {}
        for key, value in scope.get("headers", []):
            if key in headers and key in {b"host", b"origin", b"authorization", b"content-length"}:
                return await JSONResponse({"detail": "重複ヘッダー"}, 400)(scope, receive, send)
            headers[key] = value.decode("latin-1")
        host = headers.get(b"host", "")
        try:
            parsed = urlsplit("http://" + host)
            valid_host = parsed.hostname in {"127.0.0.1", "localhost"} and not parsed.username and not parsed.password and not parsed.path and not parsed.query and not parsed.fragment and parsed.netloc == host and parsed.port != 0
        except ValueError:
            valid_host = False
        if not valid_host:
            return await JSONResponse({"detail": "許可されないHost"}, 400)(scope, receive, send)
        origin = headers.get(b"origin")
        if origin is not None and origin != "http://" + host:
            return await JSONResponse({"detail": "許可されないOrigin"}, 403)(scope, receive, send)
        if headers.get(b"sec-fetch-site") == "cross-site":
            return await JSONResponse({"detail": "外部サイトからの接続を拒否しました"}, 403)(scope, receive, send)
        path = scope["path"]
        public = path == "/api/overlay-state" or (scope["method"] == "GET" and re.fullmatch(r"/api/font-assets/[a-f0-9]{64}", path) is not None)
        if path.startswith("/api/") and not public or path in {"/openapi.json", "/docs", "/redoc"}:
            authorization = headers.get(b"authorization", "")
            token = authorization[7:] if authorization.lower().startswith("bearer ") else ""
            admin = secrets.compare_digest(token.encode("utf-8"), self.keys.admin.encode("utf-8"))
            ingest = path in {"/api/comments/receive", "/api/onecomme/comment", "/api/onecomme/heartbeat"} and secrets.compare_digest(token.encode("utf-8"), self.keys.ingest.encode("utf-8"))
            if not (admin or ingest):
                return await JSONResponse({"detail": "管理画面から接続キーを設定してください"}, 401)(scope, receive, send)
        body_limit = 4 * 1024 * 1024 if path == "/api/control/restore" else self.max_body_bytes
        font_upload = path == "/api/fonts" and scope["method"] == "POST"
        if font_upload:
            body_limit = 32 * 1024 * 1024
        if scope["method"] in {"POST", "PUT", "PATCH"}:
            try:
                length = int(headers.get(b"content-length", "0"))
                if length < 0:
                    raise ValueError()
            except ValueError:
                return await JSONResponse({"detail": "不正なContent-Length"}, 400)(scope, receive, send)
            if length > body_limit:
                return await JSONResponse({"detail": "入力が大きすぎます"}, 413)(scope, receive, send)
            body = bytearray()
            while True:
                message = await receive()
                if message["type"] == "http.disconnect":
                    return
                body.extend(message.get("body", b""))
                if len(body) > body_limit:
                    return await JSONResponse({"detail": "入力が大きすぎます"}, 413)(scope, receive, send)
                if not message.get("more_body", False):
                    break
            expected_type = "application/octet-stream" if font_upload else "application/json"
            if body and headers.get(b"content-type", "").split(";")[0].strip().lower() != expected_type:
                return await JSONResponse({"detail": "application/jsonが必要です"}, 415)(scope, receive, send)
            if body and not font_upload:
                try:
                    validate_json_body(body)
                except (ValueError, UnicodeError, RecursionError):
                    return await JSONResponse({"detail": "JSONの形式・文字・数値または入れ子の深さが不正です"}, 400)(scope, receive, send)
            sent = False
            original_receive = receive
            async def bounded_receive():
                nonlocal sent
                if not sent:
                    sent = True
                    return {"type": "http.request", "body": bytes(body), "more_body": False}
                return await original_receive()
            receive = bounded_receive

        async def secure_send(message):
            if message["type"] == "http.response.start":
                extra = [(b"x-content-type-options", b"nosniff"), (b"referrer-policy", b"no-referrer"),
                    (b"content-security-policy", b"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; frame-ancestors 'self'; connect-src 'self'; img-src 'self' data: https://*.ggpht.com https://ggpht.com https://*.googleusercontent.com https://googleusercontent.com; object-src 'none'; base-uri 'none'")]
                if path != "/api/overlay-state":
                    extra.append((b"cache-control", b"no-store"))
                message = {**message, "headers": list(message.get("headers", [])) + extra}
            await send(message)
        await self.app(scope, receive, secure_send)
