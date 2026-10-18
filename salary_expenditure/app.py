"""
Salary Expenditure Management System  (SalaryTrack v2)
=======================================================
A beginner-friendly Flask web application where every employee has their own
account and can:
  * set a monthly salary,
  * record, edit and delete daily expenses,
  * see total expenditure, remaining balance and % of salary spent,
  * view charts and a monthly summary report.

What is new in v2
  * Register / log in / log out (passwords are stored hashed, never as text).
  * Every salary and expense row belongs to one user (user_id) and every query
    filters by the logged-in user, so employees never see each other's data.
  * PostgreSQL for the online version (set DATABASE_URL). On your own computer
    it still works with a local SQLite file if DATABASE_URL is not set.
  * No secrets in the code: SECRET_KEY and DATABASE_URL come from environment
    variables.
  * CSRF protection on every form and clear error pages.

Run it locally with:   python app.py      ->  http://127.0.0.1:5000
"""

import calendar
import hmac
import math
import os
import re
import secrets
import sqlite3
from datetime import date, datetime
from functools import wraps
from urllib.parse import urlparse

from flask import (
    Flask, abort, flash, g, redirect, render_template, request, session, url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash

# ---------------------------------------------------------------------------
# 1. Configuration (everything secret comes from environment variables)
# ---------------------------------------------------------------------------
BASE_DIR = os.path.abspath(os.path.dirname(__file__))

# Vercel sets VERCEL=1 automatically. You can also set APP_ENV=production.
IS_PRODUCTION = bool(os.environ.get("VERCEL")) or os.environ.get("APP_ENV") == "production"

CURRENCY = "₹"            # change to "$" or "€" if you like
MAX_AMOUNT = 100_000_000  # largest amount we accept for one entry

CATEGORIES = [
    "Food", "Rent", "Travel", "Shopping",
    "Bills", "Education", "Healthcare", "Others",
]

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


def _normalize_database_url(url):
    """Hosting sites give 'postgres://...'; the driver wants 'postgresql://...'."""
    if url.startswith("postgres://"):
        return "postgresql://" + url[len("postgres://"):]
    return url


def _dev_secret_key():
    """
    Local development only: create a random secret once and keep it in a
    git-ignored file, so you stay logged in when the dev server reloads.
    """
    path = os.path.join(BASE_DIR, ".dev_secret_key")
    try:
        with open(path) as f:
            value = f.read().strip()
        if value:
            return value
        value = secrets.token_hex(32)
        with open(path, "w") as f:
            f.write(value)
        return value
    except OSError:
        return None


def load_config():
    """Read settings from the environment. Returns (config_dict, problems_list)."""
    problems = []

    secret = os.environ.get("SECRET_KEY", "").strip()
    if not secret:
        if IS_PRODUCTION:
            problems.append(
                "SECRET_KEY is not set. Add a long random value in your hosting "
                "dashboard (Environment Variables)."
            )
        else:
            secret = _dev_secret_key() or ""
            if not secret:
                problems.append("SECRET_KEY is not set and a local one could not be created.")
    elif len(secret) < 16:
        problems.append("SECRET_KEY is too short. Use at least 16 random characters.")

    url = _normalize_database_url(
        (os.environ.get("DATABASE_URL") or os.environ.get("POSTGRES_URL") or "").strip()
    )
    if not url:
        if IS_PRODUCTION:
            problems.append(
                "DATABASE_URL is not set. Online deployments need a PostgreSQL "
                "database (see README: Neon / Supabase)."
            )
        else:
            url = "sqlite:///" + os.path.join(BASE_DIR, "salarytrack.db")
    elif not (url.startswith("postgresql://") or url.startswith("sqlite:///")):
        problems.append("DATABASE_URL must start with postgresql:// (or sqlite:/// for local use).")
    elif IS_PRODUCTION and url.startswith("sqlite"):
        problems.append("SQLite cannot store data on Vercel. Set DATABASE_URL to a PostgreSQL database.")

    return {"SECRET_KEY": secret or "unset", "DATABASE_URL": url}, problems


app = Flask(
    __name__,
    # CSS/JS live in public/static so Vercel can serve them from its CDN while
    # Flask serves the very same URLs (/static/...) when you run locally.
    static_folder=os.path.join(BASE_DIR, "public", "static"),
    static_url_path="/static",
)
_config, CONFIG_PROBLEMS = load_config()
app.config.update(
    SECRET_KEY=_config["SECRET_KEY"],
    DATABASE_URL=_config["DATABASE_URL"],
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=IS_PRODUCTION,
    MAX_CONTENT_LENGTH=64 * 1024,   # no form needs more than 64 KB
)


# ---------------------------------------------------------------------------
# 2. Database layer: SQLite on your laptop, PostgreSQL online
# ---------------------------------------------------------------------------
class ConfigError(Exception):
    """Raised when the app is not set up correctly (shown as a helpful page)."""


def is_postgres():
    return app.config["DATABASE_URL"].startswith("postgresql://")


class Database:
    """
    A tiny wrapper so the rest of the code can write the same SQL for both
    databases. Write '?' for values; they are turned into '%s' for PostgreSQL.
    Always pass values as parameters (never build SQL with f-strings).
    """

    def __init__(self, conn, postgres):
        self.conn = conn
        self.postgres = postgres

    def execute(self, sql, params=()):
        if self.postgres:
            sql = sql.replace("?", "%s")
        cur = self.conn.cursor()
        cur.execute(sql, params)
        return cur

    def commit(self):
        self.conn.commit()

    def rollback(self):
        self.conn.rollback()

    def close(self):
        self.conn.close()


_pg_ready = False


def _setup_postgres_types(psycopg2):
    """Return numbers as float and dates as 'YYYY-MM-DD' text, like SQLite does."""
    global _pg_ready
    if _pg_ready:
        return
    from psycopg2 import extensions
    extensions.register_type(extensions.new_type(
        (1700,), "NUMERIC_AS_FLOAT", lambda v, cur: float(v) if v is not None else None))
    extensions.register_type(extensions.new_type(
        (1082,), "DATE_AS_TEXT", lambda v, cur: v))
    _pg_ready = True


def connect():
    """Open a new database connection."""
    url = app.config["DATABASE_URL"]
    if is_postgres():
        try:
            import psycopg2
            import psycopg2.extras
        except ImportError:
            raise ConfigError("The PostgreSQL driver is missing. Run: pip install psycopg2-binary")
        _setup_postgres_types(psycopg2)
        try:
            conn = psycopg2.connect(
                url, cursor_factory=psycopg2.extras.RealDictCursor, connect_timeout=10)
        except psycopg2.OperationalError as exc:
            app.logger.error("Could not connect to PostgreSQL: %s", exc)
            raise ConfigError(
                "Could not connect to the database. Check DATABASE_URL "
                "(user, password, host, and ?sslmode=require for hosted databases).")
        return Database(conn, True)

    path = url[len("sqlite:///"):]
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return Database(conn, False)


def get_db():
    """One connection per request (reused inside the request)."""
    if "db" not in g:
        g.db = connect()
    return g.db


@app.teardown_appcontext
def close_db(exception=None):
    db = g.pop("db", None)
    if db is not None:
        try:
            db.close()
        except Exception:      # closing must never hide the real error
            pass


SCHEMA_SQLITE = [
    """CREATE TABLE IF NOT EXISTS users (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        name          TEXT NOT NULL,
        email         TEXT NOT NULL UNIQUE,
        password_hash TEXT NOT NULL,
        created_at    TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )""",
    """CREATE TABLE IF NOT EXISTS salary (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        month      TEXT NOT NULL,
        amount     REAL NOT NULL CHECK (amount >= 0),
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE (user_id, month)
    )""",
    """CREATE TABLE IF NOT EXISTS expenses (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        name        TEXT NOT NULL,
        amount      REAL NOT NULL CHECK (amount > 0),
        category    TEXT NOT NULL,
        date        TEXT NOT NULL,
        description TEXT DEFAULT '',
        created_at  TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )""",
    "CREATE INDEX IF NOT EXISTS idx_expenses_user_date ON expenses (user_id, date)",
]

SCHEMA_POSTGRES = [
    """CREATE TABLE IF NOT EXISTS users (
        id            BIGSERIAL PRIMARY KEY,
        name          TEXT NOT NULL,
        email         TEXT NOT NULL UNIQUE,
        password_hash TEXT NOT NULL,
        created_at    TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
    )""",
    """CREATE TABLE IF NOT EXISTS salary (
        id         BIGSERIAL PRIMARY KEY,
        user_id    BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        month      TEXT NOT NULL,
        amount     NUMERIC(14,2) NOT NULL CHECK (amount >= 0),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE (user_id, month)
    )""",
    """CREATE TABLE IF NOT EXISTS expenses (
        id          BIGSERIAL PRIMARY KEY,
        user_id     BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        name        TEXT NOT NULL,
        amount      NUMERIC(14,2) NOT NULL CHECK (amount > 0),
        category    TEXT NOT NULL,
        date        DATE NOT NULL,
        description TEXT DEFAULT '',
        created_at  TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
    )""",
    "CREATE INDEX IF NOT EXISTS idx_expenses_user_date ON expenses (user_id, date)",
]


def init_db(db=None):
    """Create the tables if they do not exist yet. Safe to run many times."""
    own = db is None
    db = db or connect()
    statements = SCHEMA_POSTGRES if db.postgres else SCHEMA_SQLITE
    try:
        for attempt in (1, 2):
            try:
                for sql in statements:
                    db.execute(sql)
                db.commit()
                break
            except Exception:
                db.rollback()
                # Two cold-starting servers can race to create the same table.
                # Trying once more is enough because the tables then exist.
                if attempt == 2:
                    raise
    finally:
        if own:
            db.close()


_db_ready = False


def ensure_db_ready():
    """Run init_db() once per server process (cheap and idempotent)."""
    global _db_ready
    if not _db_ready:
        init_db()
        _db_ready = True


# ---------------------------------------------------------------------------
# 3. Security helpers: CSRF, login, safe redirects
# ---------------------------------------------------------------------------
def csrf_token():
    """A random token stored in the session and placed in every form."""
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_hex(16)
    return session["csrf_token"]


def safe_next_url(target):
    """Only allow redirects to pages on this site (blocks open-redirect tricks)."""
    if not target:
        return None
    parts = urlparse(target)
    if parts.scheme or parts.netloc or not target.startswith("/") or target.startswith("//") or "\\" in target:
        return None
    return target


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if g.user is None:
            flash("Please log in to continue.", "error")
            return redirect(url_for("login", next=safe_next_url(request.full_path.rstrip("?"))))
        return view(*args, **kwargs)
    return wrapped


@app.before_request
def before_request():
    """Runs before every page: config check, database setup, CSRF, who is logged in."""
    g.user = None
    if request.endpoint == "static":
        return None

    if CONFIG_PROBLEMS:
        return render_template("error.html", code=500, message="The server is not configured yet.",
                               details=CONFIG_PROBLEMS), 500

    try:
        ensure_db_ready()
    except ConfigError as exc:
        return render_template("error.html", code=500, message=str(exc)), 500

    if request.method == "POST":
        sent = request.form.get("csrf_token", "")
        expected = session.get("csrf_token", "")
        if not expected or not hmac.compare_digest(sent, expected):
            abort(400)

    user_id = session.get("user_id")
    if user_id is not None:
        row = get_db().execute(
            "SELECT id, name, email FROM users WHERE id = ?", (user_id,)).fetchone()
        if row is None:
            session.clear()          # account no longer exists
        else:
            g.user = row
    return None


@app.after_request
def security_headers(response):
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "same-origin")
    if request.endpoint != "static":
        response.headers.setdefault("Cache-Control", "no-store")   # private pages
    return response


