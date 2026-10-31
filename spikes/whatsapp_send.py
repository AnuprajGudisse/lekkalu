"""Day 1 WhatsApp spike: send one message to TEST_RECIPIENT_NUMBER.

Usage: uv run --no-project --env-file .env python spikes/whatsapp_send.py ["text"]
Free-form text only works inside the 24-hour window (after the recipient messages
the test number). Pass --template to send the hello_world template instead.
"""
import json
import os
import sys
from pathlib import Path

import httpx

OUT = Path(__file__).parent / "out"
url = (
    f"https://graph.facebook.com/{os.environ['WHATSAPP_GRAPH_VERSION']}"
    f"/{os.environ['WHATSAPP_PHONE_NUMBER_ID']}/messages"
)
to = os.environ["TEST_RECIPIENT_NUMBER"]
args = sys.argv[1:]

if args[:1] == ["--template"]:
    body = {"type": "template", "template": {"name": "hello_world", "language": {"code": "en_US"}}}
else:
    body = {"type": "text", "text": {"body": args[0] if args else "లెక్కలు test: నమస్కారం!"}}

r = httpx.post(
    url,
    headers={"Authorization": f"Bearer {os.environ['WHATSAPP_ACCESS_TOKEN']}"},
    json={"messaging_product": "whatsapp", "recipient_type": "individual", "to": to, **body},
    timeout=10,
)
OUT.mkdir(exist_ok=True)
(OUT / "whatsapp_send_response.json").write_text(json.dumps(r.json(), indent=2, ensure_ascii=False))
print(r.status_code, json.dumps(r.json(), ensure_ascii=False))
