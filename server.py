#!/usr/bin/env python3
import json
import os
import re
import secrets
import shutil
import sqlite3
import zipfile
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).parent
DATA = ROOT / "data"
PUBLIC = ROOT / "public"
UPLOADS = DATA / "uploads"
DB_PATH = DATA / "app.db"

ADMIN_LOGIN = "admin"
ADMIN_PASSWORD = "kids123"
TOKENS = set()

RUS_LETTER_RE = re.compile(r"^[А-ЯЁ]+$")
HEX_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")


def ensure_dirs():
    for p in [DATA, PUBLIC, UPLOADS, UPLOADS / "crosswords", UPLOADS / "skins"]:
        p.mkdir(parents=True, exist_ok=True)


def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = db()
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS skins (
      id TEXT PRIMARY KEY,
      title TEXT NOT NULL,
      description TEXT,
      json TEXT NOT NULL,
      created_at TEXT NOT NULL
    )""")
    cur.execute("""
    CREATE TABLE IF NOT EXISTS crosswords (
      id TEXT PRIMARY KEY,
      title TEXT NOT NULL,
      description TEXT,
      publication_date TEXT,
      skin_id TEXT,
      hint_limit INTEGER NOT NULL,
      published INTEGER NOT NULL DEFAULT 0,
      json TEXT NOT NULL,
      created_at TEXT NOT NULL,
      FOREIGN KEY(skin_id) REFERENCES skins(id)
    )""")
    cur.execute("""
    CREATE TABLE IF NOT EXISTS leaderboard (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      crossword_id TEXT NOT NULL,
      player_name TEXT NOT NULL,
      time_seconds INTEGER NOT NULL,
      hints_used INTEGER NOT NULL,
      words_solved INTEGER NOT NULL,
      created_at TEXT NOT NULL
    )""")
    conn.commit()
    conn.close()


def seed_if_empty():
    conn = db()
    c = conn.cursor()
    if c.execute("SELECT COUNT(*) FROM crosswords").fetchone()[0] > 0:
        conn.close()
        return

    skin = {
      "id": "animals_forest",
      "title": "Лесные животные",
      "description": "Тёплая природная тема",
      "colors": {
        "background": "#DFF6FF", "mainPanel": "#0D2C54", "sidePanel": "#FFF8E8",
        "activeCell": "#FFD95A", "correctCell": "#DFFFCF", "wrongCell": "#FFD9D9",
        "primaryButton": "#48C83E", "secondaryButton": "#4AA3FF", "hintButton": "#FFC64A",
        "textMain": "#173052", "textLight": "#FFFFFF"
      },
      "background": {"type": "color", "image": ""},
      "crosswordBoard": {"backgroundImage": "", "cellStyle": "rounded", "cellRadius": 12, "cellBorder": "#D8E2EF", "activeGlow": True},
      "sidePanel": {"backgroundImage": "", "radius": 24},
      "character": {"name": "Лисёнок", "image": "", "position": "leftBottom"},
      "buttons": {"checkButtonText": "Проверить", "checkButtonIcon": "", "hintLetterIcon": "", "hintOnlyWordLettersIcon": "", "closeIcon": ""},
      "reward": {"successIcon": "", "factCardBackground": "#E8FFD8"}
    }

    cw = {
      "id": "animals_001",
      "title": "Кроссворд про животных",
      "description": "Детский кроссворд",
      "publicationDate": "2026-04-28",
      "skinId": "animals_forest",
      "gridWidth": 8,
      "gridHeight": 8,
      "hintLimit": 6,
      "grid": [
        ["#", "#", "К", "#", "#", "#", "#", "#"],
        ["С", "О", "Б", "А", "К", "А", "#", "#"],
        ["#", "#", "Т", "#", "#", "#", "#", "#"],
        ["#", "Л", "И", "С", "А", "#", "#", "#"],
        ["#", "Е", "#", "#", "#", "#", "#", "#"],
        ["#", "В", "#", "#", "#", "#", "#", "#"],
        ["#", "#", "#", "#", "#", "#", "#", "#"],
        ["#", "#", "#", "#", "#", "#", "#", "#"]
      ],
      "words": [
        {"id": "dog", "number": 1, "direction": "across", "row": 1, "col": 0, "answer": "СОБАКА", "question": "Верный друг человека", "image": "", "imageAlt": "Собака", "descriptionHint": "Это домашнее животное умеет охранять дом.", "fact": "Верно, это собака. Человек приручил собаку примерно 15 000 лет назад.", "extraLetters": ["Р", "Л", "Т"]},
        {"id": "cat", "number": 2, "direction": "down", "row": 0, "col": 2, "answer": "КОТ", "question": "Домашнее животное, которое мяукает", "image": "", "imageAlt": "Кот", "descriptionHint": "Это животное любит тепло и мурлычет.", "fact": "Верно, это кот. Кошки живут рядом с человеком уже несколько тысяч лет.", "extraLetters": ["С", "А"]},
        {"id": "fox", "number": 3, "direction": "across", "row": 3, "col": 1, "answer": "ЛИСА", "question": "Рыжая лесная хитрунья", "image": "", "imageAlt": "Лиса", "descriptionHint": "Живёт в лесу и любит охотиться ночью.", "fact": "Верно, это лиса. У лисы очень чуткий слух.", "extraLetters": ["М", "У", "П"]}
      ]
    }

    now = datetime.now(timezone.utc).isoformat()
    c.execute("INSERT INTO skins (id,title,description,json,created_at) VALUES (?,?,?,?,?)", (skin["id"], skin["title"], skin["description"], json.dumps(skin, ensure_ascii=False), now))
    c.execute("INSERT INTO crosswords (id,title,description,publication_date,skin_id,hint_limit,published,json,created_at) VALUES (?,?,?,?,?,?,?,?,?)", (cw["id"], cw["title"], cw["description"], cw["publicationDate"], cw["skinId"], cw["hintLimit"], 1, json.dumps(cw, ensure_ascii=False), now))
    conn.commit()
    conn.close()


def json_resp(handler, data, code=200):
    payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
    handler.send_response(code)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(payload)))
    handler.end_headers()
    handler.wfile.write(payload)


def read_json(handler):
    length = int(handler.headers.get("Content-Length", "0"))
    body = handler.rfile.read(length) if length else b"{}"
    return json.loads(body.decode("utf-8"))


def parse_multipart_upload(handler):
    ctype = handler.headers.get("Content-Type", "")
    m = re.search(r"boundary=(.+)", ctype)
    if not m:
        raise ValueError("Ожидалась загрузка файла")
    boundary = m.group(1).encode()
    length = int(handler.headers.get("Content-Length", "0"))
    data = handler.rfile.read(length)
    parts = data.split(b"--" + boundary)
    for p in parts:
        if b"Content-Disposition" in p and b"filename=" in p:
            head, content = p.split(b"\r\n\r\n", 1)
            name_match = re.search(br'filename="([^"]+)"', head)
            filename = name_match.group(1).decode("utf-8") if name_match else "upload.zip"
            return filename, content.rstrip(b"\r\n--")
    raise ValueError("Файл не найден в запросе")


def normalize_asset_path(base, rel_path):
    if not rel_path:
        return ""
    return f"/assets/{base}/{rel_path}"


def validate_crossword(cw, zip_names):
    required = ["id", "title", "gridWidth", "gridHeight", "hintLimit", "grid", "words"]
    for key in required:
        if key not in cw:
            return f"Не заполнено поле {key}"
    if not isinstance(cw["hintLimit"], int):
        return "Лимит подсказок должен быть целым числом"
    if len(cw["grid"]) != cw["gridHeight"] or any(len(r) != cw["gridWidth"] for r in cw["grid"]):
        return "Размер сетки не соответствует gridWidth и gridHeight"

    for w in cw["words"]:
        for req in ["id", "direction", "row", "col", "answer", "question", "image", "descriptionHint", "fact", "extraLetters"]:
            if req not in w or w[req] in [None, ""]:
                return f"У слова {w.get('id', 'unknown')} не заполнено поле {req}"
        if not RUS_LETTER_RE.match(w["answer"]):
            return f"Ответ {w['answer']} должен содержать только русские буквы"
        if w["image"] not in zip_names:
            return f"Не найден файл {w['image']}"
        r, c = w["row"], w["col"]
        dr, dc = (0, 1) if w["direction"] == "across" else (1, 0)
        for ch in w["answer"]:
            if not (0 <= r < cw["gridHeight"] and 0 <= c < cw["gridWidth"]):
                return "Координаты слова выходят за границы сетки"
            if cw["grid"][r][c] != ch:
                return f"Слово {w['answer']} не совпадает с буквами в сетке"
            r += dr
            c += dc
    return None


def validate_skin(skin, zip_names):
    for key in ["id", "title", "colors", "background", "crosswordBoard", "sidePanel", "character", "buttons", "reward"]:
        if key not in skin:
            return f"Не заполнено поле {key}"
    for ck in ["activeCell", "correctCell", "wrongCell", "primaryButton", "hintButton"]:
        val = skin.get("colors", {}).get(ck)
        if not val or not HEX_RE.match(val):
            return f"Некорректный цвет {ck}"
    must_files = [
        skin.get("background", {}).get("image", ""),
        skin.get("crosswordBoard", {}).get("backgroundImage", ""),
        skin.get("sidePanel", {}).get("backgroundImage", ""),
        skin.get("character", {}).get("image", ""),
        skin.get("buttons", {}).get("hintLetterIcon", ""),
        skin.get("buttons", {}).get("hintOnlyWordLettersIcon", ""),
        skin.get("reward", {}).get("successIcon", ""),
    ]
    for f in [x for x in must_files if x]:
        if f not in zip_names:
            return f"Не найден файл {f}"
    return None


class Handler(SimpleHTTPRequestHandler):
    def translate_path(self, path):
        parsed = urlparse(path).path
        if parsed.startswith('/assets/'):
            rel = parsed[len('/assets/'):]
            return str(UPLOADS / rel)
        return str(PUBLIC / (parsed.lstrip('/') or 'index.html'))

    def do_GET(self):
        p = urlparse(self.path).path
        if p == "/api/crosswords":
            conn = db()
            rows = conn.execute("SELECT id,title,description,publication_date,skin_id FROM crosswords WHERE published=1 ORDER BY created_at DESC").fetchall()
            conn.close()
            return json_resp(self, [dict(r) for r in rows])
        if p.startswith("/api/crosswords/"):
            cid = p.split("/")[-1]
            conn = db()
            row = conn.execute("SELECT * FROM crosswords WHERE id=? AND published=1", (cid,)).fetchone()
            if not row:
                conn.close()
                return json_resp(self, {"error": "Кроссворд не найден"}, 404)
            cw = json.loads(row["json"])
            if row["skin_id"]:
                skin_row = conn.execute("SELECT json FROM skins WHERE id=?", (row["skin_id"],)).fetchone()
                if skin_row:
                    skin = json.loads(skin_row[0])
                    for b in ["background.image", "crosswordBoard.backgroundImage", "sidePanel.backgroundImage", "character.image", "buttons.hintLetterIcon", "buttons.hintOnlyWordLettersIcon", "buttons.checkButtonIcon", "reward.successIcon"]:
                        ref = skin
                        keys = b.split('.')
                        for k in keys[:-1]:
                            ref = ref.get(k, {})
                        last = keys[-1]
                        if last in ref and ref[last]:
                            ref[last] = normalize_asset_path(f"skins/{skin['id']}", ref[last])
                    cw["skin"] = skin
            for w in cw["words"]:
                if w.get("image"):
                    w["image"] = normalize_asset_path(f"crosswords/{cw['id']}", w["image"])
            conn.close()
            return json_resp(self, cw)
        if p.startswith("/api/leaderboard/"):
            cid = p.split("/")[-1]
            conn = db()
            rows = conn.execute("SELECT player_name,time_seconds,hints_used,words_solved,created_at FROM leaderboard WHERE crossword_id=? ORDER BY time_seconds ASC,hints_used ASC,created_at ASC LIMIT 50", (cid,)).fetchall()
            conn.close()
            return json_resp(self, [dict(r) for r in rows])
        if p == "/api/admin/crosswords":
            if not self.is_admin():
                return json_resp(self, {"error": "Нет доступа"}, 401)
            conn = db()
            rows = conn.execute("SELECT id,title,published,skin_id,publication_date FROM crosswords ORDER BY created_at DESC").fetchall()
            conn.close()
            return json_resp(self, [dict(r) for r in rows])
        if p == "/api/admin/skins":
            if not self.is_admin():
                return json_resp(self, {"error": "Нет доступа"}, 401)
            conn = db()
            rows = conn.execute("SELECT id,title,description,created_at FROM skins ORDER BY created_at DESC").fetchall()
            conn.close()
            return json_resp(self, [dict(r) for r in rows])

        return super().do_GET()

    def do_POST(self):
        p = urlparse(self.path).path
        if p == "/api/admin/login":
            data = read_json(self)
            if data.get("login") == ADMIN_LOGIN and data.get("password") == ADMIN_PASSWORD:
                t = secrets.token_hex(16)
                TOKENS.add(t)
                return json_resp(self, {"token": t})
            return json_resp(self, {"error": "Неверный логин или пароль"}, 401)
        if p.startswith("/api/leaderboard/"):
            cid = p.split("/")[-1]
            data = read_json(self)
            name = (data.get("name") or "").strip()[:30]
            if not name:
                return json_resp(self, {"error": "Введите имя"}, 400)
            conn = db()
            conn.execute("INSERT INTO leaderboard (crossword_id,player_name,time_seconds,hints_used,words_solved,created_at) VALUES (?,?,?,?,?,?)", (cid, name, int(data.get("timeSeconds", 0)), int(data.get("hintsUsed", 0)), int(data.get("wordsSolved", 0)), datetime.now(timezone.utc).isoformat()))
            conn.commit()
            conn.close()
            return json_resp(self, {"ok": True})

        if not self.is_admin():
            return json_resp(self, {"error": "Нет доступа"}, 401)

        if p == "/api/admin/upload-crossword":
            try:
                _, blob = parse_multipart_upload(self)
                tmp = DATA / "tmp_crossword.zip"
                tmp.write_bytes(blob)
                with zipfile.ZipFile(tmp) as z:
                    names = z.namelist()
                    if "crossword.json" not in names:
                        return json_resp(self, {"error": "В архиве нет crossword.json"}, 400)
                    cw = json.loads(z.read("crossword.json").decode("utf-8"))
                    err = validate_crossword(cw, names)
                    if err:
                        return json_resp(self, {"error": err}, 400)
                    target = UPLOADS / "crosswords" / cw["id"]
                    if target.exists():
                        shutil.rmtree(target)
                    target.mkdir(parents=True, exist_ok=True)
                    z.extractall(target)
                conn = db()
                conn.execute(
                    "INSERT OR REPLACE INTO crosswords (id,title,description,publication_date,skin_id,hint_limit,published,json,created_at) VALUES (?,?,?,?,?,?,?,?,COALESCE((SELECT created_at FROM crosswords WHERE id=?),?))",
                    (cw["id"], cw["title"], cw.get("description", ""), cw.get("publicationDate", ""), cw.get("skinId"), int(cw["hintLimit"]), 0, json.dumps(cw, ensure_ascii=False), cw["id"], datetime.now(timezone.utc).isoformat()),
                )
                conn.commit()
                conn.close()
                return json_resp(self, {"ok": True, "id": cw["id"]})
            except Exception as e:
                return json_resp(self, {"error": f"Ошибка загрузки: {e}"}, 400)
        if p == "/api/admin/upload-skin":
            try:
                _, blob = parse_multipart_upload(self)
                tmp = DATA / "tmp_skin.zip"
                tmp.write_bytes(blob)
                with zipfile.ZipFile(tmp) as z:
                    names = z.namelist()
                    if "skin.json" not in names:
                        return json_resp(self, {"error": "В архиве нет skin.json"}, 400)
                    skin = json.loads(z.read("skin.json").decode("utf-8"))
                    err = validate_skin(skin, names)
                    if err:
                        return json_resp(self, {"error": err}, 400)
                    target = UPLOADS / "skins" / skin["id"]
                    if target.exists():
                        shutil.rmtree(target)
                    target.mkdir(parents=True, exist_ok=True)
                    z.extractall(target)
                conn = db()
                conn.execute("INSERT OR REPLACE INTO skins (id,title,description,json,created_at) VALUES (?,?,?,?,COALESCE((SELECT created_at FROM skins WHERE id=?),?))", (skin["id"], skin["title"], skin.get("description", ""), json.dumps(skin, ensure_ascii=False), skin["id"], datetime.now(timezone.utc).isoformat()))
                conn.commit()
                conn.close()
                return json_resp(self, {"ok": True, "id": skin["id"]})
            except Exception as e:
                return json_resp(self, {"error": f"Ошибка загрузки темы: {e}"}, 400)
        if p.endswith("/publish"):
            cid = p.split("/")[-2]
            data = read_json(self)
            conn = db()
            conn.execute("UPDATE crosswords SET published=? WHERE id=?", (1 if data.get("published") else 0, cid))
            conn.commit()
            conn.close()
            return json_resp(self, {"ok": True})
        if p.endswith("/skin"):
            cid = p.split("/")[-2]
            data = read_json(self)
            conn = db()
            conn.execute("UPDATE crosswords SET skin_id=? WHERE id=?", (data.get("skinId"), cid))
            conn.commit()
            conn.close()
            return json_resp(self, {"ok": True})
        return json_resp(self, {"error": "Не найдено"}, 404)

    def do_DELETE(self):
        p = urlparse(self.path).path
        if not self.is_admin():
            return json_resp(self, {"error": "Нет доступа"}, 401)
        if p.startswith("/api/admin/crosswords/"):
            cid = p.split("/")[-1]
            conn = db()
            conn.execute("DELETE FROM crosswords WHERE id=?", (cid,))
            conn.commit(); conn.close()
            folder = UPLOADS / "crosswords" / cid
            if folder.exists(): shutil.rmtree(folder)
            return json_resp(self, {"ok": True})
        if p.startswith("/api/admin/skins/"):
            sid = p.split("/")[-1]
            conn = db()
            conn.execute("DELETE FROM skins WHERE id=?", (sid,))
            conn.execute("UPDATE crosswords SET skin_id=NULL WHERE skin_id=?", (sid,))
            conn.commit(); conn.close()
            folder = UPLOADS / "skins" / sid
            if folder.exists(): shutil.rmtree(folder)
            return json_resp(self, {"ok": True})
        return json_resp(self, {"error": "Не найдено"}, 404)

    def is_admin(self):
        token = self.headers.get("X-Admin-Token", "")
        return token in TOKENS


if __name__ == "__main__":
    ensure_dirs()
    init_db()
    seed_if_empty()
    server = ThreadingHTTPServer(("0.0.0.0", int(os.environ.get("PORT", "8000"))), Handler)
    print("Сервер запущен: http://localhost:8000")
    server.serve_forever()
