# AI Usage Documentation

## Tools Used

- **Claude (Anthropic)** was the only AI tool I used for this project. I used it for:
  - **Boilerplate:** generating the Flask routes and the MySQL connector functions (`app.py`, `database.py`).
  - **SQL and schema design:** drafting `schema.sql` (tables, foreign keys, ENUMs, JSON columns, CHECK constraints, indexes, a view) and the JSON queries used by the dashboard.
  - **Algorithm:** writing the skill-matching percentage algorithm for the Job Match page, plus unit tests for it.
  - **Frontend:** the Jinja HTML templates and `style.css`.
  - **Debugging and workflow:** reconciling my assignment schema with the project spec, protecting my assignment database, handling the MySQL password safely, and planning the Git commits.

I did not use ChatGPT, Gemini, or Copilot for this project.

## Key Prompts

These are the prompts I actually sent (condensed where marked).

1. *"Based on my project description and the context file attached. Can you help me complete my Advanced DB Management project? Guide me step by step in how I would build out the project."* (with the Project Specification attached). This produced the *plan* for the first version: schema, Flask routes, database functions, templates, CSS, the Job Match algorithm, tests, README, and a setup guide.

### A. Boilerplate for Flask routes and MySQL connector functions

> **Prompt:** "Generate initial boilerplate for Flask routes and MySQL connector functions."

**What the response contained:** a connection helper that reads its settings from `.env`, a cursor helper that commits or rolls back, small query helpers, and one database function plus one Flask route per CRUD action. The companies table is the pattern that the other three tables repeat.

`database.py` (connection and query helpers, plus the create function for companies):

```python
DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", "3306")),
    "user": os.getenv("DB_USER", "root"),
    "password": os.getenv("DB_PASSWORD", ""),
    "database": os.getenv("DB_NAME", "job_app_tracker"),
}


def get_db():
    return mysql.connector.connect(**DB_CONFIG)


@contextmanager
def get_cursor(commit=False):
    """Yield a dictionary cursor and always close the connection.

    With commit=True the transaction is committed on success and rolled
    back if anything raises.
    """
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    try:
        yield cursor
        if commit:
            conn.commit()
    except Exception:
        if commit:
            conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()


def query_all(sql, params=()):
    with get_cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchall()


def create_company(data):
    new_id, _ = execute(
        """INSERT INTO companies (company_name, industry, website, city, state, notes)
           VALUES (%s, %s, %s, %s, %s, %s)""",
        (data["company_name"], data["industry"], data["website"],
         data["city"], data["state"], data["notes"]),
    )
    return new_id
```

`app.py` (the "add company" route):

```python
@app.route("/companies/new", methods=["GET", "POST"])
def company_new():
    values, errors = {}, {}
    if request.method == "POST":
        data, errors = validate_company(request.form)
        values = request.form.to_dict()
        if not errors:
            try:
                new_id = db.create_company(data)
                flash(f"Company “{data['company_name']}” added.", "success")
                return redirect(url_for("company_detail", company_id=new_id))
            except mysql.connector.IntegrityError as err:
                if not _is_duplicate(err):
                    raise
                errors["company_name"] = "A company with this name already exists."
    return render_template("company_form.html", values=values, errors=errors, company=None)
```

Every query uses `%s` placeholders instead of string formatting, so user input can't be turned into SQL. I later added return-type annotations to `query_all` and `query_one` myself (see "What I Changed or Decided Myself").

### B. Drafting, optimizing, and debugging SQL queries and schema constraints

> **Prompt:** "Draft, optimize, or debug complex SQL queries and schema constraints."

**What the response contained:** a `jobs` table with a foreign key delete rule, an ENUM, and CHECK constraints that protect the data and the JSON column, followed by the query that lists upcoming interviews from the `interview_data` JSON column.

`schema.sql`:

