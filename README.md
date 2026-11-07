## Quick Start (for graders)
1. `pip install -r requirements.txt`
2. `mysql -u root -p < schema.sql`  (creates the `job_app_tracker` database with sample data)
3. Copy `.env.example` to `.env` and set `DB_PASSWORD` to your MySQL password
   (leave it empty if your root user has no password; change `DB_USER` if you don't use root)
4. `python app.py` → open http://127.0.0.1:5000

---

# Job Application Tracker

A full-stack web app for tracking job applications, built for **COP4751 Advanced Database Management**.

- **Database:** MySQL 8 (4 tables, foreign keys, JSON columns, CHECK constraints, a view)
- **Backend:** Python 3 + Flask
- **Frontend:** HTML (Jinja templates) + CSS
- **Extra:** Job Match, which ranks jobs by how many of their required skills you have

> 🎥 **Demo video:** [`demo.mp4`](demo.mp4) *(replace with future video file name)*

---

## Features

| Page | What it does |
|------|--------------|
| **Dashboard** | Totals, applications by status, upcoming interviews, recent applications, most requested skills |
| **Companies** | List/search, detail page (with its jobs and contacts), add, edit, delete |
| **Jobs** | List/filter by type, detail page (with its applications), add, edit, delete. Required skills are stored as a JSON array |
| **Applications** | Filter by status, detail page, add, edit, delete. Interview rounds are stored in a JSON object |
| **Contacts** | List/search, detail page, add, edit, delete |
| **Job Match** | Enter your skills and get every job ranked by match %, with matched and missing skills |

All forms are validated on the server (required fields, lengths, URLs, emails, phone numbers, dates, salary range, valid dropdown choices, duplicate company names). Deletes ask for confirmation first.

---

## Setup Instructions

### 1. Prerequisites
- **Python 3.10+**: check with `python --version` (or `python3 --version` on macOS)
- **MySQL Server 8.0+**: running locally. You need the root password (or another user's password).
- **Git**

### 2. Clone the repository
```bash
git clone https://github.com/<your-username>/job_application_tracker.git
cd job_application_tracker
```

### 3. Create a virtual environment and install dependencies
**Windows (PowerShell):**
```powershell
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```
**macOS / Linux:**
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 4. Create the database
Pick **one** of these:

- **Command line:**
  ```bash
  mysql -u root -p < schema.sql
  ```
- **MySQL Workbench:** File → Open SQL Script → `schema.sql` → click the ⚡ (Execute) button.

This creates the `job_app_tracker` database, all 4 tables, the `application_details` view and sample data (12 companies, 29 jobs, 15 applications, 13 contacts).
Re-running it resets everything back to the sample data.

### 5. Configure your database password
Copy the example settings file and put your MySQL password in it:

**Windows:** `copy .env.example .env`  **macOS/Linux:** `cp .env.example .env`

Then edit `.env`:
```
DB_USER=root
DB_PASSWORD=your_mysql_password_here
```
(`.env` is in `.gitignore`, so your password is never pushed to GitHub.)

### 6. Run the app
```bash
python app.py
```
Open **http://127.0.0.1:5000** in your browser.

### 7. (Optional) Run the unit tests
```bash
python -m unittest test_job_match.py -v
```

---

## Project Structure
```
job_tracker/
├── app.py               # Flask routes, form validation, Job Match algorithm
├── database.py          # All SQL / database functions
├── schema.sql           # Creates the database, tables, view and sample data
├── test_job_match.py    # Unit tests for the matching algorithm
├── requirements.txt     # Python dependencies
├── .env.example         # Template for database settings (copy to .env)
├── templates/
│   ├── base.html               # Shared layout + navigation
│   ├── _macros.html            # Reusable form fields, badges, delete button
│   ├── dashboard.html
│   ├── companies.html   company_detail.html   company_form.html
│   ├── jobs.html        job_detail.html       job_form.html
│   ├── applications.html application_detail.html application_form.html
│   ├── contacts.html    contact_detail.html   contact_form.html
│   ├── job_match.html
│   └── error.html
├── static/
│   └── style.css
├── AI_USAGE.md          # GenAI documentation
└── README.md
```

---

## Database Design

```
companies 1 ──< jobs 1 ──< applications
    1
    └──< contacts
```

| Table | Key points |
|-------|------------|
| `companies` | `company_name` is `NOT NULL` and `UNIQUE` |
| `jobs` | FK → companies (`ON DELETE CASCADE`); `job_type` ENUM; `requirements` **JSON array**, e.g. `["Python","SQL"]`; CHECK constraints keep salaries non-negative and `salary_max >= salary_min` |
| `applications` | FK → jobs (`ON DELETE CASCADE`); `status` ENUM; `interview_data` **JSON object**, e.g. `{"rounds":[{"date":"2026-10-01","type":"Technical","interviewer":"…","notes":"…"}]}`; indexes on `status` and `application_date` |
| `contacts` | FK → companies (`ON DELETE SET NULL`), so a contact is kept when their company is deleted |

**Why these delete rules?** A job can't exist without its company, and an application can't exist without its job, so those cascade. A contact is a person you still know, so the link is just cleared.

**Advanced MySQL features used:**
- `JSON` columns with `CHECK (JSON_TYPE(...) = 'ARRAY' / 'OBJECT')` validation
- `JSON_TABLE()` turns JSON arrays into rows: it builds the dashboard's *Upcoming interviews* and *Most requested skills*, plus the Job Match skill picker
- A **view** (`application_details`) joins applications → jobs → companies
- Parameterized queries everywhere (`%s` placeholders) to prevent SQL injection

---

## Job Match Algorithm

```
match % = (job's required skills that you have) / (job's total required skills) × 100
```
1. Your skills are split on commas, trimmed, and de-duplicated. Matching ignores case, so `python` = `Python`.
2. Each job's `requirements` JSON array is compared against your skills.
3. Jobs are sorted by match % (highest first), then by number of matched skills.
4. Each result shows **Have** and **Missing** skills, e.g. *Data Analyst at Northwind Analytics: 67% (2/3 skills), Missing: Tableau*.
5. Jobs with no listed requirements are skipped. 0% matches are hidden unless you tick *Include 0% matches*.

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `Access denied for user 'root'@'localhost'` | Wrong password in `.env` |
| `Unknown database 'job_app_tracker'` | Run `schema.sql` (step 4) |
| `Can't connect to MySQL server` | Start the MySQL service (Windows: Services → MySQL80 → Start; macOS: System Settings → MySQL) |
| `ModuleNotFoundError: No module named 'flask'` | Activate the virtual environment, then run `pip install -r requirements.txt` |
| `Unknown collation 'utf8mb4_0900_ai_ci'` or JSON_TABLE errors | You're on MySQL 5.7 or MariaDB. Install MySQL 8.0+ |
| Port 5000 already in use (common on macOS: AirPlay) | Run `flask --app app run --port 5001` |
