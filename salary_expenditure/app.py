"""
Salary Expenditure Management System
====================================
A beginner-friendly Flask + SQLite web application that lets a user:
  * set a monthly salary,
  * record, edit and delete daily expenses,
  * see total expenditure, remaining balance and % of salary spent,
  * view charts and a monthly summary report.

Run it with:   python app.py
Then open:     http://127.0.0.1:5000
"""

import calendar
import math
import os
import sqlite3
from datetime import date, datetime

from flask import Flask, flash, g, redirect, render_template, request, url_for

# ---------------------------------------------------------------------------
# 1. Configuration
# ---------------------------------------------------------------------------
BASE_DIR = os.path.abspath(os.path.dirname(__file__))

# The database file lives next to app.py. (SALARY_DB lets tests use another file.)
DATABASE = os.environ.get("SALARY_DB", os.path.join(BASE_DIR, "database.db"))

CURRENCY = "₹"            # change to "$" or "€" if you like
MAX_AMOUNT = 100_000_000  # largest amount we accept for one entry

CATEGORIES = [
    "Food", "Rent", "Travel", "Shopping",
    "Bills", "Education", "Healthcare", "Others",
]

# One colour per category (used for badges and charts)
CATEGORY_COLORS = {
    "Food": "#f59e0b",
    "Rent": "#6366f1",
    "Travel": "#0ea5e9",
    "Shopping": "#ec4899",
    "Bills": "#ef4444",
    "Education": "#10b981",
    "Healthcare": "#14b8a6",
    "Others": "#64748b",
}

app = Flask(__name__)
# The secret key is needed for flash messages. Change it for a real deployment.
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "change-this-secret-key")


# ---------------------------------------------------------------------------
# 2. Database helpers
# ---------------------------------------------------------------------------
def get_db():
    """Open one database connection per request and reuse it."""
    if "db" not in g:
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row  # lets us use row["column_name"]
    return g.db