```sql
CREATE TABLE jobs (
    job_id        INT           PRIMARY KEY AUTO_INCREMENT,
    company_id    INT           NOT NULL,
    job_title     VARCHAR(100)  NOT NULL,
    job_type      ENUM('Full-time','Part-time','Contract','Internship')
                                NOT NULL DEFAULT 'Full-time',
    salary_min    INT,
    salary_max    INT,
    job_url       VARCHAR(300),
    date_posted   DATE,
    requirements  JSON,
    CONSTRAINT fk_jobs_company
        FOREIGN KEY (company_id) REFERENCES companies(company_id)
        ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT chk_salary_min_positive CHECK (salary_min IS NULL OR salary_min >= 0),
    CONSTRAINT chk_salary_range CHECK (
        salary_min IS NULL OR salary_max IS NULL OR salary_max >= salary_min),
    CONSTRAINT chk_requirements_is_array CHECK (
        requirements IS NULL OR JSON_TYPE(requirements) = 'ARRAY')
);
```

- `ON DELETE CASCADE`: deleting a company also deletes its jobs, because a job can't exist without its company.
- The CHECK constraints reject negative salaries, a maximum below the minimum, and a `requirements` value that isn't a JSON array, even if bad data bypasses the web forms.

**The debugging part.** The first version of the dashboard's upcoming-interviews query read from the `application_details` view:

```sql
-- First version (fails)
FROM application_details a,
     JSON_TABLE(a.interview_data, '$.rounds[*]' COLUMNS (...)) AS r
```

MySQL rejected it with `ERROR 1210 (HY000): Incorrect arguments to JSON_TABLE`. The fix was to join the base tables and run `JSON_TABLE` on the real `applications.interview_data` column. This is the version in `database.py`:

```sql
SELECT a.application_id, j.job_title, c.company_name,
       r.round_date, r.round_type, r.interviewer
FROM applications a
JOIN jobs      j ON j.job_id     = a.job_id
JOIN companies c ON c.company_id = j.company_id,
     JSON_TABLE(a.interview_data, '$.rounds[*]'
         COLUMNS (round_date  DATE         PATH '$.date',
                  round_type  VARCHAR(50)  PATH '$.type',
                  interviewer VARCHAR(100) PATH '$.interviewer')) AS r
WHERE r.round_date >= CURDATE()
ORDER BY r.round_date
LIMIT 5;
```

`JSON_TABLE` turns each element of the `rounds` array into its own row, so interview dates stored inside JSON can be filtered and sorted like normal columns.

### C. The skill-matching percentage algorithm for the Job Match view

> **Prompt:** "Assist in writing the skill-matching percentage algorithm for the Job Match view."

**What the response contained:** three small functions in `app.py` (clean up the typed skills, score one job, rank all jobs), plus unit tests.

```python
def normalize_skill(skill):
    """'  power   BI ' -> 'power bi' so comparisons ignore case and spacing."""
    return " ".join(str(skill).lower().split())


def parse_skills(raw):
    """Turn 'Python, SQL,  flask' (or a list) into a clean, de-duplicated list."""
    items = raw if isinstance(raw, (list, tuple)) else re.split(r"[,;\n]", raw or "")
    seen, skills = set(), []
    for item in items:
        cleaned = " ".join(str(item).split())
        key = cleaned.lower()
        if cleaned and key not in seen:
            seen.add(key)
            skills.append(cleaned)
    return skills


def calculate_match(user_skills, job_requirements):
    """match % = (required skills the user has) / (total required skills) * 100
    Returns None when the job lists no requirements (nothing to match on).
    """
    required = parse_skills(job_requirements or [])
    if not required:
        return None
    have = {normalize_skill(s) for s in user_skills}
    matched = [s for s in required if normalize_skill(s) in have]
    missing = [s for s in required if normalize_skill(s) not in have]
    percent = math.floor(len(matched) / len(required) * 100 + 0.5)  # round half up
    return {
        "matched": matched,
        "missing": missing,
        "matched_count": len(matched),
        "required_count": len(required),
        "percent": percent,
    }


def rank_jobs(user_skills, jobs, include_zero=False):
    """Attach match info to each job and sort best match first."""
    results = []
    for job in jobs:
        match = calculate_match(user_skills, job.get("requirements"))
        if match is None or (match["percent"] == 0 and not include_zero):
            continue
        results.append({**job, **match})
    results.sort(key=lambda r: (-r["percent"], -r["matched_count"], r["job_title"].lower()))
    return results
```

