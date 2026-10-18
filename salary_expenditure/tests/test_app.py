"""
Automatic tests for SalaryTrack v2.   Run from the project folder with:

    python -m unittest discover -s tests -v

By default the tests use a temporary SQLite file. To run the SAME tests against
a real PostgreSQL database, set TEST_DATABASE_URL first (use an EMPTY test
database, never your real one - the tests delete all rows in it).
"""
import os
import re
import sys
import tempfile
import unittest
from datetime import date

os.environ.setdefault("SECRET_KEY", "test-secret-key-for-unit-tests-only")
os.environ.pop("DATABASE_URL", None)
os.environ.pop("VERCEL", None)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app as appmod  # noqa: E402

TEST_URL = os.environ.get("TEST_DATABASE_URL")
TODAY = date.today()
THIS_MONTH = TODAY.strftime("%Y-%m")
THIS_DAY = TODAY.isoformat()


class Base(unittest.TestCase):
    def setUp(self):
        if TEST_URL:
            appmod.app.config["DATABASE_URL"] = TEST_URL
        else:
            self.tmp = tempfile.TemporaryDirectory()
            appmod.app.config["DATABASE_URL"] = "sqlite:///" + os.path.join(self.tmp.name, "t.db")
        appmod._db_ready = False
        appmod.app.config["TESTING"] = False   # exercise the real error pages
        appmod.CONFIG_PROBLEMS[:] = []
        appmod.ensure_db_ready()
        if TEST_URL:
            db = appmod.connect()
            for t in ("expenses", "salary", "users"):
                db.execute(f"DELETE FROM {t}")
            db.commit()
            db.close()
        self.alice = appmod.app.test_client()
        self.bob = appmod.app.test_client()

    def tearDown(self):
        if not TEST_URL:
            self.tmp.cleanup()

    # ---- helpers ----
    def token(self, client):
        html = client.get("/login", follow_redirects=True).get_data(as_text=True)
        m = re.search(r'name="csrf_token" value="([^"]+)"', html)
        return m.group(1)

    def post(self, client, url, data=None, **kw):
        data = dict(data or {})
        data["csrf_token"] = self.token(client)
        return client.post(url, data=data, **kw)

    def register(self, client, name="Alice", email="alice@example.com", pw="secret123"):
        return self.post(client, "/register", {"name": name, "email": email, "password": pw, "confirm": pw})

    def login(self, client, email="alice@example.com", pw="secret123"):
        return self.post(client, "/login", {"email": email, "password": pw})

    def set_salary(self, client, month, amount):
        return self.post(client, "/salary", {"month": month, "amount": str(amount)}, follow_redirects=True)

    def add_expense(self, client, name="Groceries", amount="100", category="Food", d=None, desc=""):
        return self.post(client, "/expenses/add", {
            "name": name, "amount": amount, "category": category, "date": d or THIS_DAY,
            "description": desc}, follow_redirects=True)

    def page(self, client, url):
        r = client.get(url, follow_redirects=True)
        return r.status_code, r.get_data(as_text=True)

    def expense_id(self, name):
        db = appmod.connect()
        try:
            return db.execute("SELECT id FROM expenses WHERE name = ?", (name,)).fetchone()["id"]
        finally:
            db.close()


