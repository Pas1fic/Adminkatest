# Project Data access

project_data.db is opened read-only and is mapped into the existing admin sections:

- **Users** - a curated account overview; ordinary admins see operational/profile basics, while super admins additionally see contact and address details.
- **Shops** - only accounts with a real shop name; shown as a shop record with its owner, description, verification, category and image previews.
- **Lots** - records merged from all *_category tables, with a category-table filter and a detailed record view.
- **Currencies** - rates from currency_converter.
- **Newsletter** - recipients from spam_emails.

Passwords, password hashes, login/registration/session tokens, chat tokens, IP addresses and device fingerprints are excluded from both the mapped sections and the owner-only generic Project Data browser. The generic browser remains super-admin-only.

The original project_data.db is never modified by these views. Existing news, support and complaints modules continue to use their existing databases.