@app.teardown_appcontext
def close_db(exception=None):
    """Close the connection automatically when the request ends."""
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    """Create the database file and tables if they do not exist yet."""
    db = sqlite3.connect(DATABASE)
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS salary (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            month      TEXT    NOT NULL UNIQUE,          -- e.g. '2026-10'
            amount     REAL    NOT NULL CHECK (amount >= 0),
            updated_at TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS expenses (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT    NOT NULL,
            amount      REAL    NOT NULL CHECK (amount > 0),
            category    TEXT    NOT NULL,
            date        TEXT    NOT NULL,                -- e.g. '2026-10-13'
            description TEXT    DEFAULT '',
            created_at  TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_expenses_date ON expenses(date);
        """
    )
    db.commit()
    db.close()


# ---------------------------------------------------------------------------
# 3. Small helper functions (dates, validation, calculations)
# ---------------------------------------------------------------------------
def current_month():
    """Return this month as text like '2026-10'."""
    return date.today().strftime("%Y-%m")


def normalize_month(value):
    """Return a clean 'YYYY-MM' string, or None if the value is not valid."""
    try:
        parsed = datetime.strptime((value or "").strip(), "%Y-%m")
    except ValueError:
        return None
    if not 2000 <= parsed.year <= 2100:
        return None
    return parsed.strftime("%Y-%m")


def month_from_request():
    """Read ?month=YYYY-MM from the URL; fall back to the current month."""
    return normalize_month(request.args.get("month", "")) or current_month()


def month_label(month):
    """'2026-10' -> 'October 2026'."""
    return datetime.strptime(month, "%Y-%m").strftime("%B %Y")


def parse_date(value):
    """Return a date from 'YYYY-MM-DD' text, or None if invalid."""
    try:
        parsed = datetime.strptime((value or "").strip(), "%Y-%m-%d").date()
    except ValueError:
        return None
    return parsed if 2000 <= parsed.year <= 2100 else None


def parse_amount(raw, allow_zero=False):
    """
    Convert text to a rounded number.
    Returns (value, error_message). Exactly one of them is None.
    """
    raw = (raw or "").replace(",", "").strip()
    if raw == "":
        return None, "Amount is required."
    try:
        value = float(raw)
    except ValueError:
        return None, "Amount must be a number."
    if not math.isfinite(value):          # blocks 'nan' and 'inf'
        return None, "Amount must be a valid number."
    if value < 0:
        return None, "Amount cannot be negative."
    if value == 0 and not allow_zero:
        return None, "Amount must be greater than zero."
    if value > MAX_AMOUNT:
        return None, f"Amount is too large (maximum {MAX_AMOUNT:,})."
    return round(value, 2), None


def validate_expense(form):
    """
    Check the expense form on the server (never trust the browser alone).
    Returns (clean_values, errors) where errors is a dict {field: message}.
    """
    errors = {}

    name = form.get("name", "").strip()
    if not name:
        errors["name"] = "Expense name is required."
    elif len(name) > 100:
        errors["name"] = "Expense name must be 100 characters or fewer."

    amount, amount_error = parse_amount(form.get("amount", ""))
    if amount_error:
        errors["amount"] = amount_error

    category = form.get("category", "").strip()
    if category not in CATEGORIES:
        errors["category"] = "Please choose a category from the list."

    expense_date = parse_date(form.get("date", ""))
    if expense_date is None:
        errors["date"] = "Please enter a valid date."

    description = form.get("description", "").strip()
    if len(description) > 300:
        errors["description"] = "Description must be 300 characters or fewer."

    clean = {
        "name": name,
        "amount": amount,
        "category": category,
        "date": expense_date.isoformat() if expense_date else "",
        "description": description,
    }
    return clean, errors


def get_salary(db, month):
    """
    Return (salary, carried_over).
    If no salary was saved for the month we reuse the most recent earlier
    salary (carried_over=True). If there is none at all we return 0.
    """
    row = db.execute("SELECT amount FROM salary WHERE month = ?", (month,)).fetchone()
    if row:
        return row["amount"], False
    row = db.execute(
        "SELECT amount FROM salary WHERE month < ? ORDER BY month DESC LIMIT 1",
        (month,),
    ).fetchone()
    if row:
        return row["amount"], True
    return 0.0, False


def month_summary(db, month):
    """Calculate all the headline numbers for one month."""
    salary, carried = get_salary(db, month)

    total = db.execute(
        "SELECT COALESCE(SUM(amount), 0) FROM expenses WHERE substr(date, 1, 7) = ?",
        (month,),
    ).fetchone()[0]
    total = round(total, 2)

    remaining = round(salary - total, 2)

    # Handle salary = 0 so we never divide by zero.
    percent = round(total / salary * 100, 1) if salary > 0 else None

    if salary <= 0:
        status = "no_salary"
    elif remaining < 0:
        status = "over"
    elif percent >= 80:
        status = "warning"
    else:
        status = "good"

    # Width of the progress bar (never more than 100%)
    if percent is not None:
        bar = min(percent, 100)
    else:
        bar = 100 if total > 0 else 0

    return {
        "salary": salary,
        "carried": carried,
        "total": total,
        "remaining": remaining,
        "percent": percent,
        "bar": bar,
        "status": status,
    }


def category_breakdown(db, month):
    """Total spent per category for a month, biggest first, with % share."""
    rows = db.execute(
        """
        SELECT category, SUM(amount) AS total, COUNT(*) AS count
        FROM expenses
        WHERE substr(date, 1, 7) = ?
        GROUP BY category
        ORDER BY total DESC
        """,
        (month,),
    ).fetchall()
    grand_total = sum(r["total"] for r in rows)
    return [
        {
            "category": r["category"],
            "total": round(r["total"], 2),
            "count": r["count"],
            "share": round(r["total"] / grand_total * 100, 1) if grand_total else 0,
        }
        for r in rows
    ]


def chart_category_data(breakdown):
    """Shape the category breakdown for Chart.js."""
    return {
        "labels": [b["category"] for b in breakdown],
        "values": [b["total"] for b in breakdown],
        "colors": [CATEGORY_COLORS.get(b["category"], "#64748b") for b in breakdown],
    }


# ---------------------------------------------------------------------------
# 4. Jinja filters and template variables
# ---------------------------------------------------------------------------
@app.template_filter("money")
def money_filter(value):
    """Format a number as money, e.g. 12500 -> ₹12,500.00 (negatives -> -₹500.00)."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = 0.0
    sign = "-" if number < 0 else ""
    return f"{sign}{CURRENCY}{abs(number):,.2f}"


@app.template_filter("nice_date")
def nice_date_filter(value):
    """'2026-10-13' -> '13 Oct 2026'."""
    parsed = parse_date(value)
    return parsed.strftime("%d %b %Y") if parsed else value


@app.context_processor
def inject_globals():
    """Variables available in every template."""
    return {
        "categories": CATEGORIES,
        "category_colors": CATEGORY_COLORS,
        "currency": CURRENCY,
        "this_month": current_month(),
        "today": date.today().isoformat(),
    }


# ---------------------------------------------------------------------------
# 5. Routes (pages)
# ---------------------------------------------------------------------------
@app.route("/")
def dashboard():
    """Home page: summary cards, category chart and recent expenses."""
    db = get_db()
    month = month_from_request()

    summary = month_summary(db, month)
    breakdown = category_breakdown(db, month)
    recent = db.execute(
        """
        SELECT * FROM expenses
        WHERE substr(date, 1, 7) = ?
        ORDER BY date DESC, id DESC
        LIMIT 6
        """,
        (month,),
    ).fetchall()

    return render_template(
        "dashboard.html",
        month=month,
        month_label=month_label(month),
        s=summary,
        breakdown=breakdown,
        chart_data={"currency": CURRENCY, "categories": chart_category_data(breakdown)},
        recent=recent,
    )


@app.route("/salary", methods=["GET", "POST"])
def salary():
    """Enter or update the salary for a month."""
    db = get_db()
    errors = {}

    if request.method == "POST":
        month_raw = request.form.get("month", "")
        amount_raw = request.form.get("amount", "")
        form = {"month": month_raw, "amount": amount_raw}

        month = normalize_month(month_raw)
        if month is None:
            errors["month"] = "Please choose a valid month."
        amount, amount_error = parse_amount(amount_raw, allow_zero=True)
        if amount_error:
            errors["amount"] = amount_error

        if not errors:
            # Insert a new row, or update it if this month already has a salary.
            db.execute(
                """
                INSERT INTO salary (month, amount) VALUES (?, ?)
                ON CONFLICT(month) DO UPDATE
                    SET amount = excluded.amount, updated_at = CURRENT_TIMESTAMP
                """,
                (month, amount),
            )
            db.commit()
            flash(f"Salary for {month_label(month)} saved: {money_filter(amount)}.", "success")
            return redirect(url_for("dashboard", month=month))

        flash("Please correct the highlighted fields.", "error")
    else:
        month = month_from_request()
        row = db.execute("SELECT amount FROM salary WHERE month = ?", (month,)).fetchone()
        form = {"month": month, "amount": f"{row['amount']:.2f}" if row else ""}

    history = db.execute("SELECT * FROM salary ORDER BY month DESC LIMIT 12").fetchall()
    return render_template("salary.html", form=form, errors=errors, history=history)


@app.route("/expenses")
def expenses():
    """List all expenses with optional filters (dates, category, search text)."""
    db = get_db()

    date_from = request.args.get("from", "").strip()
    date_to = request.args.get("to", "").strip()
    category = request.args.get("category", "").strip()
    search = request.args.get("q", "").strip()

    clauses, params = [], []

    if date_from:
        if parse_date(date_from):
            clauses.append("date >= ?")
            params.append(date_from)
        else:
            flash("The 'From' date was not valid and was ignored.", "error")
            date_from = ""
    if date_to:
        if parse_date(date_to):
            clauses.append("date <= ?")
            params.append(date_to)
        else:
            flash("The 'To' date was not valid and was ignored.", "error")
            date_to = ""
    if category in CATEGORIES:
        clauses.append("category = ?")
        params.append(category)
    else:
        category = ""
    if search:
        # Escape LIKE wildcards so the user's text is searched literally.
        escaped = search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        clauses.append("(name LIKE ? ESCAPE '\\' OR description LIKE ? ESCAPE '\\')")
        params.extend([f"%{escaped}%", f"%{escaped}%"])

    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""

    rows = db.execute(
        f"SELECT * FROM expenses {where} ORDER BY date DESC, id DESC", params
    ).fetchall()
    total = round(sum(r["amount"] for r in rows), 2)

    return render_template(
        "expenses.html",
        rows=rows,
        total=total,
        filters={"from": date_from, "to": date_to, "category": category, "q": search},
        has_filters=bool(clauses),
    )


@app.route("/expenses/add", methods=["GET", "POST"])
def add_expense():
    """Show the 'add expense' form and save it."""
    form = {"name": "", "amount": "", "category": "", "date": date.today().isoformat(), "description": ""}
    errors = {}

    if request.method == "POST":
        form = {key: request.form.get(key, "") for key in form}
        clean, errors = validate_expense(request.form)
        if not errors:
            db = get_db()
            db.execute(
                "INSERT INTO expenses (name, amount, category, date, description) VALUES (?, ?, ?, ?, ?)",
                (clean["name"], clean["amount"], clean["category"], clean["date"], clean["description"]),
            )
            db.commit()
            flash(f"Expense '{clean['name']}' added.", "success")
            return redirect(url_for("dashboard", month=clean["date"][:7]))
        flash("Please correct the highlighted fields.", "error")

    return render_template("add_expense.html", form=form, errors=errors)


@app.route("/expenses/<int:expense_id>/edit", methods=["GET", "POST"])
def edit_expense(expense_id):
    """Show the 'edit expense' form and save the changes."""
    db = get_db()
    row = db.execute("SELECT * FROM expenses WHERE id = ?", (expense_id,)).fetchone()
    if row is None:
        flash("That expense could not be found.", "error")
        return redirect(url_for("expenses"))

    errors = {}
    if request.method == "POST":
        form = {key: request.form.get(key, "") for key in ("name", "amount", "category", "date", "description")}
        clean, errors = validate_expense(request.form)
        if not errors:
            db.execute(
                "UPDATE expenses SET name = ?, amount = ?, category = ?, date = ?, description = ? WHERE id = ?",
                (clean["name"], clean["amount"], clean["category"], clean["date"], clean["description"], expense_id),
            )
            db.commit()
            flash("Expense updated.", "success")
            return redirect(url_for("expenses"))
        flash("Please correct the highlighted fields.", "error")
    else:
        form = {
            "name": row["name"],
            "amount": f"{row['amount']:.2f}",
            "category": row["category"],
            "date": row["date"],
            "description": row["description"] or "",
        }

    return render_template("edit_expense.html", form=form, errors=errors, expense_id=expense_id)


@app.route("/expenses/<int:expense_id>/delete", methods=["POST"])
def delete_expense(expense_id):
    """Delete one expense (POST only, so a link click can never delete by accident)."""
    db = get_db()
    cursor = db.execute("DELETE FROM expenses WHERE id = ?", (expense_id,))
    db.commit()
    if cursor.rowcount:
        flash("Expense deleted.", "success")
    else:
        flash("That expense could not be found.", "error")
    return redirect(url_for("expenses"))


@app.route("/reports")
def reports():
    """Charts plus a written monthly summary report."""
    db = get_db()
    month = month_from_request()
    year = month[:4]

    summary = month_summary(db, month)
    breakdown = category_breakdown(db, month)

    # Expenditure for each month of the selected year (for the bar chart)
    monthly_spend = [0.0] * 12
    rows = db.execute(
        """
        SELECT CAST(substr(date, 6, 2) AS INTEGER) AS m, SUM(amount) AS total
        FROM expenses
        WHERE substr(date, 1, 4) = ?
        GROUP BY m
        """,
        (year,),
    ).fetchall()
    for r in rows:
        monthly_spend[r["m"] - 1] = round(r["total"], 2)
    monthly_salary = [get_salary(db, f"{year}-{i:02d}")[0] for i in range(1, 13)]

    # Extra facts for the summary report
    stats = db.execute(
        "SELECT COUNT(*) AS n FROM expenses WHERE substr(date, 1, 7) = ?", (month,)
    ).fetchone()
    count = stats["n"]
    biggest = db.execute(
        """
        SELECT name, amount, category, date FROM expenses
        WHERE substr(date, 1, 7) = ?
        ORDER BY amount DESC, id DESC LIMIT 1
        """,
        (month,),
    ).fetchone()

    year_num, month_num = int(year), int(month[5:])
    if month == current_month():
        days = date.today().day            # days passed so far this month
    else:
        days = calendar.monthrange(year_num, month_num)[1]

    report = {
        "count": count,
        "average": round(summary["total"] / count, 2) if count else 0,
        "daily_average": round(summary["total"] / days, 2) if days else 0,
        "days": days,
        "biggest": biggest,
        "top_category": breakdown[0] if breakdown else None,
    }

    chart_data = {
        "currency": CURRENCY,
        "categories": chart_category_data(breakdown),
        "monthly": {
            "labels": [calendar.month_abbr[i] for i in range(1, 13)],
            "spend": monthly_spend,
            "salary": monthly_salary,
            "year": year,
        },
    }

    return render_template(
        "reports.html",
        month=month,
        month_label=month_label(month),
        year=year,
        s=summary,
        breakdown=breakdown,
        report=report,
        chart_data=chart_data,
        year_has_data=any(monthly_spend),
    )


# ---------------------------------------------------------------------------
# 6. Error pages
# ---------------------------------------------------------------------------
@app.errorhandler(404)
def not_found(error):
    return render_template("error.html", code=404, message="Sorry, that page does not exist."), 404


@app.errorhandler(405)
def method_not_allowed(error):
    return render_template("error.html", code=405, message="That action is not allowed here."), 405


@app.errorhandler(500)
def server_error(error):
    return render_template("error.html", code=500, message="Something went wrong on our side."), 500


# Create the database as soon as the app is loaded.
init_db()

if __name__ == "__main__":
    # debug=True reloads the server when you edit code. Turn it off for real use.
    app.run(debug=True)
