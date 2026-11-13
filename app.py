from __future__ import annotations

import base64
import getpass
import hashlib
import hmac
import json
import math
import os
import re
import secrets
import smtplib
import sqlite3
import ssl
import sys
import time
from email.message import EmailMessage
from contextlib import closing
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse


ROOT = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get("ADMIN_DATA_DIR", ROOT / "data")).resolve()
DB_PATH = Path(os.environ.get("ADMIN_DB", DATA_DIR / "admin.sqlite3")).resolve()
LOG_DIR = DATA_DIR / "admin-logs"
HOST = os.environ.get("ADMIN_HOST", "127.0.0.1")
PORT = int(os.environ.get("ADMIN_PORT", "7070"))
SESSION_MINUTES = int(os.environ.get("SESSION_MINUTES", "30"))
OTP_TTL = int(os.environ.get("OTP_TTL_SECONDS", "600"))
APP_ENV = os.environ.get("APP_ENV", "development")
COOKIE_SECURE = os.environ.get("COOKIE_SECURE") == "1"
MAX_BODY = 2_500_000
PAGE_SIZE = 10

# These are the application's primary content databases. They are separate from
# admin.sqlite3, which stores admin accounts, sessions, permissions and audit.
PRIMARY_DATABASES = {
    "news": {"file": "news.db", "table": "news"},
    "support": {"file": "profile_support.db", "table": "support_messages"},
    "complaints": {"file": "profile_yammer.db", "table": "yammer_messages"},
}
PRIMARY_DB_DIR = Path(os.environ.get("ADMIN_PRIMARY_DB_DIR", ROOT / "db")).resolve()

MODULES = {
    "users", "lots", "shops", "news", "support", "complaints", "banners",
    "currencies", "newsletter", "transactions", "promotion", "refunds",
    "profit", "stats", "audit", "admins", "scan", "bulk", "assistant", "project_data",
}
ADMIN_MODULES = {"users", "lots", "shops", "news", "support", "complaints", "currencies", "newsletter"}
SUPER_MODULES = MODULES - ADMIN_MODULES
FIELDS = {
    "users": ["id", "nick", "email", "balance", "status", "fake", "last_login", "created_at"],
    "lots": ["id", "title", "seller", "price", "status", "fake", "category", "subcategory", "auction_date"],
    "shops": ["id", "name", "owner", "status", "promoted"],
    "news": ["id", "cat", "badge", "title", "desc", "body", "img", "read_time", "published", "created_at"],
    "support": ["id", "date_message", "header_message", "message", "priority", "proof", "user_id", "user_name", "user_mail"],
    "complaints": ["id", "date_message", "reason", "message", "proof", "link_proof", "email_user", "user_id", "user_name"],
    "banners": ["id", "place", "title", "from", "to", "active", "paid", "amount"],
    "currencies": ["id", "code", "rate", "updated"],
    "newsletter": ["id", "email", "status", "joined"],
    "transactions": ["id", "date", "user", "type", "amount", "status"],
    "promotion": ["id", "item", "slot", "until", "paid"],
    "refunds": ["id", "user", "amount", "reason", "status"],
    "profit": ["id", "period", "gross", "refunds", "net"],
    "stats": ["id", "date", "users", "active_users", "lots", "fake_lots"],
    "admins": ["id", "login", "email", "role", "status", "sections"],
    "scan": ["id", "table_name", "columns", "scanned_at"],
}
SENSITIVE_KEYS = {"password", "password_hash", "salt", "otp", "token", "secret", "csrf"}
USER_FIELDS = {"nick": "nick", "nickname": "nick", "email": "email", "id": "id", "shop": "shop"}
VALID_PLACEMENTS = {
    "category", "header", "category_header", "footer", "home_carousel",
    "home_current", "mobile_super",
}
SAMPLE_DATE = time.strftime("%Y-%m-%d", time.localtime())


class APIError(Exception):
    def __init__(self, status: int, code: str, message: str = "") -> None:
        super().__init__(message or code)
        self.status = status
        self.code = code
        self.message = message or code


def now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB_PATH, timeout=15)
    db.row_factory = sqlite3.Row
    db.create_function("casefold", 1, lambda value: value.casefold() if value else "")
    db.execute("PRAGMA foreign_keys=ON")
    db.execute("PRAGMA journal_mode=WAL")
    return db


def hash_password(password: str, salt_hex: str | None = None) -> tuple[str, str]:
    salt = bytes.fromhex(salt_hex) if salt_hex else secrets.token_bytes(16)
    hashed = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1).hex()
    return hashed, salt.hex()


def password_matches(password: str, salt: str, expected: str) -> bool:
    got, _ = hash_password(password, salt)
    return hmac.compare_digest(got, expected)


def safe_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def redact(value: dict | None) -> dict | None:
    if not value:
        return None
    return {key: item for key, item in value.items() if key.lower() not in SENSITIVE_KEYS}


def append_admin_log(admin_id: int, record: dict) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    path = LOG_DIR / f"admin-{admin_id}.txt"
    line = json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n"
    descriptor = os.open(path, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o600)
    with os.fdopen(descriptor, "a", encoding="utf-8") as log_file:
        log_file.write(line)
        log_file.flush()
        os.fsync(log_file.fileno())


def audit(
    db: sqlite3.Connection,
    actor_id: int | None,
    actor: str,
    action: str,
    module: str,
    object_id: str | int | None = None,
    before: dict | None = None,
    after: dict | None = None,
    ip: str = "",
) -> None:
    before_safe, after_safe = redact(before), redact(after)
    stamp = now()
    db.execute(
        "INSERT INTO audit(actor_id,actor,action,module,object_id,before_json,after_json,ip,created_at) "
        "VALUES(?,?,?,?,?,?,?,?,?)",
        (
            actor_id, actor, action, module,
            str(object_id) if object_id is not None else None,
            safe_json(before_safe) if before_safe is not None else None,
            safe_json(after_safe) if after_safe is not None else None,
            ip, stamp,
        ),
    )
    if actor_id is not None:
        append_admin_log(
            actor_id,
            {
                "time": stamp,
                "admin": actor,
                "action": action,
                "module": module,
                "object_id": object_id,
                "before": before_safe,
                "after": after_safe,
                "ip": ip,
            },
        )


def seed(db: sqlite3.Connection) -> None:
    samples = {
        "users": [
            {"nick": "sample_user", "email": "user@example.test", "balance": 0, "status": "active",
             "fake": False, "last_login": SAMPLE_DATE, "created_at": now()},
            {"nick": "demo_fake", "email": "fake@example.test", "balance": 0, "status": "active",
             "fake": True, "last_login": "", "created_at": now()},
        ],
        "lots": [
            {"title": "Демо-лот", "seller": "sample_user", "price": 0, "status": "active",
             "fake": False, "category": "Демо", "subcategory": "Пример", "auction_date": SAMPLE_DATE},
            {"title": "Демо-аукцион", "seller": "demo_fake", "price": 0, "status": "active",
             "fake": True, "category": "Демо", "subcategory": "Аукцион", "auction_date": SAMPLE_DATE},
        ],
        "shops": [{"name": "Демо-магазин", "owner": "sample_user", "status": "active", "promoted": False}],
        "news": [{"title": "Добро пожаловать", "text": "<p>Демонстрационная новость</p>",
                  "image_data": "", "date": SAMPLE_DATE, "status": "published"}],
        "support": [{"from": "sample_user", "date": now(), "status": "new", "text": "Демо-обращение"}],
        "complaints": [{"type": "lot", "target": "Демо-лот", "status": "new", "text": "Демо-жалоба"}],
        "banners": [{"place": "category", "title": "Демо-баннер", "from": SAMPLE_DATE,
                     "to": "", "active": True, "paid": False, "amount": 0}],
        "currencies": [
            {"code": "RUB", "rate": 0, "updated": "Не подключён источник курса"},
            {"code": "EUR", "rate": 0, "updated": "Не подключён источник курса"},
        ],
        "newsletter": [{"email": "subscriber@example.test", "status": "active", "joined": SAMPLE_DATE}],
        "transactions": [{"date": now(), "user": "sample_user", "type": "Демо",
                          "amount": 0, "status": "demo"}],
        "promotion": [],
        "refunds": [],
    }
    for module, rows in samples.items():
        for item in rows:
            db.execute(
                "INSERT INTO records(module,data,created_at,updated_at) VALUES(?,?,?,?)",
                (module, safe_json(item), now(), now()),
            )


