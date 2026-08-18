#!/usr/bin/env python3
"""Minimal HTTP server for Rocket.Chat slash-commands /todos and /ideen."""

import json
import os
import re
from http.server import HTTPServer, BaseHTTPRequestHandler

HERMES_HOME = os.path.expanduser("/opt/data")
TODOS_PATH = os.path.join(HERMES_HOME, "todos.md")
IDEAS_PATH = os.path.join(HERMES_HOME, "ideas.md")
PORT = int(os.environ.get("SLASH_PORT", "8765"))


def read_file(path):
    """Read a file and return (exists, content_or_error)."""
    if not os.path.isfile(path):
        return False, "Datei nicht gefunden."
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return True, fh.read()
    except Exception as e:
        return False, f"Fehler beim Lesen: {e}"


def render_todos(markdown):
    """Parse a simple markdown TODO list into a compact formatted string."""
    lines = markdown.splitlines()
    sections = {}
    current_section = "Allgemein"
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("## "):
            current_section = stripped.lstrip("# ")
        elif stripped.startswith("- [ ]"):
            task = re.sub(r"^- \[.\] ", "", stripped).strip()
            sections.setdefault(current_section, []).append(("offen", task))
        elif stripped.startswith("- [x]"):
            task = re.sub(r"^- \[.\] ", "", stripped).strip()
            sections.setdefault(current_section, []).append(("erledigt", task))
    if not sections:
        return "📋 *Todos*\n\nKeine Einträge gefunden."

    out = ["📋 *Todos*\n"]
    for section, items in sections.items():
        if section == "Erledigt":
            continue
        out.append(f"*{section}:*")
        for status, task in items:
            icon = "☐" if status == "offen" else "☑"
            out.append(f"  {icon} {task}")
        out.append("")
    # Erledigte ganz unten
    if "Erledigt" in sections:
        out.append(f"*Erledigt:*")
        for status, task in sections["Erledigt"]:
            out.append(f"  ☑ {task}")
    return "\n".join(out)


def render_ideas(markdown):
    """Parse the ideas file into a compact format."""
    lines = markdown.splitlines()
    out = ["💡 *Ideen*"]
    current_section = ""
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("## "):
            current_section = stripped.lstrip("# ")
        elif stripped.startswith("- [ ]"):
            idea = re.sub(r"^- \[.\] ", "", stripped).strip()
            out.append(f"  💭 {idea}")
        elif stripped.startswith("- [x]"):
            idea = re.sub(r"^- \[.\] ", "", stripped).strip()
            out.append(f"  ✅ {idea}")
    return "\n".join(out)


class SlashHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        path = self.path.rstrip("/")

        if path == "/todos":
            exists, content = read_file(TODOS_PATH)
            if not exists:
                self._respond(content)
            else:
                self._respond(render_todos(content))
        elif path == "/ideen":
            exists, content = read_file(IDEAS_PATH)
            if not exists:
                self._respond(content)
            else:
                self._respond(render_ideas(content))
        elif path == "/health":
            self._respond("🤖 Slash-Server läuft!", status=200)
        else:
            self._respond(f"Unbekannter Befehl: {path}", status=404)

    def do_GET(self):
        self.do_POST()

    def _respond(self, text, status=200):
        """Send response in Rocket.Chat slash-command format."""
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        body = json.dumps({"text": text}, ensure_ascii=False)
        self.wfile.write(body.encode("utf-8"))

    def log_message(self, format, *args):
        print(f"[SlashServer] {args[0]} {args[1]} {args[2]}")


if __name__ == "__main__":
    server = HTTPServer(("0.0.0.0", PORT), SlashHandler)
    print(f"[SlashServer] Listening on http://0.0.0.0:{PORT}")
    print(f"[SlashServer] Endpoints: /todos  /ideen  /health")
    server.serve_forever()