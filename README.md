# Telegram RustDL Range Bridge

A Telegram bot that accepts a forwarded document and returns a signed HTTPS URL compatible with RustDL.

## Architecture

Telegram remains the storage layer. Render stores no file copy. The public endpoint:

- answers HEAD with Content-Length, Accept-Ranges and ETag;
- forwards HTTP Range requests;
- returns 206 Partial Content and Content-Range;
- refuses to append if Telegram ignores a requested Range;
- uses HMAC-signed expiring URLs;
- limits concurrent streams.

## Telegram size limit

The standard Bot API currently limits getFile downloads to 20 MB. For files above that size, deploy Telegram's Local Bot API Server, which supports unlimited downloads. The bridge API can remain unchanged.

## Environment

Required:
- BOT_TOKEN
- LINK_SECRET
- WEBHOOK_SECRET

Optional:
- PUBLIC_BASE_URL (otherwise Render's RENDER_EXTERNAL_URL is used)
- LINK_TTL_SECONDS (default 86400)

## Render

Build:
pip install -r requirements.txt

Start:
gunicorn bot:app --bind 0.0.0.0:$PORT --workers 1 --threads 4 --timeout 0

One worker is intentional because webhook initialization and the stream semaphore are process-local.

## Security

Never commit BOT_TOKEN. The previous version of this repository contained a bot token, so that credential must be revoked and replaced before production use.