# ---------------------------------------------------------------------------
# 4. Small helper functions (dates, validation, calculations)
# ---------------------------------------------------------------------------
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def current_month():
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
    return normalize_month(request.args.get("month", "")) or current_month()


def month_label(month):
    return datetime.strptime(month, "%Y-%m").strftime("%B %Y")


def month_range(month):
    """'2026-10' -> ('2026-10-01', '2026-11-01'): start (included), end (excluded)."""
    year, mon = int(month[:4]), int(month[5:7])
    ny, nm = (year + 1, 1) if mon == 12 else (year, mon + 1)
    return f"{year:04d}-{mon:02d}-01", f"{ny:04d}-{nm:02d}-01"


def parse_date(value):
    """Return a date from 'YYYY-MM-DD' text (or a date), or None if invalid."""
    if isinstance(value, date):
        return value
    try:
        parsed = datetime.strptime((value or "").strip(), "%Y-%m-%d").date()
    except ValueError:
        return None
    return parsed if 2000 <= parsed.year <= 2100 else None


def parse_amount(raw, allow_zero=False):
    """Convert text to a rounded number. Returns (value, error_message)."""
    raw = (raw or "").replace(",", "").strip()
    if raw == "":
        return None, "Amount is required."
    try:
        value = float(raw)
    except ValueError:
        return None, "Amount must be a number."
    if not math.isfinite(value):
        return None, "Amount must be a valid number."
    if value < 0:
        return None, "Amount cannot be negative."
    if value == 0 and not allow_zero:
        return None, "Amount must be greater than zero."
    if value > MAX_AMOUNT:
        return None, f"Amount is too large (maximum {MAX_AMOUNT:,})."
    return round(value, 2), None