**Worked example** (the same one the project specification uses). With the skills `Python, SQL, Flask`:

| Job | Required skills | Result |
|---|---|---|
| Software Developer | Python, SQL, Flask | **100%** (3/3 skills) |
| Data Analyst | Python, SQL, Tableau | **67%** (2/3 skills), missing: Tableau |

Design choices in the response:

- Matching ignores upper and lower case, so `python` matches `Python`.
- Duplicate skills are removed, so typing `SQL, sql` doesn't count twice.
- A job with no listed requirements returns `None` instead of dividing by zero.
- Percentages round half up (1 of 8 skills is 12.5%, shown as 13%).
- Ties are broken by the number of matched skills, then by job title, so the order is stable.

The unit test for the spec example is `calculate_match(["Python", "SQL", "Flask"], ["Python", "SQL", "Tableau"])`, which must give `percent == 67` with `missing == ["Tableau"]`.

### D. Clarifying error messages and troubleshooting frontend HTML/CSS

> **Prompt:** "Clarify error messages and troubleshoot frontend HTML/CSS integration."

**What the response contained:** a plain-language explanation of each error, and the fix.

**Error 1: `1210 (HY000): Incorrect arguments to JSON_TABLE`.** The first argument of `JSON_TABLE` has to be a column from a real table. It can't be a column that comes from a view. The fix is shown in section 2.

**Error 2: `1045 (28000): Access denied for user 'root'@'localhost'`.** This is the error someone sees if the password in `.env` is wrong, so the app handles it with a readable page that tells them what to check, instead of a raw traceback:

```python
@app.errorhandler(mysql.connector.Error)
def database_error(err):
    app.logger.exception("Database error")
    hint = ("Check that MySQL is running, that your .env file has the right "
            "DB_USER / DB_PASSWORD, and that you have run schema.sql.")
    return render_template("error.html", title="Database error",
                           message=str(err), hint=hint), 500
```

**CSS problem: misaligned labels in the interview-round rows.** In the "Edit application" form, the labels above the Date, Type, Interviewer and Notes fields did not line up, because date pickers and dropdowns have different native heights and the grid row was aligned to the bottom. The response switched the alignment to the top and gave every control the same fixed height:

```css
/* Before */
.round-row { display: grid; grid-template-columns: 150px 150px 1fr 1.5fr auto; gap: 10px; align-items: end; }
.round-row .remove-round { margin-bottom: 14px; }

/* After */
.round-row { display: grid; grid-template-columns: 150px 150px 1fr 1.5fr auto; gap: 10px; align-items: start; }
.round-row .field { margin-bottom: 12px; }
.round-row input, .round-row select { height: 40px; }
.round-row .remove-round { margin-top: 29px; height: 40px; }
```
2. *"We had already done a sort of database setup as practice assignments... here are all of my queries on my job_tracker db schema so far. Do you think I should build off this or continue your sample data and structure?"* (condensed; I attached my assignment queries). This produced a column-by-column comparison of my assignment schema against the project spec.
3. *"I don't want to delete my current job_tracker database as we have more assignments on that specifically... Could you just rewrite the instances of your 'job_tracker' db name with 'job_app_tracker'?"* (condensed). This isolated the project database from my assignment database.
4. *"...keep the project structure, but help me add my data from the assignment after your sample data, please."* (condensed). This converted my assignment data to the project schema and instructed me on how to append it to `schema.sql`.
5. A request to fill out this documentation file using the project's AI-usage guidelines, good markdown format, and context to individual changes I made.

## What the AI Generated

