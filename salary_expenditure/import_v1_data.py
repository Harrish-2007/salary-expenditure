"""
Copy your OLD (v1) salary and expense data into a v2 account.

Your old file (database.db) is only READ - it is never changed or deleted.

Steps:
  1. Start the app, register your account, and log in once.
  2. Run (from the project folder):

         python import_v1_data.py path/to/old/database.db you@example.com

  To import into your ONLINE database, set DATABASE_URL first (see README).
Running it twice does not create duplicates.
"""
import sqlite3
import sys

import app


def main():
    if len(sys.argv) != 3:
        sys.exit("Usage: python import_v1_data.py <old_database.db> <your_account_email>")
    old_path, email = sys.argv[1], sys.argv[2].strip().lower()

    if app.CONFIG_PROBLEMS:
        sys.exit("Configuration problem: " + " ".join(app.CONFIG_PROBLEMS))

    old = sqlite3.connect(f"file:{old_path}?mode=ro", uri=True)   # read-only
    old.row_factory = sqlite3.Row
    salaries = old.execute("SELECT month, amount FROM salary").fetchall()
    expenses = old.execute(
        "SELECT name, amount, category, date, description FROM expenses").fetchall()
    old.close()

    app.init_db()
    db = app.connect()
    try:
        user = db.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
        if user is None:
            sys.exit(f"No account with email {email}. Register in the app first.")
        uid = user["id"]

        for s in salaries:
            db.execute(
                "INSERT INTO salary (user_id, month, amount) VALUES (?, ?, ?) "
                "ON CONFLICT (user_id, month) DO NOTHING", (uid, s["month"], s["amount"]))

        added = 0
        for e in expenses:
            exists = db.execute(
                "SELECT 1 AS x FROM expenses WHERE user_id = ? AND name = ? AND amount = ? "
                "AND date = ? AND category = ?",
                (uid, e["name"], e["amount"], e["date"], e["category"])).fetchone()
            if not exists:
                db.execute(
                    "INSERT INTO expenses (user_id, name, amount, category, date, description) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (uid, e["name"], e["amount"], e["category"], e["date"], e["description"] or ""))
                added += 1
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
    print(f"Done: {len(salaries)} salary row(s) checked, {added} new expense(s) imported for {email}.")


if __name__ == "__main__":
    main()
