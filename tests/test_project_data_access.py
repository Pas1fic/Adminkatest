import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import app


class ProjectDataAccessTests(unittest.TestCase):
    def test_project_data_is_read_only_and_super_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db_path = root / "project_data.db"
            db = sqlite3.connect(db_path)
            db.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, email TEXT, password TEXT, login_token TEXT)")
            db.execute("INSERT INTO users VALUES (1, 'owner@example.test', 'hash-value', 'secret-token')")
            db.commit()
            db.close()

            with patch.object(app, "PRIMARY_DB_DIR", root):
                handler = app.Handler.__new__(app.Handler)
                tables = handler.project_data_get({})
                self.assertEqual(tables["tables"][0]["name"], "users")
                result = handler.project_data_get({"table": ["users"]})
                self.assertEqual(result["items"][0]["password"], "hash-value")
                self.assertEqual(result["items"][0]["login_token"], "secret-token")

            self.assertFalse(app.can_module({"role": "admin", "permissions": ["users"]}, "project_data"))
            self.assertTrue(app.can_module({"role": "super", "permissions": []}, "project_data"))
            db = sqlite3.connect(db_path)
            try:
                self.assertEqual(db.execute("SELECT COUNT(*) FROM users").fetchone()[0], 1)
            finally:
                db.close()


if __name__ == "__main__":
    unittest.main()