- **Database (`schema.sql`):** four tables (`companies`, `jobs`, `applications`, `contacts`), two JSON columns (`jobs.requirements` as an array of skills, `applications.interview_data` as an object holding interview rounds), ENUMs, CHECK constraints, indexes, and an `application_details` view that joins applications to jobs and companies.
- **Backend (`database.py`, `app.py`):** CRUD for all four tables, search and filters, the dashboard statistics, server-side validation, and error pages.
- **Job Match:** it takes the skills I type, compares them with each job's required skills, and ranks jobs by match percentage, showing which skills I have and which are missing.
- **Frontend:** templates for every page, a reusable macros file, delete confirmation dialogs, and a form where interview rounds can be added and removed.
- **Tests:** unit tests for the matching algorithm, plus a scripted check of every page and CRUD action that Claude ran in its own environment against MySQL 8.

## Schema Reconciliation: My Assignment vs. the Project Spec

My practice-assignment schema and the project spec describe the same application, but the columns differ. After comparing them (prompt 2), I chose to follow the project spec's structure, because the grading rubric asks for JSON columns and the spec lists exact columns.

### Similarities (kept as is)

- The same four tables with the same relationship chain: `companies` → `jobs` → `applications`, and `companies` → `contacts`.
- The same primary-key pattern (`INT AUTO_INCREMENT PRIMARY KEY`) and foreign keys.
- The `companies` table is essentially the same.
- `applications` keeps `application_date` (NOT NULL), `resume_version`, and `cover_letter_sent`.
- `contacts` keeps `email`, `phone`, `linkedin_url`, and `notes`.
- The idea of an index on application status (from my indexing assignment) is kept as `idx_applications_status`.

### Differences (changed to match the spec)

| Table | My assignment schema | Project schema |
|---|---|---|
| companies | extra `created_at` timestamp | `created_at` removed; added `UNIQUE` on `company_name` to prevent duplicates |
| jobs | `job_description`, `is_active`, `created_at`; `posting_url VARCHAR(500)`; `DECIMAL(10,2)` salaries; `job_type VARCHAR(20)`; no skills column | those three extra columns removed; `posting_url` renamed `job_url`; salaries `INT`; `job_type` is an `ENUM`; **new `requirements JSON`** |
| applications | `status VARCHAR(30)`; separate `response_date`, `interview_date`, `notes`, `created_at` | `status` is an `ENUM` of six values; the extra columns are replaced by **`interview_data JSON`**, so each interview round (date, type, interviewer, notes) lives inside the JSON |
| contacts | `first_name` and `last_name`; `job_title`; `company_id NOT NULL` | single `contact_name`; `job_title` renamed `title`; `company_id` is optional |

### Constraints added beyond the spec

- `ON DELETE CASCADE` from companies to jobs and from jobs to applications, because a job cannot exist without its company, and an application cannot exist without its job.
- `ON DELETE SET NULL` for contacts, so deleting a company keeps the person but clears the link.
- CHECK constraints: salaries must be non-negative, `salary_max >= salary_min`, `requirements` must be a JSON array, and `interview_data` must be a JSON object.

### Converting my assignment data

I asked Claude to guide me in appending my assignment data to `schema.sql` after the sample data it wrote. The conversion involved:

- **Statuses:** my free-text statuses had to fit the six ENUM values (`Interview Scheduled` became `Interview`, `Phone Screen` became `Screening`).
- **Websites:** `https://` was added to each website, because the forms only accept `http://` or `https://` URLs.
- **Contact names:** first and last names were joined into `contact_name`, and `job_title` became `title`.
- **Skills:** my jobs had no skill lists, so each of my 18 jobs got a `requirements` array so that Job Match can rank them.
- **Linking by name:** rows are linked with name lookups instead of fixed ID numbers. My original script inserted applications with job IDs 8, 10, 11, 12 and 14, which don't exist on a fresh database, so that script could not rebuild the database from scratch. The new script can.
- **Rolled-back rows:** I kept the rows my own transaction practice committed (New Tech Corp and its Software Architect job, and Robert Kim). I left out Jennifer Martinez, because my savepoint rollback undid her insert.
- **Result:** the database now holds 12 companies, 29 jobs, 15 applications, and 13 contacts.

## Validation and Refactoring Applied