def validate_expense(form):
    """Check the expense form on the server. Returns (clean_values, errors)."""
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


def get_salary(db, user_id, month):
    """
    Return (salary, carried_over) for this user.
    If no salary was saved for the month we reuse the most recent earlier
    salary (carried_over=True). If there is none at all we return 0.
    """
    row = db.execute(
        "SELECT amount FROM salary WHERE user_id = ? AND month = ?", (user_id, month)).fetchone()
    if row:
        return row["amount"], False
    row = db.execute(
        "SELECT amount FROM salary WHERE user_id = ? AND month < ? ORDER BY month DESC LIMIT 1",
        (user_id, month),
    ).fetchone()
    if row:
        return row["amount"], True
    return 0.0, False


def month_summary(db, user_id, month):
    """Calculate all the headline numbers for one month."""
    salary, carried = get_salary(db, user_id, month)
    start, end = month_range(month)

    total = db.execute(
        "SELECT COALESCE(SUM(amount), 0) AS total FROM expenses "
        "WHERE user_id = ? AND date >= ? AND date < ?",
        (user_id, start, end),
    ).fetchone()["total"]
    total = round(float(total), 2)

    remaining = round(salary - total, 2)
    percent = round(total / salary * 100, 1) if salary > 0 else None

    if salary <= 0:
        status = "no_salary"
    elif remaining < 0:
        status = "over"
    elif percent >= 80:
        status = "warning"
    else:
        status = "good"

    if percent is not None:
        bar = min(percent, 100)
    else:
        bar = 100 if total > 0 else 0

    return {
        "salary": salary, "carried": carried, "total": total,
        "remaining": remaining, "percent": percent, "bar": bar, "status": status,
    }