class AuthTests(Base):
    def test_pages_require_login(self):
        for url in ("/", "/salary", "/expenses", "/expenses/add", "/reports"):
            r = self.alice.get(url)
            self.assertEqual(r.status_code, 302, url)
            self.assertIn("/login", r.headers["Location"])

    def test_register_validation(self):
        bad = [
            ({"name": "", "email": "a@b.com", "password": "secret123", "confirm": "secret123"}, "Please enter your name"),
            ({"name": "A", "email": "nope", "password": "secret123", "confirm": "secret123"}, "valid email"),
            ({"name": "A", "email": "a@b.com", "password": "short", "confirm": "short"}, "at least 8"),
            ({"name": "A", "email": "a@b.com", "password": "secret123", "confirm": "different1"}, "do not match"),
        ]
        for data, msg in bad:
            r = self.post(self.alice, "/register", data)
            self.assertEqual(r.status_code, 200)
            self.assertIn(msg, r.get_data(as_text=True))

    def test_register_login_logout_and_duplicate(self):
        r = self.register(self.alice)
        self.assertEqual(r.status_code, 302)            # logged in straight away
        self.assertEqual(self.alice.get("/").status_code, 200)
        self.post(self.alice, "/logout")
        self.assertEqual(self.alice.get("/").status_code, 302)
        r = self.login(self.alice, pw="wrong-password")
        self.assertIn("Incorrect email or password", r.get_data(as_text=True))
        self.assertEqual(self.login(self.alice).status_code, 302)
        self.assertEqual(self.alice.get("/").status_code, 200)
        r = self.register(self.bob, name="Other", email="ALICE@example.com")   # same email, other case
        self.assertIn("already registered", r.get_data(as_text=True))

    def test_password_is_hashed(self):
        self.register(self.alice)
        db = appmod.connect()
        h = db.execute("SELECT password_hash FROM users").fetchone()["password_hash"]
        db.close()
        self.assertNotIn("secret123", h)

    def test_csrf_blocks_post_without_token(self):
        self.register(self.alice)
        r = self.alice.post("/salary", data={"month": THIS_MONTH, "amount": "5"})
        self.assertEqual(r.status_code, 400)
        r = self.alice.post("/salary", data={"month": THIS_MONTH, "amount": "5", "csrf_token": "bad"})
        self.assertEqual(r.status_code, 400)

    def test_open_redirect_blocked(self):
        self.register(self.alice)
        self.post(self.alice, "/logout")
        r = self.post(self.alice, "/login?next=//evil.example.com",
                      {"email": "alice@example.com", "password": "secret123"})
        self.assertEqual(r.headers["Location"], "/")
        self.post(self.alice, "/logout")
        r = self.post(self.alice, "/login?next=/reports",
                      {"email": "alice@example.com", "password": "secret123"})
        self.assertEqual(r.headers["Location"], "/reports")


