import base64
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlparse

import app


class DummyHandler:
    _test_db_spec = staticmethod(app.Handler._test_db_spec)
    _test_db_schema = staticmethod(app.Handler._test_db_schema)

    def __init__(self, path=""):
        self.path = path
        self.result = None

    def send_json(self, status, payload, cookie=None):
        self.result = (status, payload)

    def ip(self):
        return "127.0.0.1"


class TestDatabaseAdminTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db_dir = Path(self.temp.name)
        for name in ("news.db", "profile_support.db", "profile_yammer.db"):
            shutil.copy2(Path(app.ROOT) / "test_databases" / name, self.db_dir / name)
        self.db_patch = patch.object(app, "TEST_DB_DIR", self.db_dir)
        self.audit_patch = patch.object(app, "audit", lambda *args, **kwargs: None)
        self.db_patch.start()
        self.audit_patch.start()
        self.addCleanup(self.db_patch.stop)
        self.addCleanup(self.audit_patch.stop)
        self.auth = {"id": 1, "username": "unit-test", "role": "super"}

    def call_get(self, key, table, query=""):
        handler = DummyHandler(f"/api/test-databases/{key}/{table}{query}")
        app.Handler.test_database_get(handler, urlparse(handler.path).path)
        self.assertEqual(handler.result[0], 200)
        return handler.result[1]

    def test_lists_all_three_original_schemas(self):
        expected = {
            "news": ("news", 100, 10),
            "support": ("support_messages", 2, 9),
            "yammer": ("yammer_messages", 2, 9),
        }
        for key, (table, rows, columns) in expected.items():
            result = self.call_get(key, table)
            self.assertEqual(result["total"], rows)
            self.assertEqual(len(result["columns"]), columns)

    def test_search_and_crud_with_blob_upload(self):
        cases = [
            ("news", "news", {"published": "2099-01-01"}),
            ("support", "support_messages", {"proof": base64.b64encode(b"unit attachment").decode()}),
            ("yammer", "yammer_messages", {"proof": base64.b64encode(b"unit attachment").decode()}),
        ]
        for key, table, extra in cases:
            result = self.call_get(key, table)
            row = result["items"][0]
            editable = next(c["name"] for c in result["columns"]
                            if c["editable"] and c["name"] not in {"proof", "id"})
            update = DummyHandler(f"/api/test-databases/{key}/{table}")
            app.Handler.test_database_write(
                update, update.path,
                {"id": row[result["primary_key"]], editable: row[editable]}, self.auth
            )
            self.assertEqual(update.result[0], 200)

            values = {editable: "unit-test-value", **extra}
            insert = DummyHandler(f"/api/test-databases/{key}/{table}")
            app.Handler.test_database_write(insert, insert.path, values, self.auth)
            self.assertEqual(insert.result[0], 200)
            new_id = insert.result[1]["item"][result["primary_key"]]

            if "proof" in extra:
                self.assertIn("BLOB", insert.result[1]["item"]["proof"])

            search = self.call_get(key, table, "?q=unit-test-value")
            self.assertGreaterEqual(search["total"], 1)

            delete = DummyHandler(f"/api/test-databases/{key}/{table}/{new_id}")
            app.Handler.test_database_delete(delete, delete.path, self.auth)
            self.assertEqual(delete.result[0], 200)

    def test_rejects_unknown_database_and_table(self):
        with self.assertRaises(app.APIError):
            app.Handler._test_db_spec("unknown")
        with self.assertRaises(app.APIError):
            app.Handler._test_db_spec("news", "admins")


if __name__ == "__main__":
    unittest.main()
