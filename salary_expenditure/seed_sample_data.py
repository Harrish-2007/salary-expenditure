"""
Optional helper: fills the database with sample salary and expense data
so you can see the dashboard and charts working straight away.

Run it once from the project folder:
    python seed_sample_data.py

It adds data for the current month and the two months before it.
It does nothing if you already have expenses saved (so it never mixes
sample data with your real data).
"""

import sqlite3
from datetime import date

import app  # re-uses the database path and creates the tables


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
    db = sqlite3.connect(app.DATABASE)

    already = db.execute("SELECT COUNT(*) FROM expenses").fetchone()[0]
    if already:
        print(f"Database already has {already} expense(s). Nothing was added.")
        db.close()
        return

    today = date.today()
    for back, salary in enumerate(SALARIES):
        year, month = shift_month(today.year, today.month, back)
        month_text = f"{year}-{month:02d}"
        db.execute("INSERT OR REPLACE INTO salary (month, amount) VALUES (?, ?)", (month_text, salary))

        for day, name, amount, category, description in SAMPLE_EXPENSES:
            # In the current month, do not create dates in the future.
            if back == 0:
                day = min(day, today.day)
            # Make older months a little different so the bar chart is interesting.
            amount = round(amount * (1 - 0.04 * back), 2)
            db.execute(
                "INSERT INTO expenses (name, amount, category, date, description) VALUES (?, ?, ?, ?, ?)",
                (name, amount, category, f"{month_text}-{day:02d}", description),
            )

    db.commit()
    db.close()
    print("Sample data added: 3 months of salary and 36 expenses.")
    print("Now run:  python app.py")


if __name__ == "__main__":
    main()