def category_breakdown(db, user_id, month):
    """Total spent per category for a month, biggest first, with % share."""
    start, end = month_range(month)
    rows = db.execute(
        """
        SELECT category, SUM(amount) AS total, COUNT(*) AS count
        FROM expenses
        WHERE user_id = ? AND date >= ? AND date < ?
        GROUP BY category
        ORDER BY total DESC, category
        """,
        (user_id, start, end),
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
    return {
        "labels": [b["category"] for b in breakdown],
        "values": [b["total"] for b in breakdown],
        "colors": [CATEGORY_COLORS.get(b["category"], "#64748b") for b in breakdown],
    }


def own_expense(db, expense_id):
    """Fetch an expense ONLY if it belongs to the logged-in user (else None)."""
    return db.execute(
        "SELECT * FROM expenses WHERE id = ? AND user_id = ?", (expense_id, g.user["id"])
    ).fetchone()


# ---------------------------------------------------------------------------
# 5. Jinja filters and template variables
# ---------------------------------------------------------------------------
@app.template_filter("money")
def money_filter(value):
    """12500 -> ₹12,500.00 (negatives -> -₹500.00)."""
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
    return {
        "categories": CATEGORIES,
        "category_colors": CATEGORY_COLORS,
        "currency": CURRENCY,
        "this_month": current_month(),
        "today": date.today().isoformat(),
        "csrf_token": csrf_token,
        "user": g.get("user"),
    }


# ---------------------------------------------------------------------------
# 6. Account routes: register, login, logout
# ---------------------------------------------------------------------------
@app.route("/register", methods=["GET", "POST"])
def register():
    if g.user:
        return redirect(url_for("dashboard"))
    errors, form = {}, {"name": "", "email": ""}

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm", "")
        form = {"name": name, "email": email}

        if not name:
            errors["name"] = "Please enter your name."
        elif len(name) > 60:
            errors["name"] = "Name must be 60 characters or fewer."
        if not EMAIL_RE.match(email) or len(email) > 254:
            errors["email"] = "Please enter a valid email address."
        if len(password) < 8:
            errors["password"] = "Password must be at least 8 characters."
        elif len(password) > 128:
            errors["password"] = "Password must be 128 characters or fewer."
        if password != confirm and "password" not in errors:
            errors["confirm"] = "The two passwords do not match."

        if not errors:
            db = get_db()
            if db.execute("SELECT 1 AS x FROM users WHERE email = ?", (email,)).fetchone():
                errors["email"] = "That email is already registered. Try logging in."
            else:
                try:
                    row = db.execute(
                        "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?) RETURNING id",
                        (name, email, generate_password_hash(password)),
                    ).fetchone()
                    db.commit()
                except Exception:
                    db.rollback()
                    # Almost always two sign-ups with the same email at once.
                    app.logger.exception("Registration failed")
                    errors["email"] = "That email is already registered. Try logging in."
                else:
                    session.clear()
                    session["user_id"] = row["id"]
                    flash(f"Welcome, {name}! Start by saving your monthly salary.", "success")
                    return redirect(url_for("salary"))
        flash("Please correct the highlighted fields.", "error")

    return render_template("register.html", form=form, errors=errors)


# Used to spend the same time on unknown emails as on wrong passwords.
_DUMMY_HASH = generate_password_hash("not-a-real-password")


@app.route("/login", methods=["GET", "POST"])
def login():
    if g.user:
        return redirect(url_for("dashboard"))
    form = {"email": ""}

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        form["email"] = email

        row = get_db().execute(
            "SELECT id, name, password_hash FROM users WHERE email = ?", (email,)).fetchone()
        ok = check_password_hash(row["password_hash"] if row else _DUMMY_HASH, password)
        if row and ok:
            session.clear()                       # new session after login
            session["user_id"] = row["id"]
            flash(f"Welcome back, {row['name']}.", "success")
            return redirect(safe_next_url(request.args.get("next")) or url_for("dashboard"))
        flash("Incorrect email or password.", "error")

    return render_template("login.html", form=form)


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("login"))


