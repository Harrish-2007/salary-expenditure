# Salary Expenditure Management System

A beginner-friendly college mini project built with **HTML, CSS, JavaScript, Python Flask and SQLite**.
It helps you set a monthly salary, record daily expenses, and see how much you have spent and how much is left.

---

## 1. What is this project? (simple explanation)

Imagine you get a salary every month. During the month you spend money on food, rent, travel and so on.
This website lets you:

1. **Save your salary** for a month.
2. **Add every expense** (name, amount, category, date, optional note).
3. **See the result automatically**:
   - Total Expenditure = sum of all expenses in the month
   - Remaining Balance = Salary − Total Expenditure
   - Salary Spent % = (Total Expenditure ÷ Salary) × 100
4. **See charts** (doughnut chart by category, bar chart by month) and a **monthly summary report**.

If your salary is 0 the app shows "N/A" instead of crashing, and if you spend more than your salary it shows a red warning and a negative balance.

---

## 2. Folder structure

```
salary_expenditure/
├── app.py                  <- the Flask "brain": pages, calculations, database code
├── requirements.txt        <- list of Python packages to install (just Flask)
├── seed_sample_data.py     <- optional: fills the app with sample data for testing
├── database.db             <- created AUTOMATICALLY the first time you run app.py
├── README.md               <- this guide
├── PROJECT_REPORT.md       <- abstract, objectives, modules, etc. for your report
├── templates/              <- HTML pages (Flask calls these "templates")
│   ├── base.html           <- common layout: sidebar, top bar, messages
│   ├── _macros.html        <- reusable pieces (category badge, expense table)
│   ├── _expense_form.html  <- the form shared by Add and Edit pages
│   ├── dashboard.html      <- home page with cards, chart, recent transactions
│   ├── salary.html         <- enter / update monthly salary
│   ├── add_expense.html    <- add a new expense
│   ├── edit_expense.html   <- edit an existing expense
│   ├── expenses.html       <- all expenses + filters (date, category, search)
│   ├── reports.html        <- charts + monthly summary report
│   └── error.html          <- friendly 404 / 405 / 500 page
└── static/                 <- files the browser downloads as-is
    ├── css/style.css       <- all the colours, layout and responsive design
    ├── js/script.js        <- menu button, delete confirmation, charts
    └── images/favicon.svg  <- the small logo / browser-tab icon
```

### Purpose of each file

| File | What it does |
|---|---|
| `app.py` | Creates the database, defines every page (route), validates input, does the calculations. |
| `requirements.txt` | Tells `pip` which packages to install. |
| `seed_sample_data.py` | Adds 3 months of sample salary and expenses so you can test quickly. |
| `templates/base.html` | The page frame. Every other page "extends" it, so the sidebar is written only once. |
| `templates/_macros.html` | Small reusable HTML helpers used on several pages. |
| `templates/_expense_form.html` | One form used by both Add and Edit (no copy-paste). |
| `templates/dashboard.html` | Summary cards, category chart, breakdown list, recent transactions. |
| `templates/salary.html` | Salary form + salary history. |
| `templates/add_expense.html` / `edit_expense.html` | Pages that wrap the expense form. |
| `templates/expenses.html` | Full list with filters and Edit / Delete buttons. |
| `templates/reports.html` | Doughnut chart, monthly bar chart, summary report, print button. |
| `static/css/style.css` | Design: sidebar, cards, tables, forms, mobile layout, print layout. |
| `static/js/script.js` | Mobile menu, "Are you sure?" on delete, and draws the charts. |

### How the database looks

**salary** table: `id`, `month` (like `2026-10`), `amount`, `updated_at`
**expenses** table: `id`, `name`, `amount`, `category`, `date`, `description`, `created_at`

Both tables are created automatically when the app starts. All SQL uses `?` placeholders (parameterized queries), which protects against SQL injection.

---

## 3. Setup on Windows with Visual Studio Code

### Step 0 - Install the tools (one time only)
1. Install **Python 3.9 or newer** from <https://www.python.org/downloads/>.
   On the first installer screen, **tick "Add python.exe to PATH"**.
2. Install **Visual Studio Code** from <https://code.visualstudio.com/>.
3. In VS Code open the Extensions panel (`Ctrl+Shift+X`) and install the **Python** extension (by Microsoft).

