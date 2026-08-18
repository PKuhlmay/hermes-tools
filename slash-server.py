#!/usr/bin/env python3
"""Minimal HTTP server for Rocket.Chat slash-commands /todos and /ideen.

Queries Notion databases instead of local markdown files.
"""

import json
import os
import re
import subprocess
from http.server import HTTPServer, BaseHTTPRequestHandler

HERMES_HOME = os.path.expanduser("/opt/data")
PORT = int(os.environ.get("SLASH_PORT", "8765"))

NOTION_API_KEY = None
TODOS_DB_ID = "3c0afcfa-468d-81a6-8c14-c5d453393e46"
IDEEN_DB_ID = "3c0afcfa-468d-816e-9e6e-d8183bdcf8bb"


def load_notion_key():
    """Load NOTION_API_KEY from .env file."""
    global NOTION_API_KEY
    if NOTION_API_KEY:
        return True
    env_path = os.path.join(HERMES_HOME, ".env")
    try:
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("NOTION_API_KEY="):
                    NOTION_API_KEY = line.split("=", 1)[1].strip("'\"")
                    return True
    except Exception:
        pass
    return False


def notion_query(database_id, filter_dict=None, sorts=None):
    """Query a Notion database and return parsed results."""
    if not load_notion_key():
        return {"success": False, "error": "NOTION_API_KEY nicht gefunden."}

    payload = {}
    if filter_dict:
        payload["filter"] = filter_dict
    if sorts:
        payload["sorts"] = sorts

    try:
        import urllib.request

        url = f"https://api.notion.com/v1/databases/{database_id}/query"
        headers = {
            "Authorization": f"Bearer {NOTION_API_KEY}",
            "Notion-Version": "2022-06-28",
            "Content-Type": "application/json",
        }
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}


def fetch_todos():
    """Fetch open todos from Notion, sorted by priority descending."""
    result = notion_query(
        TODOS_DB_ID,
        filter_dict={"property": "Status", "select": {"equals": "Offen"}},
        sorts=[{"property": "Priorität", "direction": "descending"}],
    )
    if not result["success"]:
        return f"❌ Fehler: {result['error']}"

    results = result["data"].get("results", [])
    if not results:
        return "📋 *Todos*\n\nKeine offenen Todos. 🎉"

    out = ["📋 *Offene Todos*\n"]
    for r in results:
        props = r.get("properties", {})
        name = (
            props.get("Name", {})
            .get("title", [{}])[0]
            .get("text", {})
            .get("content", "Unbenannt")
        )
        prio = props.get("Priorität", {}).get("select")
        prio_name = prio.get("name", "Ohne") if prio else "Ohne"

        icons = {"Hoch": "🔥", "Mittel": "📊", "Niedrig": "💭", "Ohne": "☐"}
        icon = icons.get(prio_name, "☐")
        out.append(f"  {icon} **{prio_name}** — {name}")

    return "\n".join(out)


def fetch_ideas():
    """Fetch open ideas from Notion."""
    result = notion_query(
        IDEEN_DB_ID,
        filter_dict={"property": "Status", "select": {"equals": "Offen"}},
        sorts=[{"property": "Status", "direction": "ascending"}],
    )
    if not result["success"]:
        return f"❌ Fehler: {result['error']}"

    results = result["data"].get("results", [])
    if not results:
        return "💡 *Ideen*\n\nKeine offenen Ideen. 💭"

    out = ["💡 *Offene Ideen*\n"]
    for r in results:
        props = r.get("properties", {})
        name = (
            props.get("Name", {})
            .get("title", [{}])[0]
            .get("text", {})
            .get("content", "Unbenannt")
        )
        kategorie = props.get("Kategorie", {}).get("select")
        kat_name = kategorie.get("name", "") if kategorie else ""
        kat_tag = f" `[{kat_name}]`" if kat_name else ""
        out.append(f"  💭 {name}{kat_tag}")

    return "\n".join(out)


class SlashHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        path = self.path.rstrip("/")

        if path == "/todos":
            self._respond(fetch_todos())
        elif path == "/ideen":
            self._respond(fetch_ideas())
        elif path == "/health":
            self._respond("🤖 Slash-Server läuft! (Notion-Anbindung aktiv)")
        else:
            self._respond(f"Unbekannter Befehl: {path}", status=404)

    def do_GET(self):
        self.do_POST()

    def _respond(self, text, status=200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        body = json.dumps({"text": text}, ensure_ascii=False)
        self.wfile.write(body.encode("utf-8"))

    def log_message(self, format, *args):
        print(f"[SlashServer] {args[0]} {args[1]} {args[2]}")


if __name__ == "__main__":
    # Quick test on startup
    if load_notion_key():
        print(f"[SlashServer] NOTION_API_KEY geladen (endet auf ...{NOTION_API_KEY[-4:]})")
    else:
        print("[SlashServer] WARNUNG: NOTION_API_KEY nicht gefunden!")

    server = HTTPServer(("0.0.0.0", PORT), SlashHandler)
    print(f"[SlashServer] Listening on http://0.0.0.0:{PORT}")
    print(f"[SlashServer] Endpoints: /todos  /ideen  /health")
    server.serve_forever()