# ---------------------------------------------------------------------------
# 7. Main routes (all of them need a logged-in user)
# ---------------------------------------------------------------------------
@app.route("/")
@login_required
def dashboard():
    """Home page: summary cards, category chart and recent expenses."""
    db, uid = get_db(), g.user["id"]
    month = month_from_request()
    start, end = month_range(month)

    summary = month_summary(db, uid, month)
    breakdown = category_breakdown(db, uid, month)
    recent = db.execute(
        """
        SELECT * FROM expenses
        WHERE user_id = ? AND date >= ? AND date < ?
        ORDER BY date DESC, id DESC
        LIMIT 6
        """,
        (uid, start, end),
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
@login_required
def salary():
    """Enter or update the salary for a month."""
    db, uid = get_db(), g.user["id"]
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
                INSERT INTO salary (user_id, month, amount) VALUES (?, ?, ?)
                ON CONFLICT (user_id, month) DO UPDATE
                    SET amount = excluded.amount, updated_at = CURRENT_TIMESTAMP
                """,
                (uid, month, amount),
            )
            db.commit()
            flash(f"Salary for {month_label(month)} saved: {money_filter(amount)}.", "success")
            return redirect(url_for("dashboard", month=month))

        flash("Please correct the highlighted fields.", "error")
    else:
        month = month_from_request()
        row = db.execute(
            "SELECT amount FROM salary WHERE user_id = ? AND month = ?", (uid, month)).fetchone()
        form = {"month": month, "amount": f"{row['amount']:.2f}" if row else ""}

    history = db.execute(
        "SELECT month, amount FROM salary WHERE user_id = ? ORDER BY month DESC LIMIT 12",
        (uid,)).fetchall()
    return render_template("salary.html", form=form, errors=errors, history=history)


@app.route("/salary/<month>/delete", methods=["POST"])
@login_required
def delete_salary(month):
    """Delete the saved salary of one month (expenses are not touched)."""
    month = normalize_month(month)
    if month is None:
        abort(404)
    db = get_db()
    cur = db.execute("DELETE FROM salary WHERE user_id = ? AND month = ?", (g.user["id"], month))
    db.commit()
    if cur.rowcount:
        flash(f"Salary for {month_label(month)} deleted.", "success")
    else:
        flash("That salary entry could not be found.", "error")
    return redirect(url_for("salary"))


@app.route("/expenses")
@login_required
def expenses():
    """List your expenses with optional filters (dates, category, search text)."""
    db, uid = get_db(), g.user["id"]

    date_from = request.args.get("from", "").strip()
    date_to = request.args.get("to", "").strip()
    category = request.args.get("category", "").strip()
    search = request.args.get("q", "").strip()[:100]

    clauses, params = ["user_id = ?"], [uid]
    filtered = False

    if date_from:
        if parse_date(date_from):
            clauses.append("date >= ?")
            params.append(date_from)
            filtered = True
        else:
            flash("The 'From' date was not valid and was ignored.", "error")
            date_from = ""
    if date_to:
        if parse_date(date_to):
            clauses.append("date <= ?")
            params.append(date_to)
            filtered = True
        else:
            flash("The 'To' date was not valid and was ignored.", "error")
            date_to = ""
    if category in CATEGORIES:
        clauses.append("category = ?")
        params.append(category)
        filtered = True
    else:
        category = ""
    if search:
        # Escape LIKE wildcards so the text is searched literally; LOWER() makes
        # the search case-insensitive on both SQLite and PostgreSQL.
        escaped = search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_").lower()
        clauses.append("(LOWER(name) LIKE ? ESCAPE '\\' OR LOWER(description) LIKE ? ESCAPE '\\')")
        params.extend([f"%{escaped}%", f"%{escaped}%"])
        filtered = True

    rows = db.execute(
        "SELECT * FROM expenses WHERE " + " AND ".join(clauses) + " ORDER BY date DESC, id DESC",
        params,
    ).fetchall()
    total = round(sum(r["amount"] for r in rows), 2)

    return render_template(
        "expenses.html",
        rows=rows,
        total=total,
        filters={"from": date_from, "to": date_to, "category": category, "q": search},
        has_filters=filtered,
    )


@app.route("/expenses/add", methods=["GET", "POST"])
@login_required
def add_expense():
    form = {"name": "", "amount": "", "category": "", "date": date.today().isoformat(), "description": ""}
    errors = {}

    if request.method == "POST":
        form = {key: request.form.get(key, "") for key in form}
        clean, errors = validate_expense(request.form)
        if not errors:
            db = get_db()
            db.execute(
                "INSERT INTO expenses (user_id, name, amount, category, date, description) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (g.user["id"], clean["name"], clean["amount"], clean["category"],
                 clean["date"], clean["description"]),
            )
            db.commit()
            flash(f"Expense '{clean['name']}' added.", "success")
            return redirect(url_for("dashboard", month=clean["date"][:7]))
        flash("Please correct the highlighted fields.", "error")

    return render_template("add_expense.html", form=form, errors=errors)


@app.route("/expenses/<int:expense_id>/edit", methods=["GET", "POST"])
@login_required
def edit_expense(expense_id):
    db = get_db()
    row = own_expense(db, expense_id)
    if row is None:
        # Same message whether it does not exist or belongs to someone else.
        flash("That expense could not be found.", "error")
        return redirect(url_for("expenses"))

    errors = {}
    if request.method == "POST":
        form = {key: request.form.get(key, "") for key in ("name", "amount", "category", "date", "description")}
        clean, errors = validate_expense(request.form)
        if not errors:
            db.execute(
                "UPDATE expenses SET name = ?, amount = ?, category = ?, date = ?, description = ? "
                "WHERE id = ? AND user_id = ?",
                (clean["name"], clean["amount"], clean["category"], clean["date"],
                 clean["description"], expense_id, g.user["id"]),
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
            "date": str(row["date"]),
            "description": row["description"] or "",
        }

    return render_template("edit_expense.html", form=form, errors=errors, expense_id=expense_id)


@app.route("/expenses/<int:expense_id>/delete", methods=["POST"])
@login_required
def delete_expense(expense_id):
    db = get_db()
    cur = db.execute("DELETE FROM expenses WHERE id = ? AND user_id = ?", (expense_id, g.user["id"]))
    db.commit()
    if cur.rowcount:
        flash("Expense deleted.", "success")
    else:
        flash("That expense could not be found.", "error")
    return redirect(url_for("expenses"))


@app.route("/reports")
@login_required
def reports():
    """Charts plus a written monthly summary report."""
    db, uid = get_db(), g.user["id"]
    month = month_from_request()
    year = month[:4]
    start, end = month_range(month)

    summary = month_summary(db, uid, month)
    breakdown = category_breakdown(db, uid, month)

    # Expenditure for each month of the selected year (for the bar chart).
    # We add the numbers up in Python so the same code works on any database.
    monthly_spend = [0.0] * 12
    year_rows = db.execute(
        "SELECT date, amount FROM expenses WHERE user_id = ? AND date >= ? AND date < ?",
        (uid, f"{year}-01-01", f"{int(year) + 1}-01-01"),
    ).fetchall()
    for r in year_rows:
        monthly_spend[int(str(r["date"])[5:7]) - 1] += r["amount"]
    monthly_spend = [round(v, 2) for v in monthly_spend]
    monthly_salary = [get_salary(db, uid, f"{year}-{i:02d}")[0] for i in range(1, 13)]

    count = db.execute(
        "SELECT COUNT(*) AS n FROM expenses WHERE user_id = ? AND date >= ? AND date < ?",
        (uid, start, end)).fetchone()["n"]
    biggest = db.execute(
        """
        SELECT name, amount, category, date FROM expenses
        WHERE user_id = ? AND date >= ? AND date < ?
        ORDER BY amount DESC, id DESC LIMIT 1
        """,
        (uid, start, end),
    ).fetchone()

    year_num, month_num = int(year), int(month[5:])
    if month == current_month():
        days = date.today().day
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
# 8. Error pages
# ---------------------------------------------------------------------------
def _error(code, message, details=None):
    return render_template("error.html", code=code, message=message, details=details), code


@app.errorhandler(400)
def bad_request(error):
    return _error(400, "Your session expired or the form was invalid. Please go back, "
                       "refresh the page and try again.")


@app.errorhandler(404)
def not_found(error):
    return _error(404, "Sorry, that page does not exist.")


@app.errorhandler(405)
def method_not_allowed(error):
    return _error(405, "That action is not allowed here.")


@app.errorhandler(413)
def too_large(error):
    return _error(413, "That request was too large.")


@app.errorhandler(ConfigError)
def config_error(error):
    return _error(500, str(error))


@app.errorhandler(Exception)
def unexpected_error(error):
    """Any other crash: undo half-finished database work, log it, show a friendly page."""
    from werkzeug.exceptions import HTTPException
    if isinstance(error, HTTPException):
        return _error(error.code or 500, error.description or "Something went wrong.")
    db = g.get("db")
    if db is not None:
        try:
            db.rollback()
        except Exception:
            pass
    app.logger.exception("Unhandled error on %s %s", request.method, request.path)
    return _error(500, "Something went wrong on our side. Your data was not changed. "
                       "Please try again; if it keeps happening, check the server logs.")


if __name__ == "__main__":
    # debug=True reloads the server when you edit code. Never use it online.
    app.run(debug=True)
