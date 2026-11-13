import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import app


class ProjectDataAccessTests(unittest.TestCase):
    def test_project_modules_use_role_specific_safe_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db_path = root / "project_data.db"
            db = sqlite3.connect(db_path)
            db.execute("""CREATE TABLE users (
                id INTEGER PRIMARY KEY, name TEXT, surname TEXT, email TEXT, mobile TEXT,
                city TEXT, country TEXT, accaunt_type TEXT, registration_data TEXT,
                last_visit TEXT, user_rate INTEGER, lot_count INTEGER, language TEXT,
                currency TEXT, user_shop_name TEXT, password TEXT, login_token TEXT,
                registration_token TEXT, last_ip TEXT, user_device_data TEXT,
                shop_description TEXT, shop_avatar TEXT, shop_banner TEXT,
                shop_verification TEXT, shop_podcategory TEXT, last_payment_for_shop TEXT
            )""")
            db.execute("""INSERT INTO users
                (id,name,surname,email,mobile,city,country,accaunt_type,registration_data,
                 last_visit,user_rate,lot_count,language,currency,user_shop_name,password,
                 login_token,registration_token,last_ip,user_device_data,shop_description,
                 shop_avatar,shop_banner,shop_verification,shop_podcategory,last_payment_for_shop)
                VALUES (1,'Test','User','test@example.test','+100000000','Grodno','BY','default',
                        '2026-01-01','2026-01-02',50,3,'RU','BYN','Test shop','hash',
                        'login-secret','registration-secret','127.0.0.1','device-secret',
                        'Shop description','data:image/png;base64,AA==','data:image/png;base64,AA==',
                        'ok','books','2026-01-03')""")
            db.commit()
            db.close()

            with patch.object(app, "PRIMARY_DB_DIR", root):
                handler = app.Handler.__new__(app.Handler)
                admin_users = handler.project_module_get("users", {}, "admin")
                super_users = handler.project_module_get("users", {}, "super")
                self.assertEqual(admin_users["total"], 1)
                self.assertNotIn("email", admin_users["columns"])
                self.assertIn("email", super_users["columns"])
                for result in (admin_users, super_users):
                    for secret in ("password", "login_token", "registration_token",
                                   "last_ip", "user_device_data"):
                        self.assertNotIn(secret, result["columns"])
                        self.assertNotIn(secret, result["items"][0])

                admin_shops = handler.project_module_get("shops", {}, "admin")
                super_shops = handler.project_module_get("shops", {}, "super")
                self.assertEqual(admin_shops["total"], 1)
                self.assertNotIn("email", admin_shops["columns"])
                self.assertIn("email", super_shops["columns"])
                self.assertEqual(admin_shops["items"][0]["user_shop_name"], "Test shop")

    def test_lot_mapping_includes_details_but_never_chat_tokens(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db_path = root / "project_data.db"
            db = sqlite3.connect(db_path)
            db.execute("""CREATE TABLE auto_category (
                id INTEGER, "seller_id	" TEXT, lot_name TEXT, lot_category TEXT,
                lot_podcategory TEXT, lot_year TEXT, lot_condition TEXT, auction_type TEXT,
                lot_start_price TEXT, lot_step TEXT, lot_buy_now TEXT, lot_minimum_bid TEXT,
                current_price TEXT, current_lot_status TEXT, lot_description TEXT,
                lot_country TEXT, lot_city TEXT, realtime_date TEXT, lot_bids_counter TEXT,
                lot_view_counter TEXT, pic1 TEXT, pic2 TEXT, pic3 TEXT, pic4 TEXT, pic5 TEXT,
                lot_delivery_track_number TEXT, user_seller_chat_token TEXT,
                dispute_user_description TEXT, dispute_seller_description TEXT
            )""")
            db.execute("""INSERT INTO auto_category VALUES
                (8,'42','Test lot','books','rare','1999','good','auction','10','1','50',
                 '5','12','active','Long description','BY','Grodno','2026-01-01',
                 '4','20','data:image/png;base64,AA==','','','','','TRACK-1',
                 'chat-secret','buyer dispute','seller dispute')""")
            db.commit()
            db.close()

            with patch.object(app, "PRIMARY_DB_DIR", root):
                handler = app.Handler.__new__(app.Handler)
                admin = handler.project_module_get("lots", {}, "admin")
                owner = handler.project_module_get("lots", {}, "super")
                self.assertEqual(admin["items"][0]["lot_description"], "Long description")
                self.assertEqual(admin["items"][0]["seller_id"], "42")
                self.assertNotIn("user_seller_chat_token", admin["items"][0])
                self.assertNotIn("user_seller_chat_token", owner["items"][0])
                self.assertIn("dispute_user_description", owner["items"][0])

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
                self.assertNotIn("password", result["columns"])
                self.assertNotIn("login_token", result["columns"])
                self.assertNotIn("password", result["items"][0])
                self.assertNotIn("login_token", result["items"][0])

            self.assertFalse(app.can_module({"role": "admin", "permissions": ["users"]}, "project_data"))
            self.assertTrue(app.can_module({"role": "super", "permissions": []}, "project_data"))
            db = sqlite3.connect(db_path)
            try:
                self.assertEqual(db.execute("SELECT COUNT(*) FROM users").fetchone()[0], 1)
            finally:
                db.close()


if __name__ == "__main__":
    unittest.main()