class SalaryAndExpenseTests(Base):
    def setUp(self):
        super().setUp()
        self.register(self.alice)

    def test_salary_create_update_and_not_stuck(self):
        """The old bug: salary stuck at 30,000. It must be changeable."""
        _, html = self.page(self.alice, "/")
        self.assertIn("₹0.00", html)
        self.set_salary(self.alice, THIS_MONTH, 30000)
        _, html = self.page(self.alice, f"/?month={THIS_MONTH}")
        self.assertIn("₹30,000.00", html)
        r = self.set_salary(self.alice, THIS_MONTH, 45500.5)
        self.assertIn("₹45,500.50", r.get_data(as_text=True))
        db = appmod.connect()
        n = db.execute("SELECT COUNT(*) AS n FROM salary").fetchone()["n"]
        db.close()
        self.assertEqual(n, 1)                          # updated, not duplicated

    def test_salary_validation(self):
        for bad in ("-5", "abc", "nan", "inf", "", "999999999999"):
            r = self.post(self.alice, "/salary", {"month": THIS_MONTH, "amount": bad})
            self.assertEqual(r.status_code, 200, bad)
            self.assertIn("field-error", r.get_data(as_text=True), bad)
        r = self.post(self.alice, "/salary", {"month": "2026-13", "amount": "5"})
        self.assertIn("valid month", r.get_data(as_text=True))
        # zero is allowed (unpaid month)
        r = self.set_salary(self.alice, THIS_MONTH, 0)
        self.assertEqual(r.status_code, 200)

    def test_calculations(self):
        self.set_salary(self.alice, THIS_MONTH, 30000)
        self.add_expense(self.alice, "Rent", "12000", "Rent")
        self.add_expense(self.alice, "Food", "3200.50", "Food")
        s = appmod.month_summary(self._db(), self._uid(), THIS_MONTH)
        self.assertEqual(s["total"], 15200.5)
        self.assertEqual(s["remaining"], 14799.5)
        self.assertEqual(s["percent"], 50.7)
        self.assertEqual(s["status"], "good")
        self.add_expense(self.alice, "TV", "20000", "Shopping")
        s = appmod.month_summary(self._db(), self._uid(), THIS_MONTH)
        self.assertEqual(s["status"], "over")
        self.assertEqual(s["remaining"], -5200.5)
        _, html = self.page(self.alice, "/")
        self.assertIn("-₹5,200.50", html)

    def test_carry_over_and_month_isolation(self):
        self.set_salary(self.alice, "2026-01", 30000)
        self.assertEqual(appmod.get_salary(self._db(), self._uid(), "2026-03"), (30000.0, True))
        self.set_salary(self.alice, "2026-03", 40000)
        self.assertEqual(appmod.get_salary(self._db(), self._uid(), "2026-03"), (40000.0, False))
        self.assertEqual(appmod.get_salary(self._db(), self._uid(), "2025-12"), (0.0, False))
        self.add_expense(self.alice, "Jan", "10", "Food", "2026-01-31")
        self.add_expense(self.alice, "Feb", "20", "Food", "2026-02-01")
        self.add_expense(self.alice, "Dec", "5", "Food", "2025-12-31")
        db, uid = self._db(), self._uid()
        self.assertEqual(appmod.month_summary(db, uid, "2026-01")["total"], 10)
        self.assertEqual(appmod.month_summary(db, uid, "2026-02")["total"], 20)
        self.assertEqual(appmod.month_summary(db, uid, "2025-12")["total"], 5)

    def test_salary_delete(self):
        self.set_salary(self.alice, "2026-05", 1000)
        self.post(self.alice, "/salary/2026-05/delete")
        self.assertEqual(appmod.get_salary(self._db(), self._uid(), "2026-05"), (0.0, False))
        r = self.post(self.alice, "/salary/2026-05/delete", follow_redirects=True)
        self.assertIn("could not be found", r.get_data(as_text=True))
        self.assertEqual(self.post(self.alice, "/salary/garbage/delete").status_code, 404)

    def test_expense_create_edit_delete(self):
        r = self.add_expense(self.alice, "Lunch", "250", "Food", desc="with team")
        self.assertIn("Lunch", r.get_data(as_text=True))
        eid = self.expense_id("Lunch")
        _, html = self.page(self.alice, f"/expenses/{eid}/edit")
        self.assertIn('value="250.00"', html)
        r = self.post(self.alice, f"/expenses/{eid}/edit", {
            "name": "Lunch+", "amount": "300", "category": "Travel", "date": THIS_DAY, "description": ""},
            follow_redirects=True)
        self.assertIn("Expense updated", r.get_data(as_text=True))
        self.assertIn("Lunch+", r.get_data(as_text=True))
        r = self.post(self.alice, f"/expenses/{eid}/delete", follow_redirects=True)
        self.assertIn("Expense deleted", r.get_data(as_text=True))
        r = self.post(self.alice, f"/expenses/{eid}/delete", follow_redirects=True)
        self.assertIn("could not be found", r.get_data(as_text=True))

    def test_expense_validation(self):
        cases = [
            {"name": "", "amount": "5", "category": "Food", "date": THIS_DAY},
            {"name": "x" * 101, "amount": "5", "category": "Food", "date": THIS_DAY},
            {"name": "x", "amount": "0", "category": "Food", "date": THIS_DAY},
            {"name": "x", "amount": "-1", "category": "Food", "date": THIS_DAY},
            {"name": "x", "amount": "abc", "category": "Food", "date": THIS_DAY},
            {"name": "x", "amount": "5", "category": "Hacking", "date": THIS_DAY},
            {"name": "x", "amount": "5", "category": "Food", "date": "31-02-2026"},
            {"name": "x", "amount": "5", "category": "Food", "date": "1999-01-01"},
            {"name": "x", "amount": "5", "category": "Food", "date": THIS_DAY, "description": "d" * 301},
        ]
        for data in cases:
            r = self.post(self.alice, "/expenses/add", data)
            self.assertEqual(r.status_code, 200, data)
            self.assertIn("field-error", r.get_data(as_text=True), data)
        db = appmod.connect()
        n = db.execute("SELECT COUNT(*) AS n FROM expenses").fetchone()["n"]
        db.close()
        self.assertEqual(n, 0)

    def test_filters_and_search(self):
        self.add_expense(self.alice, "Pizza 100%", "50", "Food", "2026-02-10")
        self.add_expense(self.alice, "Bus", "20", "Travel", "2026-02-11", "to_work")
        self.add_expense(self.alice, "Book", "70", "Education", "2026-03-01")
        _, h = self.page(self.alice, "/expenses?category=Food")
        self.assertIn("Pizza", h); self.assertNotIn(">Bus<", h)
        _, h = self.page(self.alice, "/expenses?from=2026-02-11&to=2026-02-28")
        self.assertIn("Bus", h); self.assertNotIn("Pizza", h); self.assertNotIn("Book", h)
        _, h = self.page(self.alice, "/expenses?q=100%25")          # literal percent sign
        self.assertIn("Pizza", h); self.assertNotIn("Book", h)
        _, h = self.page(self.alice, "/expenses?q=PIZZA")           # case-insensitive
        self.assertIn("Pizza", h)
        _, h = self.page(self.alice, "/expenses?q=to_work")         # literal underscore
        self.assertIn("Bus", h)
        _, h = self.page(self.alice, "/expenses?from=garbage")
        self.assertIn("not valid", h)

    def test_reports_and_dashboard_render(self):
        self.set_salary(self.alice, THIS_MONTH, 1000)
        self.add_expense(self.alice, "A", "100", "Food")
        self.add_expense(self.alice, "B", "300", "Rent")
        for url in (f"/?month={THIS_MONTH}", f"/reports?month={THIS_MONTH}", "/reports?month=garbage"):
            code, html = self.page(self.alice, url)
            self.assertEqual(code, 200, url)
        _, html = self.page(self.alice, f"/reports?month={THIS_MONTH}")
        self.assertIn("₹400.00", html)

    def _db(self):
        if not hasattr(self, "_dbc"):
            self._dbc = appmod.connect()
            self.addCleanup(self._dbc.close)
        return self._dbc

    def _uid(self):
        return self._db().execute("SELECT id FROM users WHERE email = 'alice@example.com'").fetchone()["id"]


