# SalaryTrack v2 – Salary Expenditure Management System

Flask + HTML/CSS/JS web app. Each employee has their own account and sees only
their own salary, expenses and reports. Data is stored in **PostgreSQL** online
(and in a local **SQLite** file on your own computer if you do not set a database).

## What was wrong in v1 and what changed

| Problem in v1 | Root cause | Fix in v2 |
|---|---|---|
| **500 Internal Server Error** on Vercel | `app.py` created and wrote `database.db` next to the code. Vercel's code folder is read-only, so `init_db()` crashed when the app loaded. | The database is now PostgreSQL, set with `DATABASE_URL`. No files are written. |
| Salary/expenses "stuck" at ₹30,000 | Most likely a `database.db` shipped with the deployment (reads work, writes fail on a read-only disk). Also, a month with no salary reuses the latest earlier one, so an old ₹30,000 keeps showing until you save that month. | Data lives in PostgreSQL. The carry-over rule is kept but is now labelled on the dashboard; edit/delete any month on the **Salary** page. |
| Data lost on restart/redeploy | SQLite file inside a temporary server | PostgreSQL is a separate always-on database. |
| All users share one set of data | No `user_id`, no login | `users` table + `user_id` on every salary and expense row; every query filters by the logged-in user. |
| Hardcoded secret key | `"change-this-secret-key"` default | `SECRET_KEY` comes from an environment variable; the app refuses to start online without it. |
| Unhelpful errors | Generic 500 page | Clear messages for missing settings, database connection problems, expired forms, and any other crash (the real error goes to the server log). |

Also new: CSRF protection on every form, hashed passwords, delete-salary, and a
script to move your old v1 data into your new account.

## Project layout

```
app.py                  all routes, login, database code
templates/              HTML pages (login.html and register.html are new)
public/static/          css/js/images (served at /static/...)
tests/test_app.py       24 automatic tests
import_v1_data.py       copy old v1 data into your account
seed_sample_data.py     optional demo data for an account
requirements.txt        Flask + psycopg2-binary
.env.example            names of the environment variables
```

## 1. Run it locally in VS Code (Windows)

Open the project folder in VS Code, then open **Terminal → New Terminal** (PowerShell):

```powershell
py -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

Open http://127.0.0.1:5000, click **Create an account**, then go to **Salary**
and enter your salary. With no `DATABASE_URL` set, data is saved in a local file
`salarytrack.db` (your old `database.db` is never touched).

If PowerShell blocks `venv\Scripts\activate`, run once:
`Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`.

### Optional: run locally against PostgreSQL
```powershell
$env:DATABASE_URL = "postgresql://USER:PASSWORD@HOST/DBNAME?sslmode=require"
python app.py
```

## 2. Create the production database (free)

Recommended: **Neon** (neon.tech) – free PostgreSQL that works well with Vercel.
(Supabase also works.)

1. Sign up at neon.tech → **Create project** (any name; pick the region closest to you).
2. On the project page click **Connect** and copy the connection string. Use the
   **pooled** one if offered. It looks like
   `postgresql://user:password@ep-xxxx-pooler.region.aws.neon.tech/dbname?sslmode=require`.
3. Keep it secret – it is a password. Never put it in code or on GitHub.

You do **not** have to create tables by hand: the app creates them the first
time it runs (`CREATE TABLE IF NOT EXISTS`, safe to repeat). For this project
size that is the "migration". If you later change the table design, a tool such
as Alembic can be added.

## 3. Deploy on Vercel

> I could not open Vercel's documentation while preparing this, so the Vercel
> steps below come from my general knowledge and are **not verified**. If a
> step looks different on screen, trust Vercel's current Flask guide.

1. **Back up first.** On GitHub, create a branch from your current code
   (e.g. `v1-backup`) so the original is never lost. Then put the v2 files on a
   new branch (e.g. `v2`) and open a Pull Request, or replace `main` only after
   you have tested.
2. Make sure `.gitignore` is included so `.env`, `*.db` and `venv/` are not uploaded.
3. Generate a secret key (any computer with Python):
   `python -c "import secrets; print(secrets.token_hex(32))"`
4. In Vercel: **Add New → Project →** import the GitHub repo (choose the v2 branch).
5. Before clicking Deploy, open **Environment Variables** and add:
   - `SECRET_KEY` = the random text from step 3
   - `DATABASE_URL` = the Neon connection string
