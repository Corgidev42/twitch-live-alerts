"""Alerte Discord quand la chaîne Twitch passe en live (lancé par GitHub Actions).

Variables d'environnement :
  TWITCH_CLIENT_ID, TWITCH_CLIENT_SECRET  : app Twitch (dev.twitch.tv/console)
  DISCORD_WEBHOOK_URL                     : webhook du salon 🔴・en-direct
  TWITCH_LOGIN                            : pseudo de la chaîne (ex: mantate_)
  PING_ROLE_ID                            : rôle à pinger (🔔 Notif Live)
  TEST_MODE=1                             : poste une carte de test (sans ping) puis la supprime
"""
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

STATE_FILE = Path(__file__).with_name("state.json")
LOGIN = os.environ.get("TWITCH_LOGIN", "mantate_").lower()
ROLE = os.environ.get("PING_ROLE_ID", "")
WEBHOOK = os.environ.get("DISCORD_WEBHOOK_URL", "")
PURPLE, GREY = 0x9146FF, 0x4F545C
FALLBACK_MIN = 6  # le bot poste en ~1 min ; GitHub ne prend le relais que s'il n'a rien posté après 6 min


def http(method, url, body=None, headers=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={"User-Agent": "twitch-alerts/1.0", **(headers or {})})
    if data is not None:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=20) as r:
        txt = r.read().decode()
        return json.loads(txt) if txt else None


def twitch(path):
    cid, secret = os.environ["TWITCH_CLIENT_ID"], os.environ["TWITCH_CLIENT_SECRET"]
    q = urllib.parse.urlencode(dict(client_id=cid, client_secret=secret, grant_type="client_credentials"))
    token = http("POST", f"https://id.twitch.tv/oauth2/token?{q}")["access_token"]
    return http("GET", f"https://api.twitch.tv/helix/{path}", headers={"Client-Id": cid, "Authorization": f"Bearer {token}"})["data"]


def load_state():
    try:
        return json.loads(STATE_FILE.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {"live": False}


def live_embed(stream, user):
    thumb = stream["thumbnail_url"].replace("{width}", "1280").replace("{height}", "720") + f"?t={int(time.time())}"
    return {
        "title": stream["title"] or "Live en cours",
        "url": f"https://www.twitch.tv/{LOGIN}",
        "color": PURPLE,
        "author": {"name": f"{user['display_name']} est en live !", "url": f"https://www.twitch.tv/{LOGIN}", "icon_url": user["profile_image_url"]},
        "fields": [{"name": "🎮 Jeu", "value": stream.get("game_name") or "Juste discuter", "inline": True},
                   {"name": "👀 Viewers", "value": str(stream.get("viewer_count", 0)), "inline": True}],
        "image": {"url": thumb},
        "thumbnail": {"url": user["profile_image_url"]},
        "footer": {"text": "Clique sur le titre pour rejoindre le live"},
        "timestamp": stream["started_at"],
    }


def end_embed(state):
    start = datetime.fromisoformat(state["started_at"].replace("Z", "+00:00"))
    mins = int((datetime.now(timezone.utc) - start).total_seconds() // 60)
    return {
        "title": state.get("title") or "Live terminé",
        "url": f"https://www.twitch.tv/{LOGIN}",
        "color": GREY,
        "author": {"name": "⚫ Live terminé"},
        "description": f"🎮 {state.get('game') or '—'} · ⏱️ {mins // 60}h{mins % 60:02d}\nMerci à tous d'être passés ! Les replays sont sur la chaîne.",
        "timestamp": state["started_at"],
    }


def main():
    missing = [k for k in ("TWITCH_CLIENT_ID", "TWITCH_CLIENT_SECRET", "DISCORD_WEBHOOK_URL") if not os.environ.get(k)]
    if missing:
        print("Secrets manquants, rien à faire pour l'instant :", ", ".join(missing))
        return
    if os.environ.get("TEST_MODE") == "1":
        msg = http("POST", WEBHOOK + "?wait=true", {"embeds": [{"title": "🧪 Test des alertes Twitch", "color": PURPLE,
                   "description": "Si tu vois ce message, la connexion GitHub → Discord marche. Il va disparaître tout seul."}],
                   "allowed_mentions": {"parse": []}})
        user = twitch(f"users?login={LOGIN}")
        print("Twitch OK :", user[0]["display_name"] if user else f"chaîne {LOGIN} introuvable")
        time.sleep(15)
        http("DELETE", f"{WEBHOOK}/messages/{msg['id']}")
        print("Test OK : message posté puis supprimé")
        return

    state = load_state()
    streams = twitch(f"streams?user_login={LOGIN}")
    stream = streams[0] if streams else None
    month = datetime.now(timezone.utc).strftime("%Y-%m")

    age_min = (datetime.now(timezone.utc) - datetime.fromisoformat(stream["started_at"].replace("Z", "+00:00"))).total_seconds() / 60 if stream else 0
    if stream and stream["id"] != state.get("stream_id") and age_min < FALLBACK_MIN:
        print(f"Live lancé il y a {age_min:.0f} min : on laisse le bot poster l'alerte")
    elif stream and stream["id"] != state.get("stream_id"):
        user = twitch(f"users?login={LOGIN}")[0]
        body = {"content": f"<@&{ROLE}> 🔴 **{user['display_name']}** vient de lancer le live !" if ROLE else None,
                "embeds": [live_embed(stream, user)],
                "allowed_mentions": {"roles": [ROLE] if ROLE else []}}
        msg = http("POST", WEBHOOK + "?wait=true", body)
        state = {"live": True, "stream_id": stream["id"], "message_id": msg["id"], "started_at": stream["started_at"],
                 "title": stream["title"], "game": stream.get("game_name"), "by": "github"}
        print("Alerte postée (secours GitHub) :", stream["title"])
    elif stream:
        state.update(title=stream["title"], game=stream.get("game_name"))
        print("Toujours en live")
    elif state.get("live"):
        if state.get("message_id"):
            try:
                http("PATCH", f"{WEBHOOK}/messages/{state['message_id']}", {"content": None, "embeds": [end_embed(state)]})
            except urllib.error.HTTPError as e:
                print("Impossible de modifier l'alerte :", e.code)
        state = {"live": False, "last_stream_id": state.get("stream_id")}
        print("Live terminé")
    else:
        print("Pas en live")

    state["heartbeat"] = month  # 1 commit/mois minimum pour que GitHub garde le planning actif
    STATE_FILE.write_text(json.dumps(state, indent=1, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    try:
        main()
    except urllib.error.HTTPError as e:
        print("Erreur HTTP", e.code, e.read().decode()[:300], file=sys.stderr)
        sys.exit(1)
