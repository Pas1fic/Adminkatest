# Project Data access

- `db/project_data.db` is connected as the `project_data` module.
- Only accounts with the `super` role can see the menu item or call `/api/project_data`.
- Authorization is checked on the server; hiding the menu is not the security boundary.
- The super-admin owner can inspect every table and field, including sensitive columns.
- Ordinary admins cannot access this database, even by calling the API directly.
- The database is opened in SQLite read-only mode. Create, update, and delete operations are intentionally disabled.
- The admin management API prevents creating a second super-admin, promoting an admin to super, or demoting/blocking the owner account.
