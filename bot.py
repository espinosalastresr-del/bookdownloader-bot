import base64
import hashlib
import hmac
import json
import logging
import os
import re
import threading
import time
from typing import Optional, Tuple

import requests
import telebot
from flask import Flask, Response, abort, jsonify, request

BOT_TOKEN = os.environ.get("BOT_TOKEN")
LINK_SECRET = os.environ.get("LINK_SECRET")
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET")
PORT = int(os.environ.get("PORT", "10000"))
LINK_TTL = int(os.environ.get("LINK_TTL_SECONDS", "86400"))
STREAM_TIMEOUT = (15, 60)

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is required")
if not LINK_SECRET:
    raise RuntimeError("LINK_SECRET is required")
if not WEBHOOK_SECRET:
    raise RuntimeError("WEBHOOK_SECRET is required")

app = Flask(__name__)
logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))
logger = logging.getLogger("rustdl-bridge")
bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML", threaded=False, exception_handler=None)
session = requests.Session()
stream_slots = threading.BoundedSemaphore(8)
TELEGRAM_API = "https://api.telegram.org"
TELEGRAM_FILE = "https://api.telegram.org/file"

def b64u(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()

def unb64u(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))

def sign_link(file_id: str, filename: str, size: Optional[int]) -> str:
    payload = {"v": 1, "file_id": file_id, "name": filename, "size": size, "exp": int(time.time()) + LINK_TTL}
    raw = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode()
    body = b64u(raw)
    sig = hmac.new(LINK_SECRET.encode(), body.encode(), hashlib.sha256).digest()
    return body + "." + b64u(sig)

def verify_link(token: str) -> dict:
    try:
        body, sig = token.split(".", 1)
        expected = hmac.new(LINK_SECRET.encode(), body.encode(), hashlib.sha256).digest()
        if not hmac.compare_digest(unb64u(sig), expected):
            abort(403)
        payload = json.loads(unb64u(body))
        if payload.get("v") != 1 or int(payload["exp"]) < int(time.time()):
            abort(410)
        return payload
    except (ValueError, KeyError, TypeError, json.JSONDecodeError):
        abort(404)

def telegram_file(file_id: str) -> Tuple[str, dict]:
    r = session.get(f"{TELEGRAM_API}/bot{BOT_TOKEN}/getFile", params={"file_id": file_id}, timeout=STREAM_TIMEOUT)
    r.raise_for_status()
    data = r.json()
    if not data.get("ok") or not data.get("result", {}).get("file_path"):
        raise RuntimeError("Telegram getFile returned no file_path")
    result = data["result"]
    return f"{TELEGRAM_FILE}/bot{BOT_TOKEN}/{result['file_path']}", result

def safe_filename(name: str) -> str:
    name = os.path.basename(name or "download")
    name = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", name).strip(" .")
    return name[:240] or "download"

def parse_range(value: Optional[str], size: int) -> Optional[Tuple[int, int]]:
    if not value:
        return None
    m = re.fullmatch(r"bytes=(\d+)-(\d*)", value.strip())
    if not m:
        abort(416)
    start = int(m.group(1))
    end = int(m.group(2)) if m.group(2) else size - 1
    if start >= size or end < start:
        abort(416)
    return start, min(end, size - 1)

def common_headers(response: Response, filename: str, size: int, file_id: str) -> None:
    response.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
    response.headers["Accept-Ranges"] = "bytes"
    response.headers["ETag"] = '"' + file_id + '"'
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["Content-Length"] = str(size)

