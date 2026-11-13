import base64
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

import app


class DummyHandler:
    _primary_db_spec = staticmethod(app.Handler._primary_db_spec)
    _primary_db_schema = staticmethod(app.Handler._primary_db_schema)
    _primary_db_value = staticmethod(app.Handler._primary_db_value)

    def __init__(self):
        self.result = None

    def send_json(self, status, payload, cookie=None):
        self.result = (status, payload)

    def ip(self):
        return "127.0.0.1"

    def backup_primary_database(self, module, path):
        return app.Handler.backup_primary_database(self, module, path)


class PrimaryDatabaseAdminTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db_dir = Path(self.temp.name)
        self._create_primary_databases()
        self.db_patch = patch.object(app, "PRIMARY_DB_DIR", self.db_dir)
        self.audit_patch = patch.object(app, "audit", lambda *args, **kwargs: None)
        self.data_patch = patch.object(app, "DATA_DIR", self.db_dir / "admin-data")
        self.db_patch.start()
        self.audit_patch.start()
        self.data_patch.start()
        self.addCleanup(self.db_patch.stop)
        self.addCleanup(self.audit_patch.stop)
        self.addCleanup(self.data_patch.stop)
        self.auth = {"id": 1, "username": "unit-test", "role": "admin"}

    def _create_primary_databases(self):
        db = sqlite3.connect(self.db_dir / "news.db")
        db.execute("""CREATE TABLE news (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cat TEXT NOT NULL DEFAULT 'update',
            badge TEXT NOT NULL DEFAULT '',
            title TEXT NOT NULL DEFAULT '',
            "desc" TEXT NOT NULL DEFAULT '',
            body TEXT NOT NULL DEFAULT '',
            img TEXT DEFAULT '',
            read_time TEXT DEFAULT '2 min',
            published TEXT NOT NULL,
            created_at INTEGER NOT NULL DEFAULT (strftime('%s','now'))
        )""")
        db.execute("INSERT INTO news(title,published) VALUES('Original headline','2026-01-01')")
        db.commit()
        db.close()

        db = sqlite3.connect(self.db_dir / "profile_support.db")
        db.execute("""CREATE TABLE support_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date_message TEXT NOT NULL DEFAULT 'none',
            header_message TEXT NOT NULL DEFAULT 'none',
            message TEXT NOT NULL DEFAULT 'none',
            priority TEXT NOT NULL DEFAULT 'none',
            proof BLOB NOT NULL DEFAULT 'none',
            user_id TEXT DEFAULT 'none',
            user_name TEXT DEFAULT 'none',
            user_mail TEXT DEFAULT 'none'
        )""")
        db.execute("""INSERT INTO support_messages
            (date_message,header_message,message,priority,user_id,user_name,user_mail)
            VALUES('2026-01-01','Original ticket','Original message','high','u1','User 1','u1@example.test')""")
        db.commit()
        db.close()

        db = sqlite3.connect(self.db_dir / "profile_yammer.db")
        db.execute("""CREATE TABLE yammer_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date_message TEXT NOT NULL DEFAULT 'none',
            reason TEXT NOT NULL DEFAULT 'none',
            message TEXT NOT NULL DEFAULT 'none',
            proof BLOB NOT NULL DEFAULT 'none',
            link_proof TEXT DEFAULT 'none',
            email_user TEXT DEFAULT 'none',
            user_id TEXT DEFAULT 'none',
            user_name TEXT DEFAULT 'none'
        )""")
        db.execute("""INSERT INTO yammer_messages
            (date_message,reason,message,link_proof,email_user,user_id,user_name)
            VALUES('2026-01-01','Original reason','Original report','https://example.test','u2@example.test','u2','User 2')""")
        db.commit()
        db.close()

    def call_get(self, module, query=""):
        handler = DummyHandler()
        parsed = urlparse("/api/" + module + query)
        return app.Handler.primary_database_get(handler, module, parse_qs(parsed.query))

    def test_existing_modules_use_the_original_schemas(self):
        expected = {
            "news": ("news", 10, 1),
            "support": ("support_messages", 9, 1),
            "complaints": ("yammer_messages", 9, 1),
        }
        for module, (table, columns, rows) in expected.items():
            path, actual_table = app.Handler._primary_db_spec(module)
            self.assertEqual(actual_table, table)
            db = sqlite3.connect(path)
            try:
                self.assertEqual(len(db.execute(f'PRAGMA table_info("{table}")').fetchall()), columns)
            finally:
                db.close()
            self.assertEqual(self.call_get(module)["total"], rows)
            all_rows = self.call_get(module, "?all=1")
            self.assertEqual(len(all_rows["items"]), rows)
            self.assertEqual(all_rows["limit"], 1000)

    def test_primary_module_crud_search_and_blob(self):
        cases = [
            ("news", {"title": "unit-test-value", "published": "2099-01-01"}),
            ("support", {
                "date_message": "2099-01-01", "header_message": "unit-test-value",
                "message": "A support ticket", "priority": "mid", "proof": base64.b64encode(b"attachment").decode(),
                "user_id": "u3", "user_name": "User 3", "user_mail": "u3@example.test",
            }),
            ("complaints", {
                "date_message": "2099-01-01", "reason": "unit-test-value",
                "message": "A report", "proof": base64.b64encode(b"attachment").decode(),
                "link_proof": "https://example.test", "email_user": "u4@example.test",
                "user_id": "u4", "user_name": "User 4",
            }),
        ]
        for module, values in cases:
            original = self.call_get(module)["items"][0]
            first_editable = next(k for k in values if k != "proof")
            update = DummyHandler()
            app.Handler.primary_database_write(
                update, module, {"id": original["id"], first_editable: original.get(first_editable, "updated")}, self.auth
            )
            self.assertEqual(update.result[0], 200)

            insert = DummyHandler()
            app.Handler.primary_database_write(insert, module, values, self.auth)
            self.assertEqual(insert.result[0], 200)
            new_id = insert.result[1]["item"]["id"]
            if "proof" in values:
                self.assertIn("Вложение", insert.result[1]["item"]["proof"])
                edit_attachment = DummyHandler()
                app.Handler.primary_database_write(
                    edit_attachment, module,
                    {"id": new_id, "message": "updated without replacing proof"}, self.auth
                )
                db_path, table = app.Handler._primary_db_spec(module)
                db = sqlite3.connect(db_path)
                try:
                    stored = db.execute(
                        f'SELECT proof FROM "{table}" WHERE id=?', (new_id,)
                    ).fetchone()[0]
                finally:
                    db.close()
                self.assertEqual(stored, b"attachment")

            self.assertGreaterEqual(self.call_get(module, "?q=unit-test-value")["total"], 1)
            delete = DummyHandler()
            app.Handler.primary_database_delete(delete, module, str(new_id), self.auth)
            self.assertEqual(delete.result[0], 200)

    def test_daily_backup_is_created_before_mutation(self):
        backup_root = self.db_dir / "admin-data"
        with patch.object(app, "DATA_DIR", backup_root):
            app.Handler.backup_primary_database(DummyHandler(), "news",
                                                self.db_dir / "news.db")
        backup = backup_root / "primary-database-backups" / (
            "news-" + app.time.strftime("%Y%m%d", app.time.localtime()) + ".db"
        )
        self.assertTrue(backup.is_file())
        db = sqlite3.connect(backup)
        try:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM news").fetchone()[0], 1)
        finally:
            db.close()

    def test_unknown_module_is_rejected(self):
        with self.assertRaises(app.APIError):
            app.Handler._primary_db_spec("testdb")


if __name__ == "__main__":
    unittest.main()