### Step 1 - Open the project
1. Unzip `salary_expenditure.zip` (right-click → *Extract All*).
2. In VS Code choose **File → Open Folder…** and select the `salary_expenditure` folder.
3. Open a terminal inside VS Code: **Terminal → New Terminal** (shortcut: `` Ctrl+` ``).

### Step 2 - Create a virtual environment (keeps packages tidy)
```
python -m venv venv
```
Activate it:
```
venv\Scripts\activate
```
You should now see `(venv)` at the start of the terminal line.

> **If PowerShell says "running scripts is disabled"**, run this once and try again:
> `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass`
> (or switch the terminal to *Command Prompt* using the dropdown next to the **+** button).

If VS Code asks *"We noticed a new environment…"*, click **Yes**. You can also pick it via `Ctrl+Shift+P` → *Python: Select Interpreter* → the one inside `venv`.

### Step 3 - Install the dependencies
```
pip install -r requirements.txt
```

### Step 4 - (Optional) add sample data
```
python seed_sample_data.py
```

### Step 5 - Run the application
```
python app.py
```
You will see something like:
```
 * Running on http://127.0.0.1:5000
```

### Step 6 - Open it in the browser
Open Chrome / Edge and go to **http://127.0.0.1:5000**
(or hold `Ctrl` and click the link in the VS Code terminal).
To stop the server press `Ctrl+C` in the terminal.

> **Charts need internet.** The chart library (Chart.js) is loaded from a CDN, so the doughnut and bar charts appear only when you are online. Everything else works offline.

---

## 4. Sample data for testing

The quickest way is `python seed_sample_data.py`. To enter data by hand instead:

**Salary** (page *Salary*): month = current month, amount = `50000`

**Expenses** (page *Add Expense*):

| Name | Amount | Category | Date | Description |
|---|---|---|---|---|
| House Rent | 12000 | Rent | 1st of this month | Monthly rent |
| Groceries | 3200 | Food | 2nd | Vegetables and groceries |
| Electricity Bill | 1450 | Bills | 3rd | EB bill |
| Bus Pass | 600 | Travel | 4th | |
| Online Course | 1999 | Education | 5th | Python course |
| Restaurant Dinner | 850 | Food | 7th | |
| New Shoes | 2499 | Shopping | 9th | |
| Doctor Visit | 700 | Healthcare | 11th | |
| Movie Tickets | 500 | Others | 15th | |

Expected result for the table above with salary 50000: **Total = ₹23,798.00**, **Remaining = ₹26,202.00**, **Spent = 47.6%**.

---

## 5. How to test each feature

| Feature | What to do | What you should see |
|---|---|---|
| **Database auto-creation** | Delete `database.db`, run `python app.py` | A new `database.db` appears. |
| **Salary** | *Salary* → month + `50000` → Save | Green message; dashboard shows ₹50,000.00. Save again with `55000` → it updates (no duplicate). |
| **Add expense** | *Add Expense* → fill the form → Save | Green message; the dashboard totals change. |
| **Validation** | Submit with empty name, amount `0`, or `-5` | Red messages under the fields; nothing is saved. |
| **Edit** | *Expenses* → **Edit** → change the amount → Update | List shows the new amount. |
| **Delete** | *Expenses* → **Delete** → OK | Row disappears; totals update. |
| **Filter** | *Expenses* → choose a category / date range / search text → Apply | Only matching rows and a filtered total. Use **Clear** to reset. |
| **Calculations** | Compare dashboard with the sample table above | Total, remaining and % match. |
| **Salary = 0** | Save a salary of `0` | "N/A" for percentage and a yellow message, no crash. |
| **Overspending** | Add expenses larger than the salary | Red warning, negative remaining balance, bar turns red. |
| **Month switch** | Change the month picker on Dashboard/Reports | Numbers change for that month. |
| **Charts** | Open *Dashboard* and *Reports* (internet needed) | Doughnut chart by category; bar chart of the year's monthly spending with a salary line. |
| **Monthly report** | *Reports* | Summary table, verdict sentence, category table. **Print / Save as PDF** gives a clean printout. |
| **Mobile view** | Press `F12` → device toolbar icon (`Ctrl+Shift+M`) | Sidebar hides behind the ☰ button; tables become cards. |

### Common errors and fixes

| Problem | Fix |
|---|---|
| `'python' is not recognized` | Reinstall Python and tick **Add python.exe to PATH**, or try `py` instead of `python`. |
| `No module named flask` | The virtual environment is not active or packages are not installed. Run `venv\Scripts\activate` then `pip install -r requirements.txt`. |
| PowerShell blocks `activate` | `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass`, or use Command Prompt. |
| `Address already in use` (port 5000) | Another program uses port 5000. Close it, or change the last line of `app.py` to `app.run(debug=True, port=5001)` and open `http://127.0.0.1:5001`. |
| Page opens but charts are empty | You are offline, or there is no data for that month. Connect to the internet and refresh (`Ctrl+F5`). |
| CSS looks old after editing | Hard refresh with `Ctrl+F5`. |
| `TemplateNotFound` | Run `python app.py` from inside the `salary_expenditure` folder; the `templates` folder must be next to `app.py`. |
| Want to start fresh | Stop the server, delete `database.db`, run again. |

---

## 6. Features checklist

- Dashboard: salary, total expenditure, remaining balance, % spent, category breakdown, recent transactions
- Salary management (stored in SQLite, one value per month, update any time)
- Expenses: add / view / edit / delete with 8 categories and optional description
- Automatic calculations with zero-salary and over-spending handling
- Reports: doughnut chart, monthly bar chart, filters by date and category, monthly summary report
- Server-side validation, flash messages, parameterized SQL, friendly error pages
- Responsive layout with sidebar navigation and mobile-friendly tables

For the abstract, objectives, modules, advantages, limitations and future enhancements, see **PROJECT_REPORT.md**.