- **Form validation (server-side):**
  - required fields and maximum lengths matching the column sizes
  - URLs must start with `http://` or `https://`
  - email format and phone character checks
  - dates must parse, and salaries must be whole numbers with max at least min
  - dropdown values must be valid, and selected company or job IDs must exist
  - a friendly message for a duplicate company name
  - each interview round needs a date
- **Database safety:** every query is parameterized (`%s`), deletes are POST-only with a confirmation prompt, and database errors show a readable error page.
- **Separation of concerns:** all SQL lives in `database.py`; `app.py` only handles routes, validation, and the matching algorithm; JSON columns are converted to and from Python lists and dictionaries in one place.

## What Worked Well

- Comparing my assignment schema with the spec column by column caught problems I would have missed, especially the missing JSON columns and the status values that would not fit the ENUM.
- Having one complete, consistent pattern for CRUD made it easy to see how the same route, template, and database function structure repeats for each table.
- Asking for the dashboard "upcoming interviews" feature led me to learn `JSON_TABLE`, which turns a JSON array into rows so it can be queried.

## What I Changed or Decided Myself

- I decided to follow the project spec's schema rather than my assignment schema, and to keep my assignment data as extra sample data.
- I chose to keep my assignment database (`job_tracker`) untouched for later assignments, so the project uses its own database, `job_app_tracker`, and I asked Claude to rename it everywhere.
- I chose to use my existing GitHub repository, `job_application_tracker`, so the README's clone instructions use that name.
- I added `assert m is not None` to `test_job_match.py` myself, because Pylance flagged a possible `None` when the test indexes into the result of `calculate_match`. The function returns `None` for a job with no listed requirements, so the assert is correct, and it makes the test fail clearly if that ever happens unexpectedly.
- I fixed the row typing at the database query boundary in `database.py`. `query_all` and `query_one` now declare dictionary-row return types, matching the `dictionary=True` cursor, so `row["status"]` and `row["total"]` are typed as key lookups rather than tuple indexing. I added `from typing import Any, cast` and changed the two functions to:

```python
  def query_all(sql, params=()) -> list[dict[str, Any]]:
      with get_cursor() as cur:
          cur.execute(sql, params)
          return cast(list[dict[str, Any]], cur.fetchall())


  def query_one(sql, params=()) -> dict[str, Any] | None:
      with get_cursor() as cur:
          cur.execute(sql, params)
          return cast(dict[str, Any] | None, cur.fetchone())
```
- One thing to note: dict[str, Any] | None only works on Python 3.10 or newer.
    - I raised the Python requirement from 3.9 to 3.10 because of this change.
- I set up my own `.env` file for my MySQL password and kept it out of Git using `.gitignore`.

## Bugs Found and Fixed

- **`JSON_TABLE` error:** the first version of the dashboard's "upcoming interviews" query ran `JSON_TABLE` over a column of the `application_details` view, and MySQL returned `1210: Incorrect arguments to JSON_TABLE`. The fix was to join the base tables (`applications`, `jobs`, `companies`) directly. `JSON_TABLE` needs a real table column, not a view column.
- **Layout bug:** the labels in the interview-round rows were misaligned, which was fixed in `style.css`.
- **Script that could not be re-run:** my original assignment script could not recreate the database from scratch because of its hard-coded IDs (see "Linking by name" above).

## Lessons Learned

- AI-generated code has to be tested. The `JSON_TABLE` bug only showed up when the page actually ran against MySQL.
- A schema written for an earlier assignment can look "essentially the same" as the spec and still differ in ways that cost points, like missing JSON columns and ENUM values.
- Hard-coded IDs make an SQL script fragile. Looking rows up by name makes `schema.sql` safe to run on any machine, which matters because the instructor will clone and run this project.
- Passwords belong in a `.env` file that is ignored by Git, with a `.env.example` showing the format. They should never be hard-coded in the repository.
- Foreign-key delete rules (`CASCADE` vs `SET NULL`) are design decisions, not defaults. I can explain why jobs and applications are deleted with their company while contacts are kept.
- Asking the AI to explain its code and choices, and then checking that against the spec and the running application, helped me understand the project well enough to explain it myself.