def init_db() -> None:
    with connect() as db:
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS admins(
                id INTEGER PRIMARY KEY,
                username TEXT UNIQUE NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                salt TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'admin',
                permissions TEXT NOT NULL DEFAULT '[]',
                status TEXT NOT NULL DEFAULT 'active',
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS sessions(
                id TEXT PRIMARY KEY,
                admin_id INTEGER NOT NULL REFERENCES admins(id) ON DELETE CASCADE,
                csrf TEXT NOT NULL,
                created_at INTEGER NOT NULL,
                last_seen INTEGER NOT NULL,
                profit_until INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS otp_codes(
                id INTEGER PRIMARY KEY,
                admin_id INTEGER NOT NULL REFERENCES admins(id) ON DELETE CASCADE,
                code_hash TEXT NOT NULL,
                expires INTEGER NOT NULL,
                attempts INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS audit(
                id INTEGER PRIMARY KEY,
                actor_id INTEGER,
                actor TEXT NOT NULL,
                action TEXT NOT NULL,
                module TEXT NOT NULL,
                object_id TEXT,
                before_json TEXT,
                after_json TEXT,
                ip TEXT,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS records(
                id INTEGER PRIMARY KEY,
                module TEXT NOT NULL,
                data TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS records_module_idx ON records(module,id);
            CREATE INDEX IF NOT EXISTS audit_actor_idx ON audit(actor_id,id);
            CREATE TABLE IF NOT EXISTS login_attempts(
                ip TEXT PRIMARY KEY,
                failures INTEGER NOT NULL,
                blocked_until INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS scan_preferences(
                field_key TEXT PRIMARY KEY,
                meaning TEXT NOT NULL
            );
            """
        )
        if db.execute("SELECT COUNT(*) FROM admins").fetchone()[0] == 0:
            password = os.environ.get("ADMIN_PASSWORD", "")
            if not password:
                if not sys.stdin.isatty():
                    raise RuntimeError(
                        "Set ADMIN_PASSWORD (12+ characters) before first startup."
                    )
                while True:
                    password = getpass.getpass("Create superadmin password (12+ chars): ")
                    if len(password) < 12:
                        print("Password must contain at least 12 characters.")
                        continue
                    if not hmac.compare_digest(
                        password, getpass.getpass("Confirm password: ")
                    ):
                        print("Passwords do not match.")
                        continue
                    break
            if len(password) < 12:
                raise RuntimeError("ADMIN_PASSWORD must contain at least 12 characters.")
            username = os.environ.get("ADMIN_USERNAME", "super")
            email = os.environ.get("ADMIN_EMAIL", "super@localhost")
            password_hash, salt = hash_password(password)
            cursor = db.execute(
                "INSERT INTO admins(username,email,password_hash,salt,role,permissions,status,created_at) "
                "VALUES(?,?,?,?,?,?,?,?)",
                (username, email, password_hash, salt, "super", safe_json(sorted(MODULES)),
                 "active", now()),
            )
            (LOG_DIR / f"admin-{cursor.lastrowid}.txt").parent.mkdir(parents=True, exist_ok=True)
            (LOG_DIR / f"admin-{cursor.lastrowid}.txt").touch(mode=0o600, exist_ok=True)
        if db.execute("SELECT COUNT(*) FROM records").fetchone()[0] == 0:
            seed(db)


def can_module(auth: dict, module: str) -> bool:
    if auth["role"] == "super":
        return module in MODULES
    return module in ADMIN_MODULES and module in auth["permissions"]


def require_module(auth: dict, module: str) -> None:
    if not can_module(auth, module):
        raise APIError(403, "forbidden", "Недостаточно прав для этого раздела.")
    if module == "profit" and auth["profit_until"] < int(time.time()):
        raise APIError(403, "profit_locked", "Для открытия раздела прибыли подтвердите пароль.")


def clean_value(value: object) -> object:
    if isinstance(value, str):
        if len(value) > 1_500_000:
            raise APIError(413, "field_too_large", "Слишком большое значение поля.")
        return value.strip()
    if isinstance(value, float) and not math.isfinite(value):
        raise APIError(400, "invalid_number", "Число должно быть конечным.")
    if isinstance(value, (bool, int, float)) or value is None:
        return value
    raise APIError(400, "invalid_field", "Недопустимый формат поля.")


class Handler(BaseHTTPRequestHandler):
    server_version = "Adminkatest/1.0"

    def log_message(self, fmt: str, *args: object) -> None:
        print(f"[{now()}] {self.address_string()} {fmt % args}")

    def end_headers(self) -> None:
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cache-Control", "no-store")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; style-src 'self'; "
            "img-src 'self' data: https:; connect-src 'self'; base-uri 'none'; "
            "frame-ancestors 'none'; form-action 'self'",
        )
        super().end_headers()

    def send_json(self, status: int, payload: dict, cookie: str | None = None) -> None:
        body = safe_json(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        if cookie:
            self.send_header("Set-Cookie", cookie)
        self.end_headers()
        self.wfile.write(body)

    def read_json(self) -> dict:
        try:
            size = int(self.headers.get("Content-Length", "0"))
        except ValueError as exc:
            raise APIError(400, "invalid_content_length") from exc
        if size < 0 or size > MAX_BODY:
            raise APIError(413, "request_too_large", "Размер запроса превышает лимит.")
        content_type = self.headers.get("Content-Type", "")
        if size and not content_type.lower().startswith("application/json"):
            raise APIError(415, "json_required")
        try:
            value = json.loads(self.rfile.read(size) or b"{}")
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise APIError(400, "invalid_json") from exc
        if not isinstance(value, dict):
            raise APIError(400, "object_required")
        return value

    def ip(self) -> str:
        return self.client_address[0]

    def cookie_header(self, sid: str, max_age: int = SESSION_MINUTES * 60) -> str:
        secure = "; Secure" if COOKIE_SECURE else ""
        return (
            f"admin_session={sid}; HttpOnly; SameSite=Strict; Path=/; "
            f"Max-Age={max_age}{secure}"
        )

    def authenticate(self) -> dict | None:
        sid = ""
        for part in self.headers.get("Cookie", "").split(";"):
            name, _, value = part.strip().partition("=")
            if name == "admin_session":
                sid = value
                break
        if not sid:
            return None
        stamp = int(time.time())
        with connect() as db:
            row = db.execute(
                "SELECT s.id,s.csrf,s.last_seen,s.profit_until,a.id admin_id,a.username,"
                "a.email,a.role,a.permissions,a.status FROM sessions s "
                "JOIN admins a ON a.id=s.admin_id WHERE s.id=?",
                (sid,),
            ).fetchone()
            if not row or row["status"] != "active":
                return None
            if stamp - row["last_seen"] > SESSION_MINUTES * 60:
                db.execute("DELETE FROM sessions WHERE id=?", (sid,))
                return None
            db.execute("UPDATE sessions SET last_seen=? WHERE id=?", (stamp, sid))
            return {
                "id": row["admin_id"],
                "username": row["username"],
                "email": row["email"],
                "role": row["role"],
                "permissions": json.loads(row["permissions"]),
                "csrf": row["csrf"],
                "sid": sid,
                "profit_until": row["profit_until"],
            }

    def require_auth(self, csrf: bool = False) -> dict:
        auth = self.authenticate()
        if not auth:
            raise APIError(401, "unauthorized", "Сессия завершена. Войдите снова.")
        if csrf and not hmac.compare_digest(
            self.headers.get("X-CSRF-Token", ""), auth["csrf"]
        ):
            raise APIError(403, "csrf", "Защита запроса не пройдена.")
        return auth

    def do_GET(self) -> None:
        try:
            path = unquote(urlparse(self.path).path)
            if path.startswith("/api/"):
                return self.handle_get_api(path)
            return self.serve_static(path)
        except APIError as exc:
            self.send_json(exc.status, {"error": exc.code, "message": exc.message})
        except (OSError, sqlite3.Error) as exc:
            print(f"[SERVER ERROR] {type(exc).__name__}: {exc}")
            self.send_json(500, {"error": "server_error", "message": "Внутренняя ошибка сервера."})

    def serve_static(self, path: str) -> None:
        if path == "/":
            path = "/index.html"
        requested = (ROOT / path.lstrip("/")).resolve()
        if ROOT not in requested.parents and requested != ROOT:
            raise APIError(404, "not_found")
        if requested.is_dir():
            requested = requested / "index.html"
        if requested.suffix not in {".html", ".css", ".js", ".svg", ".png", ".ico"}:
            raise APIError(404, "not_found")
        try:
            body = requested.read_bytes()
        except OSError:
            raise APIError(404, "not_found") from None
        content_types = {
            ".html": "text/html; charset=utf-8",
            ".css": "text/css; charset=utf-8",
            ".js": "text/javascript; charset=utf-8",
            ".svg": "image/svg+xml",
            ".png": "image/png",
            ".ico": "image/x-icon",
        }
        self.send_response(200)
        self.send_header("Content-Type", content_types[requested.suffix])
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def handle_get_api(self, path: str) -> None:
        if path == "/api/health":
            return self.send_json(200, {"ok": True, "version": "1.0.0"})
        if path == "/api/auth/me":
            auth = self.authenticate()
            if not auth:
                return self.send_json(401, {"error": "unauthorized"})
            return self.send_json(
                200,
                {
                    "admin": {key: auth[key] for key in ("id", "username", "email", "role")},
                    "csrf": auth["csrf"],
                    "permissions": auth["permissions"],
                },
            )
        if path.startswith("/api/admin-logs/"):
            auth = self.require_auth()
            if auth["role"] != "super":
                raise APIError(403, "forbidden")
            admin_id = path.rsplit("/", 1)[-1].removesuffix(".txt")
            if not admin_id.isdigit():
                raise APIError(400, "invalid_admin_id")
            with connect() as db:
                if not db.execute("SELECT 1 FROM admins WHERE id=?", (admin_id,)).fetchone():
                    raise APIError(404, "not_found")
            file_path = LOG_DIR / f"admin-{admin_id}.txt"
            body = file_path.read_bytes() if file_path.exists() else b""
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Disposition", f'attachment; filename="admin-{admin_id}.txt"')
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        auth = self.require_auth()
        parts = path.removeprefix("/api/").split("/")
        module = parts[0]
        if module not in MODULES:
            raise APIError(404, "not_found")
        require_module(auth, module)
        if module in {"users", "lots", "shops", "currencies", "newsletter"}:
            query = parse_qs(urlparse(self.path).query)
            return self.send_json(200, self.project_module_get(module, query, auth["role"]))
        if module == "project_data":
            if auth["role"] != "super":
                raise APIError(403, "forbidden", "Project Data is available to the owner account only.")
            query = parse_qs(urlparse(self.path).query)
            return self.send_json(200, self.project_data_get(query))
        if module in PRIMARY_DATABASES:
            query = parse_qs(urlparse(self.path).query)
            return self.send_json(200, self.primary_database_get(module, query))
        if module == "profit":
            return self.send_json(200, self.profit_summary())
        if module == "stats":
            return self.send_json(200, {"items": self.statistics(), "upd": now()})
        if module == "scan":
            return self.send_json(200, self.scan_schema())
        if module == "bulk":
            return self.send_json(200, {"operations": self.bulk_operations()})
        if module == "assistant":
            return self.send_json(200, {"ok": True})
        if module == "admins":
            query = parse_qs(urlparse(self.path).query)
            items = self.list_admins()
            search = (query.get("q") or [""])[0].strip().lower()
            if search:
                items = [
                    item for item in items
                    if search in f"{item['login']} {item['email']}".lower()
                ]
            role = (query.get("f.role") or [""])[0]
            if role:
                items = [item for item in items if item["role"] == role]
            return self.send_json(200, {
                "items": items, "page": 1, "limit": PAGE_SIZE,
                "total": len(items), "fields": FIELDS["admins"],
            })
        if module == "audit":
            query = parse_qs(urlparse(self.path).query)
            admin_id = (query.get("admin_id") or [""])[0]
            return self.send_json(200, self.list_audit(query, admin_id))
        if module == "users" and len(parts) == 2:
            return self.send_json(200, self.user_detail(parts[1]))
        query = parse_qs(urlparse(self.path).query)
        return self.send_json(200, self.list_records(module, query))

    @staticmethod
    def _primary_db_spec(module: str) -> tuple[Path, str]:
        spec = PRIMARY_DATABASES.get(module)
        if not spec:
            raise APIError(404, "database_module_not_found")
        base = PRIMARY_DB_DIR.resolve()
        path = (base / spec["file"]).resolve()
        if base not in path.parents or not path.is_file():
            raise APIError(503, "primary_database_missing",
                           f"Не найдена основная база {spec['file']} в каталоге {base}.")
        return path, spec["table"]

    @staticmethod
    def _primary_db_schema(db: sqlite3.Connection, table: str) -> tuple[list[dict], str]:
        quoted = '"' + table.replace('"', '""') + '"'
        columns = [dict(row) for row in db.execute(f"PRAGMA table_info({quoted})")]
        if not columns:
            raise APIError(404, "primary_database_table_missing")
        primary = next((col["name"] for col in columns if col["pk"]), "")
        if not primary:
            raise APIError(400, "primary_database_primary_key_required")
        return columns, primary

    @staticmethod
    def _primary_db_value(column: dict, value: object) -> object:
        # Proofs are stored as BLOBs (some legacy rows contain text data URIs).
        if column["name"] == "proof":
            if value in (None, "", b"", "none"):
                return "[Вложение отсутствует]"
            size = len(value) if isinstance(value, (bytes, bytearray)) else len(str(value))
            return f"[Вложение · {size} байт]"
        if isinstance(value, bytes):
            return f"[BLOB · {len(value)} байт]"
        return value

    def primary_database_get(self, module: str, query: dict) -> dict:
        db_path, table = self._primary_db_spec(module)
        try:
            page = max(1, min(100000, int((query.get("page") or ["1"])[0])))
        except ValueError as exc:
            raise APIError(400, "invalid_pagination") from exc
        search = (query.get("q") or [""])[0].strip().casefold()
        all_rows = (query.get("all") or [""])[0] == "1"
        limit = 1000 if all_rows else PAGE_SIZE
        offset = 0 if all_rows else (page - 1) * PAGE_SIZE
        quoted = '"' + table.replace('"', '""') + '"'
        with sqlite3.connect(db_path, timeout=15) as db:
            db.row_factory = sqlite3.Row
            columns, primary = self._primary_db_schema(db, table)
            searchable = [c["name"] for c in columns
                          if "BLOB" not in str(c["type"]).upper() and c["name"] != "proof"]
            where, params = "", []
            if search and searchable:
                where = " WHERE " + " OR ".join(
                    f'lower(CAST("{name.replace(chr(34), chr(34)*2)}" AS TEXT)) LIKE ?'
                    for name in searchable
                )
                params = [f"%{search}%"] * len(searchable)
            total = db.execute(f"SELECT COUNT(*) FROM {quoted}{where}", params).fetchone()[0]
            rows = db.execute(
                f'SELECT * FROM {quoted}{where} ORDER BY "{primary}" DESC LIMIT ? OFFSET ?',
                (*params, limit, offset),
            ).fetchall()
            items = [
                {col["name"]: self._primary_db_value(col, row[col["name"]]) for col in columns}
                for row in rows
            ]
        db.close()
        return {"items": items, "page": page, "limit": limit, "total": total,
                "pages": max(1, math.ceil(total / limit))}


    def project_module_get(self, module: str, query: dict, role: str) -> dict:
        db_path = (PRIMARY_DB_DIR / "project_data.db").resolve()
        if PRIMARY_DB_DIR.resolve() not in db_path.parents or not db_path.is_file():
            raise APIError(503, "project_data_missing", "Missing db/project_data.db.")
        page = max(1, min(100000, int((query.get("page") or ["1"])[0])))
        search = (query.get("q") or [""])[0].strip().casefold()
        limit = 1000 if (query.get("all") or [""])[0] == "1" else PAGE_SIZE
        offset = 0 if limit == 1000 else (page - 1) * PAGE_SIZE
        with closing(sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True, timeout=15)) as db:
            db.row_factory = sqlite3.Row
            if module == "users":
                cols = [r[1] for r in db.execute('PRAGMA table_info("users")')]
                hidden = {"password", "login_token", "registration_token", "last_ip", "last_ip_date", "user_device_data", "email", "mobile", "adress", "post_index", "birthday", "patronymic"}
                visible = [c for c in cols if role == "super" or c not in hidden]
                where, params = "", []
                if search:
                    terms = [c for c in ("id", "name", "surname", "email", "mobile", "user_shop_name") if c in visible]
                    where = " WHERE " + " OR ".join(f'CAST("{c}" AS TEXT) LIKE ?' for c in terms)
                    params = [f"%{search}%"] * len(terms)
                total = db.execute(f"SELECT COUNT(*) FROM users{where}", params).fetchone()[0]
                rows = db.execute(f'SELECT {",".join(chr(34)+c+chr(34) for c in visible)} FROM users{where} ORDER BY id DESC LIMIT ? OFFSET ?', (*params, limit, offset)).fetchall()
                return {"items": [dict(r) for r in rows], "columns": visible, "page": page, "limit": limit, "total": total, "pages": max(1, math.ceil(total/limit))}
            if module == "shops":
                cols = ["id", "name", "surname", "user_shop_name", "shop_description", "shop_avatar", "shop_banner", "shop_verification", "shop_podcategory"]
                if role == "super": cols += ["email", "last_payment_for_shop"]
                where, params = ' WHERE lower(trim(COALESCE(user_shop_name, ""))) NOT IN ("", "none", "null")', []
                if search:
                    where += " AND (lower(user_shop_name) LIKE ? OR lower(name) LIKE ? OR CAST(id AS TEXT) LIKE ?)"
                    params = [f"%{search}%"] * 3
                total = db.execute(f"SELECT COUNT(*) FROM users{where}", params).fetchone()[0]
                rows = db.execute(f'SELECT {",".join(chr(34)+c+chr(34) for c in cols)} FROM users{where} ORDER BY id DESC LIMIT ? OFFSET ?', (*params, limit, offset)).fetchall()
                return {"items": [dict(r) for r in rows], "columns": cols, "page": page, "limit": limit, "total": total, "pages": max(1, math.ceil(total/limit))}
            if module == "lots":
                names = [r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '%_category' ORDER BY name")]
                chosen = (query.get("category") or [""])[0]
                if chosen and chosen not in names: raise APIError(400, "invalid_category")
                selected = [chosen] if chosen else names
                parts, params = [], []
                for name in selected:
                    parts.append('SELECT *, ? AS source_category FROM "' + name.replace('"','""') + '"')
                    params.append(name)
                union = " UNION ALL ".join(parts)
                searchable = ["lot_name", "seller_id\t", "lot_category", "lot_podcategory", "lot_description", "current_lot_status"]
                where, search_params = "", []
                if search:
                    where = " WHERE " + " OR ".join(f'lower(CAST("{c}" AS TEXT)) LIKE ?' for c in searchable)
                    search_params = [f"%{search}%"] * len(searchable)
                total = db.execute(f"SELECT COUNT(*) FROM ({union}){where}", (*params, *search_params)).fetchone()[0]
                rows = db.execute(f"SELECT * FROM ({union}){where} ORDER BY id DESC LIMIT ? OFFSET ?", (*params, *search_params, limit, offset)).fetchall()
                cols = ["id", "lot_name", "seller_id", "lot_category", "lot_podcategory", "lot_start_price", "current_price", "current_lot_status", "category_table"]
                if role == "super": cols += ["lot_delivery_track_number", "user_seller_chat_token", "dispute_user_description", "dispute_seller_description"]
                items = []
                for row in rows:
                    d = dict(row); d["category_table"] = d.pop("source_category", ""); d["seller_id"] = d.pop("seller_id\t", d.get("seller_id"))
                    items.append({k:v for k,v in d.items() if k in cols})
                return {"items": items, "columns": cols, "categories": [{"name": n, "count": db.execute('SELECT COUNT(*) FROM "'+n+'"').fetchone()[0]} for n in names], "page": page, "limit": limit, "total": total, "pages": max(1, math.ceil(total/limit))}
            if module == "currencies":
                row = db.execute('SELECT * FROM currency_converter LIMIT 1').fetchone()
                names = [c[1] for c in db.execute('PRAGMA table_info("currency_converter")')]
                items = [{"code": n.upper(), "rate": row[n], "updated": "project_data.db"} for n in names] if row else []
                if search: items = [x for x in items if search in x["code"].lower()]
                return {"items": items, "columns": ["code", "rate", "updated"], "page": 1, "limit": limit, "total": len(items), "pages": 1}
            if module == "newsletter":
                where, params = (" WHERE lower(mail) LIKE ?", [f"%{search}%"]) if search else ("", [])
                total = db.execute(f"SELECT COUNT(*) FROM spam_emails{where}", params).fetchone()[0]
                rows = db.execute(f'SELECT id, mail AS email, date AS joined, "spam" AS status FROM spam_emails{where} ORDER BY id DESC LIMIT ? OFFSET ?', (*params, limit, offset)).fetchall()
                return {"items": [dict(r) for r in rows], "columns": ["id", "email", "status", "joined"], "page": page, "limit": limit, "total": total, "pages": max(1, math.ceil(total/limit))}
        raise APIError(404, "not_found")

    def project_data_get(self, query: dict) -> dict:
        db_path = (PRIMARY_DB_DIR / "project_data.db").resolve()
        if PRIMARY_DB_DIR.resolve() not in db_path.parents or not db_path.is_file():
            raise APIError(503, "project_data_missing", "Missing db/project_data.db.")
        with closing(sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True, timeout=15)) as db:
            db.row_factory = sqlite3.Row
            tables = [row[0] for row in db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
            ).fetchall()]
            selected = (query.get("table") or [""])[0]
            if not selected:
                return {"tables": [{"name": name, "count": db.execute(
                    'SELECT COUNT(*) FROM "' + name.replace('"', '""') + '"'
                ).fetchone()[0]} for name in tables]}
            if selected not in tables:
                raise APIError(404, "project_data_table_not_found")
            quoted = '"' + selected.replace('"', '""') + '"'
            columns = [dict(row) for row in db.execute(f"PRAGMA table_info({quoted})")]
            try:
                page = max(1, min(100000, int((query.get("page") or ["1"])[0])))
            except ValueError as exc:
                raise APIError(400, "invalid_pagination") from exc
            search = (query.get("q") or [""])[0].strip().casefold()
            searchable = [c["name"] for c in columns if "BLOB" not in str(c["type"]).upper()]
            where, params = "", []
            if search and searchable:
                where = " WHERE " + " OR ".join(
                    'lower(CAST("' + name.replace('"', '""') + '" AS TEXT)) LIKE ?'
                    for name in searchable
                )
                params = [f"%{search}%"] * len(searchable)
            total = db.execute(f"SELECT COUNT(*) FROM {quoted}{where}", params).fetchone()[0]
            rows = db.execute(f"SELECT * FROM {quoted}{where} LIMIT ? OFFSET ?",
                              (*params, PAGE_SIZE, (page - 1) * PAGE_SIZE)).fetchall()
            items = []
            for row in rows:
                item = {}
                for col in columns:
                    value = row[col["name"]]
                    if isinstance(value, bytes):
                        value = f"[BLOB {len(value)} bytes]"
                    item[col["name"]] = value
                items.append(item)
        return {"tables": [{"name": name} for name in tables], "table": selected,
                "columns": [c["name"] for c in columns], "items": items,
                "page": page, "limit": PAGE_SIZE, "total": total,
                "pages": max(1, math.ceil(total / PAGE_SIZE))}

    def backup_primary_database(self, module: str, db_path: Path) -> None:
        backup_dir = DATA_DIR / "primary-database-backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        day = time.strftime("%Y%m%d", time.localtime())
        backup_path = backup_dir / f"{module}-{day}.db"
        if backup_path.exists():
            return
        temporary = backup_path.with_suffix(".db.tmp")
        try:
            source = sqlite3.connect(db_path, timeout=15)
            target = sqlite3.connect(temporary, timeout=15)
            try:
                source.backup(target)
            finally:
                target.close()
                source.close()
            temporary.replace(backup_path)
        finally:
            if temporary.exists():
                temporary.unlink()

    def primary_database_write(self, module: str, data: dict, auth: dict) -> None:
        db_path, table = self._primary_db_spec(module)
        self.backup_primary_database(module, db_path)
        quoted = '"' + table.replace('"', '""') + '"'
        item_id = data.get("id")
        if item_id is not None and (isinstance(item_id, bool) or not str(item_id).isdigit()):
            raise APIError(400, "invalid_record_id")
        with sqlite3.connect(db_path, timeout=15) as db:
            db.row_factory = sqlite3.Row
            columns, primary = self._primary_db_schema(db, table)
            by_name = {c["name"]: c for c in columns}
            changes = {}
            for key, value in data.items():
                if key not in by_name or key == primary:
                    continue
                column = by_name[key]
                if key == "proof" or "BLOB" in str(column["type"]).upper():
                    if not isinstance(value, str):
                        raise APIError(400, "invalid_blob")
                    try:
                        changes[key] = base64.b64decode(value, validate=True)
                    except (ValueError, base64.binascii.Error) as exc:
                        raise APIError(400, "invalid_blob") from exc
                else:
                    changes[key] = clean_value(value)
            if not changes:
                raise APIError(400, "empty_record")
            if item_id is None:
                missing = [
                    col["name"] for col in columns
                    if col["notnull"] and col["dflt_value"] is None and not col["pk"]
                    and (col["name"] not in changes or changes[col["name"]] in (None, ""))
                ]
                if missing:
                    raise APIError(400, "required_fields",
                                   "Заполните обязательные поля: " + ", ".join(missing))
            if item_id is not None:
                before_row = db.execute(
                    f'SELECT * FROM {quoted} WHERE "{primary}"=?', (item_id,)
                ).fetchone()
                if not before_row:
                    raise APIError(404, "not_found")
                before = {k: self._primary_db_value(by_name[k], v)
                          for k, v in dict(before_row).items()}
                assignments = ", ".join('"' + k.replace('"', '""') + '"=?' for k in changes)
                db.execute(f'UPDATE {quoted} SET {assignments} WHERE "{primary}"=?',
                           (*changes.values(), item_id))
                object_id, action = str(item_id), "update"
            else:
                names = list(changes)
                quoted_names = ", ".join('"' + k.replace('"', '""') + '"' for k in names)
                marks = ", ".join("?" for _ in names)
                cursor = db.execute(f"INSERT INTO {quoted} ({quoted_names}) VALUES ({marks})",
                                    list(changes.values()))
                object_id, action, before = str(cursor.lastrowid), "create", None
            after_row = db.execute(
                f'SELECT * FROM {quoted} WHERE "{primary}"=?', (object_id,)
            ).fetchone()
            after = {k: self._primary_db_value(by_name[k], v)
                     for k, v in dict(after_row).items()}
        db.close()
        with connect() as audit_db:
            audit(audit_db, auth["id"], auth["username"], action,
                  module, object_id, before, after, self.ip())
        self.send_json(200, {"item": after})

    def primary_database_delete(self, module: str, raw_id: str, auth: dict) -> None:
        db_path, table = self._primary_db_spec(module)
        self.backup_primary_database(module, db_path)
        quoted = '"' + table.replace('"', '""') + '"'
        with sqlite3.connect(db_path, timeout=15) as db:
            db.row_factory = sqlite3.Row
            columns, primary = self._primary_db_schema(db, table)
            by_name = {c["name"]: c for c in columns}
            row = db.execute(f'SELECT * FROM {quoted} WHERE "{primary}"=?',
                             (int(raw_id),)).fetchone()
            if not row:
                raise APIError(404, "not_found")
            before = {k: self._primary_db_value(by_name[k], v)
                      for k, v in dict(row).items()}
            db.execute(f'DELETE FROM {quoted} WHERE "{primary}"=?', (int(raw_id),))
        db.close()
        with connect() as audit_db:
            audit(audit_db, auth["id"], auth["username"], "delete",
                  module, raw_id, before, None, self.ip())
        self.send_json(200, {"ok": True})

    def list_admins(self) -> list[dict]:
        with connect() as db:
            rows = db.execute(
                "SELECT id,username,email,role,status,permissions FROM admins ORDER BY id"
            ).fetchall()
        return [
            {
                "id": row["id"], "login": row["username"], "email": row["email"],
                "role": row["role"], "status": row["status"],
                "sections": ",".join(json.loads(row["permissions"])),
            }
            for row in rows
        ]

    def list_audit(self, query: dict, admin_id: str) -> dict:
        try:
            page = max(1, min(100000, int((query.get("page") or ["1"])[0])))
        except ValueError as exc:
            raise APIError(400, "invalid_pagination") from exc
        q = (query.get("q") or [""])[0].strip().lower()
        clauses, params = [], []
        if admin_id:
            clauses.append("actor_id=?")
            params.append(admin_id)
        if q:
            clauses.append("(lower(actor || ' ' || action || ' ' || module || ' ' || "
                           "COALESCE(object_id,'') || ' ' || COALESCE(after_json,'')) LIKE ?)")
            params.append(f"%{q}%")
        role = (query.get("f.admin") or [""])[0]
        if role:
            clauses.append("actor=?")
            params.append(role)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        with connect() as db:
            total = db.execute(f"SELECT COUNT(*) FROM audit{where}", params).fetchone()[0]
            rows = db.execute(
                f"SELECT id,actor,action,module,object_id,after_json,ip,created_at "
                f"FROM audit{where} ORDER BY id DESC LIMIT ? OFFSET ?",
                (*params, PAGE_SIZE, (page - 1) * PAGE_SIZE),
            ).fetchall()
        items = []
        for row in rows:
            details = json.loads(row["after_json"]) if row["after_json"] else {}
            items.append(
                {
                    "id": row["id"], "admin": row["actor"], "action": row["action"],
                    "detail": safe_json(details), "time": row["created_at"],
                    "module": row["module"], "object_id": row["object_id"], "ip": row["ip"],
                }
            )
        return {"items": items, "page": page, "limit": PAGE_SIZE, "total": total}

    def list_records(self, module: str, query: dict) -> dict:
        try:
            page = max(1, min(100000, int((query.get("page") or ["1"])[0])))
        except ValueError as exc:
            raise APIError(400, "invalid_pagination") from exc
        search = (query.get("q") or [""])[0].strip().casefold()
        search_field = (query.get("field") or [""])[0]
        if module == "users":
            search_field = USER_FIELDS.get(search_field, search_field)
        allowed_fields = set(FIELDS.get(module, []))
        if search_field and search_field not in allowed_fields and not (
            module == "users" and search_field == "shop"
        ):
            raise APIError(400, "invalid_search_field")
        clauses = ["module=?"]
        params: list[object] = [module]
        if search:
            if module == "users" and search_field == "shop":
                clauses.append(
                    "EXISTS (SELECT 1 FROM records shops WHERE shops.module='shops' "
                    "AND casefold(json_extract(shops.data,'$.owner'))=casefold(json_extract(records.data,'$.nick')) "
                    "AND casefold(json_extract(shops.data,'$.name')) LIKE ?)"
                )
                params.append(f"%{search}%")
            elif search_field == "id":
                if not search.isdigit():
                    return {"items": [], "page": page, "limit": PAGE_SIZE, "total": 0, "fields": FIELDS[module]}
                clauses.append("id=?")
                params.append(int(search))
            elif search_field:
                clauses.append("casefold(json_extract(data, ?)) LIKE ?")
                params.extend([f"$.{search_field}", f"%{search}%"])
            else:
                clauses.append("casefold(data) LIKE ?")
                params.append(f"%{search}%")
        for key, values in query.items():
            if not key.startswith("f.") or not values or not values[0]:
                continue
            field = key[2:]
            if field not in allowed_fields:
                raise APIError(400, "invalid_filter")
            if field == "fake" and values[0].lower() in {"true", "false"}:
                clauses.append("json_extract(data, ?)=?")
                params.extend([f"$.{field}", 1 if values[0].lower() == "true" else 0])
            else:
                clauses.append("lower(json_extract(data, ?))=lower(?)")
                params.extend([f"$.{field}", values[0]])
        date_from = (query.get("from") or [""])[0]
        date_field = (query.get("dk") or [""])[0]
        if date_from and date_field:
            if date_field not in allowed_fields:
                raise APIError(400, "invalid_date_field")
            clauses.append("json_extract(data, ?) >= ?")
            params.extend([f"$.{date_field}", date_from])
        where = " AND ".join(clauses)
        all_rows = (query.get("all") or [""])[0] == "1"
        limit = 1000 if all_rows else PAGE_SIZE
        offset = 0 if all_rows else (page - 1) * PAGE_SIZE
        with connect() as db:
            total = db.execute(f"SELECT COUNT(*) FROM records WHERE {where}", params).fetchone()[0]
            rows = db.execute(
                f"SELECT id,data,created_at,updated_at FROM records WHERE {where} "
                "ORDER BY id DESC LIMIT ? OFFSET ?", (*params, limit, offset),
            ).fetchall()
        items = [
            {
                "id": row["id"], **json.loads(row["data"]),
                "created_at": row["created_at"], "updated_at": row["updated_at"],
            }
            for row in rows
        ]
        return {
            "items": items, "page": page, "limit": limit, "total": total,
            "fields": FIELDS.get(module, []),
        }

    def user_detail(self, raw_id: str) -> dict:
        if not raw_id.isdigit():
            raise APIError(400, "invalid_user_id")
        with connect() as db:
            user_row = db.execute(
                "SELECT id,data FROM records WHERE module='users' AND id=?", (int(raw_id),)
            ).fetchone()
            if not user_row:
                raise APIError(404, "not_found")
            user = {"id": user_row["id"], **json.loads(user_row["data"])}
            nick = str(user.get("nick", "")).strip()
            details: dict[str, object] = {"lots": 0, "shops": 0, "complaints": 0, "support": 0}
            for module, key in (("lots", "seller"), ("shops", "owner")):
                rows = db.execute("SELECT data FROM records WHERE module=?", (module,)).fetchall()
                details[module] = sum(
                    1 for row in rows
                    if nick and nick.casefold() in str(json.loads(row["data"]).get(key, "")).casefold()
                )
        for module in ("support", "complaints"):
            db_path, table = self._primary_db_spec(module)
            with sqlite3.connect(db_path, timeout=15) as source:
                details[module] = source.execute(
                    f'SELECT COUNT(*) FROM "{table}" WHERE CAST(user_id AS TEXT)=? '
                    'OR lower(user_name)=lower(?)',
                    (str(user["id"]), nick),
                ).fetchone()[0]
        return {"user": user, "activity": details}

    def statistics(self) -> list[list[object]]:
        today = time.strftime("%Y-%m-%d", time.localtime())
        tomorrow = time.strftime("%Y-%m-%d", time.localtime(time.time() + 86400))
        with connect() as db:
            all_rows: dict[str, list[dict]] = {}
            for module in ("users", "lots"):
                all_rows[module] = [
                    json.loads(row["data"])
                    for row in db.execute("SELECT data FROM records WHERE module=?", (module,))
                ]
        users, lots = all_rows["users"], all_rows["lots"]
        count_today = lambda rows, field: sum(
            1 for row in rows if str(row.get(field, "")).startswith(today)
        )
        auctions_today = [row for row in lots if str(row.get("auction_date", "")).startswith(today)]
        auctions_tomorrow = [row for row in lots if str(row.get("auction_date", "")).startswith(tomorrow)]
        return [
            ["Пользователей", len(users)],
            ["Фейковых пользователей", sum(bool(row.get("fake")) for row in users)],
            ["Заходили сегодня", count_today(users, "last_login")],
            ["Лотов", len(lots)],
            ["Фейковых лотов", sum(bool(row.get("fake")) for row in lots)],
            ["Аукционов сегодня", len(auctions_today)],
            ["Фейковых аукционов сегодня", sum(bool(row.get("fake")) for row in auctions_today)],
            ["Аукционов завтра", len(auctions_tomorrow)],
            ["Фейковых аукционов завтра", sum(bool(row.get("fake")) for row in auctions_tomorrow)],
        ]

    def profit_summary(self) -> dict:
        placement_names = {
            "category": "Баннеры в категориях",
            "header": "Баннеры в хедерах",
            "category_header": "Хедеры категорий",
            "footer": "Баннеры в футерах",
            "home_carousel": "Оплаченные баннеры в карусели главной",
            "home_current": "Оплаченные баннеры в актуальном",
            "mobile_super": "Оплаченные плитки супер-главной (мобильная)",
        }
        counts = {key: {"total": 0, "paid": 0} for key in placement_names}
        with connect() as db:
            rows = db.execute(
                "SELECT data FROM records WHERE module='banners'"
            ).fetchall()
        for row in rows:
            banner = json.loads(row["data"])
            place = banner.get("place")
            if place not in counts or not banner.get("active", True):
                continue
            counts[place]["total"] += 1
            if banner.get("paid"):
                counts[place]["paid"] += 1
        breakdown = [
            {
                "title": title,
                "total": counts[key]["total"],
                "paid": counts[key]["paid"],
                "today_revenue": 0,
            }
            for key, title in placement_names.items()
        ]
        return {
            "total": 0,
            "rows": [],
            "today_revenue": 0,
            "lot_turnover": 0,
            "lot_profit": 0,
            "free_money": 0,
            "banners": breakdown,
        }

    def scan_schema(self) -> dict:
        tables = {}
        with connect() as db:
            for module in ("users", "lots", "shops", "news", "support", "complaints"):
                if module in PRIMARY_DATABASES:
                    db_path, table = self._primary_db_spec(module)
                    source = sqlite3.connect(db_path)
                    try:
                        tables[module] = [
                            row[1] for row in source.execute(f'PRAGMA table_info("{table}")')
                        ]
                    finally:
                        source.close()
                else:
                    row = db.execute(
                        "SELECT data FROM records WHERE module=? LIMIT 1", (module,)
                    ).fetchone()
                    tables[module] = sorted(json.loads(row["data"]).keys()) if row else []
            saved = {
                row["field_key"]: row["meaning"]
                for row in db.execute("SELECT field_key,meaning FROM scan_preferences")
            }
        return {"tables": tables, "saved": saved}

    def bulk_operations(self) -> list[dict]:
        specifications = [
            ("remove_fake_lots", "Удалить фейковые лоты", "lots", "fake"),
            ("restore_hidden_lots", "Вернуть скрытые лоты", "lots", "hidden"),
        ]
        result = []
        with connect() as db:
            for operation, title, module, criterion in specifications:
                rows = db.execute("SELECT data FROM records WHERE module=?", (module,))
                if criterion == "fake":
                    count = sum(bool(json.loads(row["data"]).get("fake")) for row in rows)
                else:
                    target = {"hidden": "hidden", "open": "new", "new": "new"}[criterion]
                    count = sum(json.loads(row["data"]).get("status") == target for row in rows)
                result.append({"id": operation, "t": title, "n": count})
        return result

    def do_POST(self) -> None:
        try:
            data = self.read_json()
            path = urlparse(self.path).path
            if path == "/api/auth/login":
                return self.login(data)
            if path == "/api/auth/verify":
                return self.verify(data)
            auth = self.require_auth(csrf=True)
            if path == "/api/auth/logout":
                with connect() as db:
                    db.execute("DELETE FROM sessions WHERE id=?", (auth["sid"],))
                    audit(db, auth["id"], auth["username"], "logout", "auth", ip=self.ip())
                return self.send_json(200, {"ok": True}, self.cookie_header("", 0))
            if path == "/api/auth/reauth":
                return self.reauthenticate(data, auth)
            if path == "/api/newsletter/send":
                require_module(auth, "newsletter")
                return self.send_newsletter(data, auth)
            if path == "/api/scan":
                require_module(auth, "scan")
                mapping = data.get("mapping", {})
                if not isinstance(mapping, dict) or len(mapping) > 2000:
                    raise APIError(400, "invalid_mapping")
                with connect() as db:
                    for field_key, meaning in mapping.items():
                        if not isinstance(field_key, str) or not isinstance(meaning, str):
                            raise APIError(400, "invalid_mapping")
                        db.execute(
                            "INSERT INTO scan_preferences(field_key,meaning) VALUES(?,?) "
                            "ON CONFLICT(field_key) DO UPDATE SET meaning=excluded.meaning",
                            (field_key[:300], meaning[:100]),
                        )
                    audit(db, auth["id"], auth["username"], "scan_mapping_saved", "scan",
                          after={"fields": len(mapping)}, ip=self.ip())
                return self.send_json(200, {"ok": True})
            if path == "/api/bulk":
                require_module(auth, "bulk")
                return self.run_bulk(data, auth)
            parts = path.removeprefix("/api/").split("/")
            module = parts[0]
            if module not in MODULES:
                raise APIError(404, "not_found")
            require_module(auth, module)
            if module in PRIMARY_DATABASES:
                return self.primary_database_write(module, data, auth)
            if module == "admins":
                return self.admin_write(data, auth)
            if module == "assistant":
                return self.assistant_answer(data)
            if len(parts) == 3 and parts[2] == "actions":
                return self.record_action(module, parts[1], data, auth)
            return self.record_write(module, data, auth)
        except APIError as exc:
            self.send_json(exc.status, {"error": exc.code, "message": exc.message})
        except sqlite3.IntegrityError as exc:
            print(f"[DATA CONFLICT] {exc}")
            self.send_json(409, {"error": "conflict", "message": "Запись с таким логином или email уже существует."})
        except ValueError as exc:
            self.send_json(400, {"error": "invalid_input", "message": str(exc) or "Некорректные данные."})
        except (OSError, sqlite3.Error, smtplib.SMTPException) as exc:
            print(f"[SERVER ERROR] {type(exc).__name__}: {exc}")
            self.send_json(500, {"error": "server_error", "message": "Не удалось выполнить операцию."})

    def login(self, data: dict) -> None:
        ip = self.ip()
        username = str(data.get("username", ""))[:200]
        password = str(data.get("password", ""))[:1024]
        valid = False
        with connect() as db:
            attempt = db.execute("SELECT * FROM login_attempts WHERE ip=?", (ip,)).fetchone()
            stamp = int(time.time())
            if attempt and attempt["blocked_until"] > stamp:
                raise APIError(429, "temporarily_blocked", "Слишком много попыток. Попробуйте позже.")
            row = db.execute(
                "SELECT * FROM admins WHERE username=? AND status='active'", (username,)
            ).fetchone()
            valid = row is not None and password_matches(
                password, row["salt"], row["password_hash"]
            )
            if not valid:
                failures = attempt["failures"] + 1 if attempt else 1
                blocked = stamp + 900 if failures >= 5 else 0
                db.execute(
                    "INSERT INTO login_attempts(ip,failures,blocked_until) VALUES(?,?,?) "
                    "ON CONFLICT(ip) DO UPDATE SET failures=excluded.failures,blocked_until=excluded.blocked_until",
                    (ip, failures, blocked),
                )
                audit(db, None, username or "unknown", "login_failed", "auth", ip=ip)
            else:
                db.execute("DELETE FROM login_attempts WHERE ip=?", (ip,))
                code = f"{secrets.randbelow(1_000_000):06d}"
                code_hash = hashlib.sha256((row["salt"] + code).encode()).hexdigest()
                db.execute("DELETE FROM otp_codes WHERE admin_id=?", (row["id"],))
                db.execute(
                    "INSERT INTO otp_codes(admin_id,code_hash,expires) VALUES(?,?,?)",
                    (row["id"], code_hash, stamp + OTP_TTL),
                )
                audit(db, row["id"], row["username"], "password_verified", "auth", ip=ip)
                recipient_email = row["email"]
        if not valid:
            raise APIError(401, "invalid_credentials", "Неверный логин или пароль.")
        if APP_ENV == "development" and not os.environ.get("SMTP_HOST"):
            print(f"[DEV ONLY] OTP for {recipient_email}: {code}", flush=True)
            self.send_json(200, {"ok": True, "requires_otp": True, "message": "Код выведен в консоль сервера."})
            return
        try:
            self.send_otp(recipient_email, code)
        except (OSError, smtplib.SMTPException) as exc:
            print(f"[SMTP ERROR] {type(exc).__name__}: {exc}")
            raise APIError(503, "email_delivery_failed", "Не удалось отправить код подтверждения.") from exc
        self.send_json(200, {"ok": True, "requires_otp": True})

    def send_otp(self, email: str, code: str) -> None:
        host = os.environ.get("SMTP_HOST")
        if not host:
            raise APIError(503, "smtp_required", "SMTP не настроен.")
        message = EmailMessage()
        message["Subject"] = "Код входа в панель администрирования"
        message["From"] = os.environ.get("SMTP_FROM", os.environ.get("SMTP_USER", "admin@localhost"))
        message["To"] = email
        message.set_content(f"Код подтверждения: {code}. Срок действия — 10 минут.")
        port = int(os.environ.get("SMTP_PORT", "587"))
        if os.environ.get("SMTP_SSL") == "1":
            server = smtplib.SMTP_SSL(host, port, context=ssl.create_default_context(), timeout=10)
        else:
            server = smtplib.SMTP(host, port, timeout=10)
            server.starttls(context=ssl.create_default_context())
        with server:
            if os.environ.get("SMTP_USER"):
                server.login(os.environ["SMTP_USER"], os.environ.get("SMTP_PASSWORD", ""))
            server.send_message(message)

    def verify(self, data: dict) -> None:
        username = str(data.get("username", ""))[:200]
        code = str(data.get("code", ""))
        invalid = False
        with connect() as db:
            row = db.execute(
                "SELECT o.id otp_id,o.code_hash,o.expires,o.attempts,a.* FROM otp_codes o "
                "JOIN admins a ON a.id=o.admin_id WHERE a.username=? AND a.status='active' "
                "ORDER BY o.id DESC LIMIT 1",
                (username,),
            ).fetchone()
            expected = hashlib.sha256((row["salt"] + code).encode()).hexdigest() if row else ""
            if (
                not row or row["expires"] < int(time.time()) or row["attempts"] >= 5
                or not hmac.compare_digest(expected, row["code_hash"])
            ):
                if row:
                    if row["expires"] < int(time.time()) or row["attempts"] >= 4:
                        db.execute("DELETE FROM otp_codes WHERE id=?", (row["otp_id"],))
                    else:
                        db.execute("UPDATE otp_codes SET attempts=attempts+1 WHERE id=?", (row["otp_id"],))
                    audit(db, row["id"], username, "otp_failed", "auth", ip=self.ip())
                invalid = True
            else:
                db.execute("DELETE FROM otp_codes WHERE id=?", (row["otp_id"],))
                sid, csrf, stamp = secrets.token_urlsafe(32), secrets.token_urlsafe(32), int(time.time())
                db.execute(
                    "INSERT INTO sessions(id,admin_id,csrf,created_at,last_seen) VALUES(?,?,?,?,?)",
                    (sid, row["id"], csrf, stamp, stamp),
                )
                audit(db, row["id"], row["username"], "login_success", "auth", ip=self.ip())
                admin = {
                    "id": row["id"], "username": row["username"], "email": row["email"], "role": row["role"],
                }
                permissions = json.loads(row["permissions"])
        if invalid:
            raise APIError(401, "invalid_code", "Неверный или просроченный код.")
        self.send_json(
            200,
            {"ok": True, "admin": admin, "csrf": csrf, "permissions": permissions},
            self.cookie_header(sid),
        )

    def reauthenticate(self, data: dict, auth: dict) -> None:
        if auth["role"] != "super":
            raise APIError(403, "forbidden")
        with connect() as db:
            row = db.execute("SELECT password_hash,salt FROM admins WHERE id=?", (auth["id"],)).fetchone()
            password = str(data.get("password", ""))[:1024]
            if not row or not password_matches(password, row["salt"], row["password_hash"]):
                audit(db, auth["id"], auth["username"], "reauth_failed", "profit", ip=self.ip())
                valid = False
            else:
                valid = True
                unlocked_until = int(time.time()) + 300
                db.execute("UPDATE sessions SET profit_until=? WHERE id=?", (unlocked_until, auth["sid"]))
                audit(db, auth["id"], auth["username"], "reauth_success", "profit", ip=self.ip())
        if not valid:
            raise APIError(401, "invalid_credentials", "Неверный пароль.")
        self.send_json(200, {"ok": True, "expires_in": 300})

    def record_write(self, module: str, data: dict, auth: dict) -> None:
        if module in {"audit", "scan", "bulk", "assistant", "profit", "stats"}:
            raise APIError(405, "method_not_allowed")
        if module == "refunds":
            raise APIError(403, "disabled", "Раздел возвратов временно отключён.")
        item_id = data.get("id")
        allowed = set(FIELDS.get(module, [])) - {"id", "created_at", "updated_at"}
        changes = {key: clean_value(value) for key, value in data.items() if key in allowed}
        if not changes:
            raise APIError(400, "empty_record", "Нет полей для сохранения.")
        with connect() as db:
            if item_id:
                row = db.execute(
                    "SELECT * FROM records WHERE id=? AND module=?", (item_id, module)
                ).fetchone()
                if not row:
                    raise APIError(404, "not_found")
                before = json.loads(row["data"])
                merged = {**before, **changes}
                db.execute(
                    "UPDATE records SET data=?,updated_at=? WHERE id=?",
                    (safe_json(merged), now(), item_id),
                )
                action = "update"
            else:
                merged = changes
                cursor = db.execute(
                    "INSERT INTO records(module,data,created_at,updated_at) VALUES(?,?,?,?)",
                    (module, safe_json(merged), now(), now()),
                )
                item_id = cursor.lastrowid
                before = None
                action = "create"
            audit(
                db, auth["id"], auth["username"], action, module, item_id,
                before, merged, self.ip(),
            )
        self.send_json(200, {"item": {"id": item_id, **merged, "updated_at": now()}})

    def record_action(self, module: str, raw_id: str, data: dict, auth: dict) -> None:
        if module not in {"complaints", "support"} or not raw_id.isdigit():
            raise APIError(404, "not_found")
        action = str(data.get("action", ""))
        statuses = {"accept": "accepted", "reject": "rejected", "measure": "action",
                    "close": "closed", "in_work": "in_work"}
        if action not in statuses:
            raise APIError(400, "invalid_action")
        self.record_write(module, {"id": int(raw_id), "status": statuses[action]}, auth)

    def run_bulk(self, data: dict, auth: dict) -> None:
        operations = {item["id"]: item for item in self.bulk_operations()}
        operation = str(data.get("id", ""))
        if operation not in operations:
            raise APIError(400, "invalid_operation")
        specs = {
            "remove_fake_lots": ("lots", lambda row: bool(row.get("fake")), "delete"),
            "restore_hidden_lots": ("lots", lambda row: row.get("status") == "hidden", "update"),
        }
        module, matches, action = specs[operation]
        affected = 0
        with connect() as db:
            rows = db.execute("SELECT id,data FROM records WHERE module=?", (module,)).fetchall()
            for row in rows:
                before = json.loads(row["data"])
                if not matches(before):
                    continue
                if action == "delete":
                    db.execute("DELETE FROM records WHERE id=?", (row["id"],))
                    after = None
                else:
                    after = {**before, "status": "active" if action == "update" else ("closed" if action == "close" else "rejected")}
                    db.execute(
                        "UPDATE records SET data=?,updated_at=? WHERE id=?",
                        (safe_json(after), now(), row["id"]),
                    )
                audit(db, auth["id"], auth["username"], f"bulk_{action}", module, row["id"], before, after, self.ip())
                affected += 1
            audit(db, auth["id"], auth["username"], "bulk_complete", "bulk",
                  after={"operation": operation, "affected": affected}, ip=self.ip())
        self.send_json(200, {"ok": True, "affected": affected})

    def assistant_answer(self, data: dict) -> None:
        text = str(data.get("text", "")).lower()
        routes = [
            (r"пользоват|юзер", "users", "Пользователи"),
            (r"лот", "lots", "Лоты"),
            (r"магазин", "shops", "Магазины"),
            (r"новост", "news", "Новости"),
            (r"жалоб", "complaints", "Жалобы"),
            (r"саппорт|поддерж|обращен", "support", "Саппорт"),
            (r"баннер", "banners", "Баннеры"),
            (r"валют|курс", "currencies", "Курсы валют"),
            (r"прибыл", "profit", "Прибыль"),
            (r"статист", "stats", "Статистика"),
            (r"транзакц", "transactions", "Лог транзакций"),
            (r"подпис|рассыл", "newsletter", "Подписчики рассылки"),
            (r"администратор|админ", "admins", "Администраторы"),
            (r"журнал|лог", "audit", "Журнал действий"),
        ]
        for pattern, module, title in routes:
            if re.search(pattern, text):
                return self.send_json(200, {"go": module, "text": f"Откройте раздел «{title}»."})
        self.send_json(200, {"text": "Не удалось определить раздел. Укажите его название."})

    def admin_write(self, data: dict, auth: dict) -> None:
        if auth["role"] != "super":
            raise APIError(403, "forbidden")
        item_id = data.get("id")
        username = str(data.get("login", data.get("username", ""))).strip()[:100]
        email = str(data.get("email", "")).strip()[:254]
        role = str(data.get("role", "admin"))
        status = str(data.get("status", "active"))
        if role not in {"admin", "super"} or status not in {"active", "blocked"}:
            raise APIError(400, "invalid_admin")
        if item_id:
            with connect() as db:
                row = db.execute("SELECT * FROM admins WHERE id=?", (item_id,)).fetchone()
                if not row:
                    raise APIError(404, "not_found")
                if row["role"] == "super" and (role != "super" or status != "active"):
                    raise APIError(403, "owner_protected", "The owner account cannot be demoted or blocked.")
                if row["role"] == "admin" and role == "super":
                    raise APIError(403, "owner_only", "Only one super-admin owner is allowed.")
                before = {"login": row["username"], "email": row["email"], "role": row["role"], "status": row["status"]}
                updates = {}
                if username:
                    updates["username"] = username
                if email:
                    updates["email"] = email
                if "status" in data:
                    updates["status"] = status
                if "role" in data:
                    updates["role"] = role
                if role == "admin" and "sections" in data:
                    sections = [v for v in str(data["sections"]).split(",") if v in ADMIN_MODULES]
                    updates["permissions"] = safe_json(sections)
                if "password" in data and data["password"]:
                    password = str(data["password"])
                    if len(password) < 12:
                        raise APIError(400, "weak_password", "Пароль должен содержать минимум 12 символов.")
                    updates["password_hash"], updates["salt"] = hash_password(password)
                if not updates:
                    raise APIError(400, "empty_update")
                db.execute(
                    "UPDATE admins SET " + ",".join(f"{key}=?" for key in updates) + " WHERE id=?",
                    (*updates.values(), item_id),
                )
                after = {**before, **{key: value for key, value in updates.items() if key != "password_hash"}}
                audit(db, auth["id"], auth["username"], "update", "admins", item_id, before, after, self.ip())
            return self.send_json(200, {"ok": True})
        if not username or not email:
            raise APIError(400, "missing_fields", "Укажите логин и email.")
        if role == "super":
            raise APIError(403, "owner_only", "A second super-admin cannot be created.")
        password = str(data.get("password", ""))
        if len(password) < 12:
            raise APIError(400, "weak_password", "Пароль должен содержать минимум 12 символов.")
        sections = [v for v in str(data.get("sections", "")).split(",") if v in ADMIN_MODULES]
        if role == "super":
            sections = sorted(MODULES)
        password_hash, salt = hash_password(password)
        with connect() as db:
            cursor = db.execute(
                "INSERT INTO admins(username,email,password_hash,salt,role,permissions,status,created_at) "
                "VALUES(?,?,?,?,?,?,?,?)",
                (username, email, password_hash, salt, role, safe_json(sections), status, now()),
            )
            item_id = cursor.lastrowid
            (LOG_DIR / f"admin-{item_id}.txt").parent.mkdir(parents=True, exist_ok=True)
            (LOG_DIR / f"admin-{item_id}.txt").touch(mode=0o600, exist_ok=True)
            audit(
                db, auth["id"], auth["username"], "create", "admins", item_id, None,
                {"login": username, "email": email, "role": role, "status": status}, self.ip(),
            )
        self.send_json(200, {"item": {"id": item_id, "login": username, "email": email,
                                     "role": role, "status": status, "sections": ",".join(sections)}})

    def send_newsletter(self, data: dict, auth: dict) -> None:
        subject = str(data.get("subject", "")).strip()[:200]
        body = str(data.get("body", "")).strip()
        if not subject or not body:
            raise APIError(400, "missing_fields", "Укажите тему и текст письма.")
        if "\r" in subject or "\n" in subject:
            raise APIError(400, "invalid_subject", "Тема письма не должна содержать переносы строк.")
        smtp_host = os.environ.get("SMTP_HOST")
        if not smtp_host:
            raise APIError(503, "smtp_required", "Рассылка недоступна: SMTP не настроен.")
        with connect() as db:
            rows = db.execute(
                "SELECT id,data FROM records WHERE module='newsletter'"
            ).fetchall()
            recipients = [
                (row["id"], json.loads(row["data"]).get("email", ""))
                for row in rows
                if json.loads(row["data"]).get("status") == "active"
            ]
        if len(recipients) > 1000:
            raise APIError(413, "recipient_limit", "За одну отправку разрешено не более 1000 подписчиков.")
        from_address = os.environ.get("SMTP_FROM", os.environ.get("SMTP_USER", "admin@localhost"))
        port = int(os.environ.get("SMTP_PORT", "587"))
        if os.environ.get("SMTP_SSL") == "1":
            server = smtplib.SMTP_SSL(smtp_host, port, context=ssl.create_default_context(), timeout=15)
        else:
            server = smtplib.SMTP(smtp_host, port, timeout=15)
            server.starttls(context=ssl.create_default_context())
        sent = 0
        with server:
            if os.environ.get("SMTP_USER"):
                server.login(os.environ["SMTP_USER"], os.environ.get("SMTP_PASSWORD", ""))
            for _, email in recipients:
                if not email:
                    continue
                message = EmailMessage()
                message["Subject"] = subject
                message["From"] = from_address
                message["To"] = email
                message.set_content(body)
                server.send_message(message)
                sent += 1
        with connect() as db:
            audit(db, auth["id"], auth["username"], "newsletter_send", "newsletter",
                  after={"sent": sent, "subject": subject}, ip=self.ip())
        self.send_json(200, {"sent": sent})

    def do_DELETE(self) -> None:
        try:
            path = urlparse(self.path).path
            auth = self.require_auth(csrf=True)
            parts = path.removeprefix("/api/").split("/")
            if len(parts) != 2 or parts[0] not in MODULES or not parts[1].isdigit():
                raise APIError(404, "not_found")
            module, raw_id = parts
            require_module(auth, module)
            if module in PRIMARY_DATABASES:
                return self.primary_database_delete(module, raw_id, auth)
            if module in {"admins", "audit", "scan", "refunds"}:
                raise APIError(403, "disabled", "Удаление в этом разделе запрещено.")
            with connect() as db:
                row = db.execute(
                    "SELECT data FROM records WHERE id=? AND module=?", (raw_id, module)
                ).fetchone()
                if not row:
                    raise APIError(404, "not_found")
                before = json.loads(row["data"])
                db.execute("DELETE FROM records WHERE id=? AND module=?", (raw_id, module))
                audit(db, auth["id"], auth["username"], "delete", module, raw_id, before, None, self.ip())
            self.send_json(200, {"ok": True})
        except APIError as exc:
            self.send_json(exc.status, {"error": exc.code, "message": exc.message})
        except (OSError, sqlite3.Error) as exc:
            print(f"[SERVER ERROR] {type(exc).__name__}: {exc}")
            self.send_json(500, {"error": "server_error", "message": "Не удалось выполнить операцию."})


def main() -> None:
    init_db()
    print(f"Admin panel: http://{HOST}:{PORT}/admin/", flush=True)
    if HOST not in {"127.0.0.1", "localhost", "::1"}:
        print("WARNING: use HTTPS and COOKIE_SECURE=1 outside localhost.", flush=True)
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