class SeparationTests(Base):
    """Employee A must never see or change employee B's records."""

    def setUp(self):
        super().setUp()
        self.register(self.alice)
        self.register(self.bob, "Bob", "bob@example.com", "bobpass123")
        self.set_salary(self.alice, THIS_MONTH, 30000)
        self.add_expense(self.alice, "AliceSecret", "999", "Food")
        self.set_salary(self.bob, THIS_MONTH, 70000)
        self.add_expense(self.bob, "BobSecret", "111", "Rent")
        self.alice_eid = self.expense_id("AliceSecret")

    def test_lists_and_dashboards_are_separate(self):
        _, a = self.page(self.alice, "/expenses")
        _, b = self.page(self.bob, "/expenses")
        self.assertIn("AliceSecret", a); self.assertNotIn("BobSecret", a)
        self.assertIn("BobSecret", b); self.assertNotIn("AliceSecret", b)
        _, a = self.page(self.alice, "/")
        _, b = self.page(self.bob, "/")
        self.assertIn("₹30,000.00", a); self.assertNotIn("₹70,000.00", a)
        self.assertIn("₹70,000.00", b); self.assertNotIn("₹30,000.00", b)
        _, b = self.page(self.bob, "/salary")
        self.assertNotIn("30,000", b)
        _, b = self.page(self.bob, "/reports")
        self.assertNotIn("AliceSecret", b); self.assertNotIn("999", b)

    def test_cannot_open_edit_or_delete_others_expense(self):
        _, h = self.page(self.bob, f"/expenses/{self.alice_eid}/edit")
        self.assertIn("could not be found", h)
        self.assertNotIn("AliceSecret", h)
        r = self.post(self.bob, f"/expenses/{self.alice_eid}/edit", {
            "name": "HACKED", "amount": "1", "category": "Food", "date": THIS_DAY, "description": ""},
            follow_redirects=True)
        self.assertIn("could not be found", r.get_data(as_text=True))
        r = self.post(self.bob, f"/expenses/{self.alice_eid}/delete", follow_redirects=True)
        self.assertIn("could not be found", r.get_data(as_text=True))
        _, a = self.page(self.alice, "/expenses")
        self.assertIn("AliceSecret", a); self.assertNotIn("HACKED", a)

    def test_salary_changes_do_not_leak(self):
        self.set_salary(self.bob, THIS_MONTH, 1)
        _, a = self.page(self.alice, "/")
        self.assertIn("₹30,000.00", a)
        self.post(self.bob, f"/salary/{THIS_MONTH}/delete")
        _, a = self.page(self.alice, "/")
        self.assertIn("₹30,000.00", a)


