"""
Optional helper: fills the database with sample salary and expense data
so you can see the dashboard and charts working straight away.

Register an account in the app first, then run (from the project folder):
    python seed_sample_data.py you@example.com

It adds data for the current month and the two months before it.
It does nothing if that account already has expenses saved (so it never mixes
sample data with your real data).
"""

import sys
from datetime import date

import app  # re-uses the database connection code


def shift_month(year, month, back):
    """Go 'back' months into the past -> (year, month)."""
    index = year * 12 + (month - 1) - back
    return index // 12, index % 12 + 1


# (day of month, name, amount, category, description)
SAMPLE_EXPENSES = [
    (1, "House Rent", 12000, "Rent", "Monthly rent"),
    (2, "Groceries", 3200, "Food", "Vegetables and groceries"),
    (3, "Electricity Bill", 1450, "Bills", "EB bill"),
    (4, "Bus Pass", 600, "Travel", "Monthly bus pass"),
    (5, "Online Course", 1999, "Education", "Python course"),
    (7, "Restaurant Dinner", 850, "Food", "Dinner with friends"),
    (9, "New Shoes", 2499, "Shopping", ""),
    (11, "Doctor Visit", 700, "Healthcare", "Regular check-up"),
    (13, "Internet Bill", 799, "Bills", "Broadband"),
    (15, "Movie Tickets", 500, "Others", ""),
    (18, "Groceries", 2800, "Food", ""),
    (21, "Taxi Fare", 450, "Travel", "Airport ride"),
]

# Salary for each month: this month, last month, two months ago
SALARIES = [50000, 48000, 45000]


def main():
    if len(sys.argv) != 2:
        sys.exit("Usage: python seed_sample_data.py <your_account_email>")
    email = sys.argv[1].strip().lower()
    if app.CONFIG_PROBLEMS:
        sys.exit("Configuration problem: " + " ".join(app.CONFIG_PROBLEMS))

    app.init_db()
    db = app.connect()
    try:
        user = db.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
        if user is None:
            sys.exit(f"No account with email {email}. Register in the app first.")
        uid = user["id"]

        already = db.execute(
            "SELECT COUNT(*) AS n FROM expenses WHERE user_id = ?", (uid,)).fetchone()["n"]
        if already:
            print(f"This account already has {already} expense(s). Nothing was added.")
            return

        today = date.today()
        for back, salary in enumerate(SALARIES):
            year, month = shift_month(today.year, today.month, back)
            month_text = f"{year}-{month:02d}"
            db.execute(
                "INSERT INTO salary (user_id, month, amount) VALUES (?, ?, ?) "
                "ON CONFLICT (user_id, month) DO UPDATE SET amount = excluded.amount",
                (uid, month_text, salary))

            for day, name, amount, category, description in SAMPLE_EXPENSES:
                if back == 0:                       # no future dates this month
                    day = min(day, today.day)
                amount = round(amount * (1 - 0.04 * back), 2)
                db.execute(
                    "INSERT INTO expenses (user_id, name, amount, category, date, description) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (uid, name, amount, category, f"{month_text}-{day:02d}", description))
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
    print("Sample data added: 3 months of salary and 36 expenses.")


if __name__ == "__main__":
    main()