6. Deploy. Vercel looks for `app.py` with a variable named `app` and installs
   `requirements.txt`. Static files are in `public/static`, which Vercel serves directly.
7. Open the site and register. If you see a page saying **"The server is not
   configured yet"**, it lists exactly which variable is missing or wrong.
   Any other error: Vercel dashboard → your project → **Logs**.

Vercel's free plan runs the app as short-lived serverless functions. That is fine
here because nothing is stored on the server – only in PostgreSQL.
If you prefer a plain always-on server, Render or Railway also work with this
code (start command: `gunicorn app:app`, and add `gunicorn` to `requirements.txt`).

## 4. Move your old v1 data into your account (optional)

1. Register in the app (locally or online).
2. Run, from the project folder (for the **online** database, first set
   `$env:DATABASE_URL = "..."` and `$env:SECRET_KEY = "..."` in the same terminal):

```powershell
python import_v1_data.py path\to\old\database.db you@example.com
```

The old file is opened read-only. Running it twice does not create duplicates.

## 5. Run the automatic tests

```powershell
python -m unittest discover -s tests -v
```

The 24 tests cover: login/logout/registration rules, CSRF, salary create/update/
delete, expense add/edit/delete, calculations (remaining balance, percent, over
budget), month boundaries, filters/search, employee separation, persistence
after a restart, and error pages.

To run the same tests on a real PostgreSQL database, point `TEST_DATABASE_URL` at
an **empty test database** (the tests delete all rows in it):
```powershell
$env:TEST_DATABASE_URL = "postgresql://USER:PASSWORD@HOST/TESTDB?sslmode=require"
python -m unittest discover -s tests -v
```

## 6. Manual testing checklist (do this after deploying)

1. Open the site → you are sent to the login page.
2. Create account **A** → you land on Salary. Enter ₹30,000 for this month → dashboard shows ₹30,000.00.
3. Change it to ₹45,500 → dashboard shows ₹45,500.00 (it must **not** stay at 30,000).
4. Add expenses: Rent ₹12,000, Food ₹3,200.50 → Total ₹15,200.50, remaining ₹30,299.50.
5. Edit one expense's amount → totals update. Delete one → it disappears and totals update.
6. Add an expense larger than the remaining balance → status turns to "over" with a negative balance.
7. Try bad input (empty name, amount `-5` or `abc`, category missing) → clear red messages, nothing saved.
8. **Persistence:** in Vercel redeploy (Deployments → ⋯ → Redeploy), then log in again → all data is still there.
9. Log out, create account **B** (use another email or a private window) → B sees ₹0, no expenses.
10. As B add a salary/expense → log back in as A: A's numbers are unchanged.
11. While logged in as B, paste the URL of A's edit page (`/expenses/<A's id>/edit`) → "could not be found".
12. Log in on a phone or another browser with account A → same data (multi-device).
13. Visit `/nonexistent` → friendly 404 page.
14. In Neon, open the **Tables** viewer: `users`, `salary`, `expenses` exist; passwords appear only as long hashes.

## 7. Where should data live? (your section 4 question)

| Option | Good | Bad |
|---|---|---|
| **Online PostgreSQL** (chosen) | Same data on every device; backups; real multi-user security; survives anything | Needs internet; you must keep the DB password secret |
| **Browser storage** (`localStorage`) | Zero setup, works offline | ~5 MB limit, text only, lost if the user clears the browser, stuck on one device/browser, readable by any script on the page, no real accounts |
| **IndexedDB** | Large offline storage, structured, works offline | Still one browser on one device; clearing site data deletes it; more complex code; no sharing or backup |
| **SQLite file on the employee's PC** | Fast, familiar, works offline | A web app on a server cannot reach files on each employee's computer; you would need a desktop app (e.g. Electron) and separate backup/sync; no multi-device |

Offline use can be added later: keep PostgreSQL as the source of truth and cache
data in IndexedDB, syncing when online.

## Security notes and limits

- Passwords are hashed with Werkzeug; forms use a CSRF token; session cookies are
  `HttpOnly`, `SameSite=Lax` and `Secure` online; all SQL uses parameters.
- There is no "forgot password" email, no login rate-limiting and no email
  verification yet. Add these before using it for real payroll data.
- Amounts are stored as `NUMERIC(14,2)` in PostgreSQL. Currency symbol is `₹`
  (change `CURRENCY` in `app.py`).