class PersistenceAndErrorTests(Base):
    def test_data_survives_restart(self):
        self.register(self.alice)
        self.set_salary(self.alice, THIS_MONTH, 30000)
        self.add_expense(self.alice, "Kept", "10", "Food")
        # simulate a server restart: forget in-process state, brand-new client
        appmod._db_ready = False
        fresh = appmod.app.test_client()
        self.login(fresh)
        _, h = self.page(fresh, "/")
        self.assertIn("₹30,000.00", h)
        _, h = self.page(fresh, "/expenses")
        self.assertIn("Kept", h)

    def test_init_db_is_repeatable(self):
        appmod.init_db(); appmod.init_db()

    def test_error_pages(self):
        self.register(self.alice)
        code, h = self.page(self.alice, "/nope")
        self.assertEqual(code, 404)
        self.assertEqual(self.alice.get("/expenses/1/delete").status_code, 405)
        self.assertEqual(self.alice.get("/logout").status_code, 405)

    def test_unexpected_crash_gives_friendly_500(self):
        self.register(self.alice)
        original = appmod.month_summary
        def boom(*a, **k): raise RuntimeError("secret internal detail")
        appmod.month_summary = boom
        try:
            r = self.alice.get("/")
        finally:
            appmod.month_summary = original
        self.assertEqual(r.status_code, 500)
        h = r.get_data(as_text=True)
        self.assertIn("Something went wrong", h)
        self.assertNotIn("secret internal detail", h)
        self.assertEqual(self.alice.get("/").status_code, 200)      # app still fine afterwards

    def test_missing_configuration_shows_clear_message(self):
        appmod.CONFIG_PROBLEMS.append("DATABASE_URL is not set.")
        try:
            r = self.alice.get("/login")
        finally:
            appmod.CONFIG_PROBLEMS[:] = []
        self.assertEqual(r.status_code, 500)
        self.assertIn("DATABASE_URL is not set.", r.get_data(as_text=True))

    def test_production_config_rules(self):
        old = dict(os.environ)
        try:
            appmod.IS_PRODUCTION = True
            os.environ.pop("SECRET_KEY", None); os.environ.pop("DATABASE_URL", None); os.environ.pop("POSTGRES_URL", None)
            _, problems = appmod.load_config()
            self.assertEqual(len(problems), 2)
            os.environ["SECRET_KEY"] = "x" * 32
            os.environ["DATABASE_URL"] = "postgres://u:p@h/db"
            cfg, problems = appmod.load_config()
            self.assertEqual(problems, [])
            self.assertTrue(cfg["DATABASE_URL"].startswith("postgresql://"))
            os.environ["DATABASE_URL"] = "sqlite:///x.db"
            _, problems = appmod.load_config()
            self.assertEqual(len(problems), 1)
        finally:
            appmod.IS_PRODUCTION = False
            os.environ.clear(); os.environ.update(old)


if __name__ == "__main__":
    unittest.main()