def proxy(token: str):
    meta = verify_link(token)
    size = meta.get("size")
    if not isinstance(size, int) or size < 0:
        abort(404)
    filename = safe_filename(meta.get("name", "download"))
    byte_range = parse_range(request.headers.get("Range"), size)

    if request.method == "HEAD":
        response = Response(status=200)
        common_headers(response, filename, size, meta["file_id"])
        return response

    upstream_url, _ = telegram_file(meta["file_id"])
    headers = {}
    if byte_range:
        headers["Range"] = f"bytes={byte_range[0]}-{byte_range[1]}"

    if not stream_slots.acquire(timeout=5):
        return Response("Too many active downloads", status=429)
    try:
        upstream = session.get(upstream_url, headers=headers, stream=True, allow_redirects=True, timeout=STREAM_TIMEOUT)
    except requests.RequestException:
        stream_slots.release()
        return Response("Upstream unavailable", status=502)

    if byte_range:
        expected = f"bytes {byte_range[0]}-{byte_range[1]}/"
        if upstream.status_code != 206 or not upstream.headers.get("Content-Range", "").startswith(expected):
            upstream.close()
            stream_slots.release()
            return Response("Upstream does not provide a valid HTTP Range response", status=502)
        status = 206
        length = byte_range[1] - byte_range[0] + 1
    else:
        if upstream.status_code != 200:
            upstream.close()
            stream_slots.release()
            return Response("Telegram file unavailable", status=502)
        status = 200
        length = size

    def generate():
        try:
            for chunk in upstream.iter_content(chunk_size=64 * 1024):
                if chunk:
                    yield chunk
        finally:
            upstream.close()
            stream_slots.release()

    response = Response(generate(), status=status, mimetype="application/octet-stream")
    common_headers(response, filename, length, meta["file_id"])
    if status == 206:
        response.headers["Content-Range"] = upstream.headers["Content-Range"]
    return response

@app.get("/")
def health():
    return jsonify(status="ok", service="telegram-rustdl-range-proxy")

@app.route("/d/<token>", methods=["GET", "HEAD"])
def download(token):
    return proxy(token)

@bot.message_handler(commands=["start", "help"])
def start(message):
    logger.info("Handling /start or /help from chat_id=%s", getattr(message.chat, "id", None))
    bot.reply_to(message, "📦 <b>RustDL Telegram Bridge</b>\n\nReenvíame un archivo como documento y te devolveré un enlace HTTP compatible con Range para usarlo con RustDL.\n\n" f"Los enlaces expiran en {LINK_TTL // 3600} h.")

@bot.message_handler(content_types=["document", "audio", "video"])
def file_message(message):
    logger.info("Handling file message from chat_id=%s", getattr(message.chat, "id", None))
    item = message.document or message.audio or message.video
    file_id = item.file_id
    size = getattr(item, "file_size", None)
    filename = getattr(item, "file_name", None) or getattr(item, "title", None) or "download"
    filename = safe_filename(filename)
    token = sign_link(file_id, filename, size)
    base = (os.environ.get("PUBLIC_BASE_URL") or os.environ.get("RENDER_EXTERNAL_URL", "")).rstrip("/")
    if not base:
        bot.reply_to(message, "⚠️ No hay URL pública configurada.")
        return
    link = f"{base}/d/{token}"
    bot.reply_to(message, f"✅ <b>{filename}</b>\n📦 {size if size is not None else 'desconocido'} bytes\n\n<code>{link}</code>\n\nEnlace firmado y temporal. No se guarda una copia en Render.", disable_web_page_preview=True)

@app.post("/webhook/<secret>")
def webhook(secret):
    if not hmac.compare_digest(secret, WEBHOOK_SECRET):
        abort(403)
    telegram_secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    if not hmac.compare_digest(telegram_secret, WEBHOOK_SECRET):
        abort(403)
    update = request.get_json(silent=True)
    if not update:
        return "bad request", 400
    try:
        parsed = telebot.types.Update.de_json(json.dumps(update))
        logger.info("Telegram update received: update_id=%s", getattr(parsed, "update_id", None))
        bot.process_new_updates([parsed])
        logger.info("Telegram update processed: update_id=%s", getattr(parsed, "update_id", None))
        return "ok"
    except Exception:
        logger.exception("Telegram update processing failed")
        return "internal error", 500

def configure_webhook():
    base = (os.environ.get("PUBLIC_BASE_URL") or os.environ.get("RENDER_EXTERNAL_URL", "")).rstrip("/")
    if not base:
        raise RuntimeError("PUBLIC_BASE_URL or RENDER_EXTERNAL_URL is required")
    url = f"{base}/webhook/{WEBHOOK_SECRET}"
    r = session.post(f"{TELEGRAM_API}/bot{BOT_TOKEN}/setWebhook", json={"url": url, "secret_token": WEBHOOK_SECRET, "drop_pending_updates": False}, timeout=STREAM_TIMEOUT)
    r.raise_for_status()
    if not r.json().get("ok"):
        raise RuntimeError(f"setWebhook failed: {r.text}")
    logger.info("Telegram webhook configured: %s/webhook/<secret>", base)

if __name__ == "__main__":
    configure_webhook()
    app.run(host="0.0.0.0", port=PORT)
else:
    try:
        configure_webhook()
    except Exception as exc:
        print(f"webhook setup failed: {exc}", flush=True)
