# Salary Expenditure Management System - Project Report Content

## Abstract
The Salary Expenditure Management System is a web-based application that helps an individual plan and control personal spending against a monthly salary. The user records a monthly salary and logs daily expenses with a name, amount, category, date and optional description. The system automatically calculates the total expenditure, remaining balance and the percentage of salary spent, and it warns the user when spending is high or exceeds the salary. Charts and a monthly summary report give a clear picture of where the money goes. The application is developed with HTML5 and CSS3 for the interface, Python Flask for the server logic and SQLite for data storage, and it runs locally on an ordinary computer without any paid software.

## Objectives
1. To provide a simple tool for recording a monthly salary and daily expenses.
2. To calculate total expenditure, remaining balance and percentage of salary spent automatically and accurately.
3. To classify expenses into categories (Food, Rent, Travel, Shopping, Bills, Education, Healthcare, Others).
4. To present spending through charts and a monthly summary report that support better budgeting decisions.
5. To store data safely and permanently in a database.
6. To offer a clean, responsive interface that works on desktops, tablets and phones.
7. To apply web-development concepts: routing, templates, database access, validation and responsive design.

## Modules
1. **Dashboard Module** - shows salary, total expenditure, remaining balance, percentage spent, category chart and recent transactions for a selected month.
2. **Salary Management Module** - adds or updates the salary for any month and shows salary history.
3. **Expense Management Module** - adds, views, edits and deletes expense records, with input validation.
4. **Calculation Module** - computes total expenditure, remaining balance and percentage spent; handles zero salary and overspending.
5. **Filter and Search Module** - filters transactions by date range, category and text.
6. **Reports and Charts Module** - doughnut chart (expenses by category), bar chart (monthly expenditure) and a printable monthly summary report.
7. **Database Module** - SQLite database with `salary` and `expenses` tables created automatically at start-up.
8. **User Interface Module** - sidebar navigation, summary cards, validation messages and mobile-friendly layout.

## Technologies Used
| Layer | Technology |
|---|---|
| Frontend | HTML5, CSS3, JavaScript |
| Backend | Python 3, Flask (Jinja2 templates) |
| Database | SQLite |
| Charts | Chart.js |
| Tools | Visual Studio Code, web browser |

## System Design (short)
- **Salary table**: id, month (unique), amount, updated_at.
- **Expenses table**: id, name, amount, category, date, description, created_at.
- **Flow**: Browser → Flask route → validation → SQLite (parameterized query) → calculations → HTML template → Browser.

## Advantages
- Easy to use and quick to learn.
- Automatic, error-free calculations.
- Helps the user avoid overspending through warnings and clear visuals.
- Free and lightweight; runs offline on a local computer (charts need internet for the CDN library).
- Uses a real database, so data is saved permanently.
- Parameterized queries and server-side validation make it safer and more reliable.
- Responsive design works on mobile screens as well as desktops.
- Clean, modular code that is easy to understand and extend.

## Limitations
- Single-user application with no login or password protection.
- Data is stored on one computer; there is no cloud backup or sync.
- Only one salary value per month; no separate income sources.
- No budget limits per category and no recurring-expense automation.
- Charts need an internet connection because the chart library is loaded from a CDN.
- No export to Excel/CSV (the report can be printed or saved as PDF from the browser).

## Future Enhancements
1. User registration and login so several people can use the system securely.
2. Category-wise monthly budgets with alerts when a limit is crossed.
3. Recurring expenses (rent, subscriptions) that are added automatically.
4. Export of reports to Excel, CSV and PDF.
5. Multiple income sources and savings goals.
6. Cloud hosting and a mobile app or Progressive Web App.
7. Email or SMS reminders for bills.
8. Receipt upload and OCR to add expenses automatically.
9. Predictive analysis to forecast next month's spending.

## Conclusion
The Salary Expenditure Management System meets its goal of giving users a simple, reliable way to track spending against their salary. It demonstrates how HTML, CSS, Flask and SQLite can be combined into a complete, useful web application, and its modular design makes it easy to extend with the enhancements listed above.
