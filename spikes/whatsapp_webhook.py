"""Day 1 WhatsApp spike: minimal webhook receiver.

Usage: uv run --no-project --env-file .env python spikes/whatsapp_webhook.py
Then: cloudflared tunnel --url http://localhost:8001
Register https://<tunnel>/webhook with WHATSAPP_VERIFY_TOKEN and subscribe to "messages".
Signature verification is Day 3 work; this spike only captures payloads.
"""
import json
import os
import time
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Request, Response

OUT = Path(__file__).parent / "out" / "webhooks"
app = FastAPI()


@app.get("/webhook")
def verify(request: Request):
    q = request.query_params
    if q.get("hub.mode") == "subscribe" and q.get("hub.verify_token") == os.environ["WHATSAPP_VERIFY_TOKEN"]:
        return Response(q.get("hub.challenge", ""), media_type="text/plain")
    return Response(status_code=403)


@app.post("/webhook")
async def receive(request: Request):
    payload = await request.json()
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{time.time_ns()}.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False))
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            for m in change.get("value", {}).get("messages", []):
                detail = m.get("text", {}).get("body") or m.get(m["type"], {})
                print(f"message type={m['type']} id={m['id']} -> {detail}")
    return Response(status_code=200)


if __name__ == "__main__":
    uvicorn.run(app, port=8001)
