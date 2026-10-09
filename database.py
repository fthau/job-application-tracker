"""
database.py - all MySQL access for the Job Application Tracker.

app.py never writes SQL directly; it calls the functions in this file.
Every query uses parameterized placeholders (%s) to prevent SQL injection.
"""

import json
import os
from contextlib import contextmanager

import mysql.connector
from dotenv import load_dotenv

# Read DB settings from a .env file (see .env.example) or environment variables.
load_dotenv()

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", "3306")),
    "user": os.getenv("DB_USER", "root"),
    "password": os.getenv("DB_PASSWORD", ""),
    "database": os.getenv("DB_NAME", "job_app_tracker"),
}


# ---------------------------------------------------------------------------
# Connection helpers
# ---------------------------------------------------------------------------

def get_db():
    """Open a new connection to the job_app_tracker database."""
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


def query_one(sql, params=()):
    with get_cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchone()


def execute(sql, params=()):
    """Run INSERT/UPDATE/DELETE. Returns (lastrowid, rowcount)."""
    with get_cursor(commit=True) as cur:
        cur.execute(sql, params)
        return cur.lastrowid, cur.rowcount


def _load_json(value, default):
    """MySQL JSON columns come back as str (or bytes); turn them into Python."""
    if value is None:
        return default
    if isinstance(value, (bytes, bytearray)):
        value = value.decode("utf-8")
    if isinstance(value, str):
        try:
            return json.loads(value)
        except ValueError:
            return default
    return value


def _decode_job(row):
    if row is not None:
        row["requirements"] = _load_json(row.get("requirements"), [])
    return row


def _decode_application(row):
    if row is not None:
        data = _load_json(row.get("interview_data"), {})
        row["interview_data"] = data if isinstance(data, dict) else {}
        row["rounds"] = row["interview_data"].get("rounds", [])
    return row


def _like(term):
    return f"%{term}%"


# ---------------------------------------------------------------------------
# COMPANIES
# ---------------------------------------------------------------------------

def get_companies(search=None):
    sql = """
        SELECT c.*,
               COUNT(DISTINCT j.job_id)      AS job_count,
               COUNT(DISTINCT ct.contact_id) AS contact_count
        FROM companies c
        LEFT JOIN jobs     j  ON j.company_id  = c.company_id
        LEFT JOIN contacts ct ON ct.company_id = c.company_id
    """
    params = ()
    if search:
        sql += """ WHERE c.company_name LIKE %s OR c.industry LIKE %s
                   OR c.city LIKE %s OR c.state LIKE %s """
        params = (_like(search),) * 4
    sql += " GROUP BY c.company_id ORDER BY c.company_name"
    return query_all(sql, params)


def get_company(company_id):
    return query_one("SELECT * FROM companies WHERE company_id = %s", (company_id,))


def get_company_options():
    """(id, name) pairs for dropdown menus."""
    return query_all("SELECT company_id, company_name FROM companies ORDER BY company_name")


def create_company(data):
    new_id, _ = execute(
        """INSERT INTO companies (company_name, industry, website, city, state, notes)
           VALUES (%s, %s, %s, %s, %s, %s)""",
        (data["company_name"], data["industry"], data["website"],
         data["city"], data["state"], data["notes"]),
    )
    return new_id


def update_company(company_id, data):
    _, count = execute(
        """UPDATE companies
           SET company_name = %s, industry = %s, website = %s,
               city = %s, state = %s, notes = %s
           WHERE company_id = %s""",
        (data["company_name"], data["industry"], data["website"],
         data["city"], data["state"], data["notes"], company_id),
    )
    return count


def delete_company(company_id):
    _, count = execute("DELETE FROM companies WHERE company_id = %s", (company_id,))
    return count


# ---------------------------------------------------------------------------
# JOBS
# ---------------------------------------------------------------------------

JOB_SELECT = """
    SELECT j.*, c.company_name,
           (SELECT COUNT(*) FROM applications a WHERE a.job_id = j.job_id) AS application_count
    FROM jobs j
    JOIN companies c ON c.company_id = j.company_id
"""


def get_jobs(search=None, job_type=None, company_id=None):
    conditions, params = [], []
    if search:
        conditions.append("(j.job_title LIKE %s OR c.company_name LIKE %s)")
        params += [_like(search), _like(search)]
    if job_type:
        conditions.append("j.job_type = %s")
        params.append(job_type)
    if company_id:
        conditions.append("j.company_id = %s")
        params.append(company_id)
    sql = JOB_SELECT
    if conditions:
        sql += " WHERE " + " AND ".join(conditions)
    sql += " ORDER BY j.date_posted DESC, j.job_id DESC"
    return [_decode_job(r) for r in query_all(sql, tuple(params))]


def get_job(job_id):
    return _decode_job(query_one(JOB_SELECT + " WHERE j.job_id = %s", (job_id,)))


def get_job_options():
    return query_all(
        """SELECT j.job_id, j.job_title, c.company_name
           FROM jobs j JOIN companies c ON c.company_id = j.company_id
           ORDER BY c.company_name, j.job_title"""
    )


def _job_params(data):
    return (data["company_id"], data["job_title"], data["job_type"],
            data["salary_min"], data["salary_max"], data["job_url"],
            data["date_posted"], json.dumps(data["requirements"]))


def create_job(data):
    new_id, _ = execute(
        """INSERT INTO jobs (company_id, job_title, job_type, salary_min, salary_max,
                             job_url, date_posted, requirements)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
        _job_params(data),
    )
    return new_id


def update_job(job_id, data):
    _, count = execute(
        """UPDATE jobs
           SET company_id = %s, job_title = %s, job_type = %s, salary_min = %s,
               salary_max = %s, job_url = %s, date_posted = %s, requirements = %s
           WHERE job_id = %s""",
        _job_params(data) + (job_id,),
    )
    return count


def delete_job(job_id):
    _, count = execute("DELETE FROM jobs WHERE job_id = %s", (job_id,))
    return count


def get_jobs_for_matching():
    """Every job with its requirements and whether you've already applied."""
    return get_jobs()


def get_all_skills():
    """Distinct skills across all jobs, pulled out of the JSON arrays with JSON_TABLE."""
    rows = query_all(
        """SELECT MIN(s.skill) AS skill, COUNT(*) AS job_count
           FROM jobs j,
                JSON_TABLE(j.requirements, '$[*]'
                           COLUMNS (skill VARCHAR(100) PATH '$')) AS s
           WHERE s.skill IS NOT NULL AND s.skill <> ''
           GROUP BY LOWER(s.skill)
           ORDER BY job_count DESC, skill"""
    )
    return rows


# ---------------------------------------------------------------------------
# APPLICATIONS  (reads use the application_details view)
# ---------------------------------------------------------------------------

def get_applications(status=None, job_id=None, search=None):
    conditions, params = [], []
    if status:
        conditions.append("status = %s")
        params.append(status)
    if job_id:
        conditions.append("job_id = %s")
        params.append(job_id)
    if search:
        conditions.append("(job_title LIKE %s OR company_name LIKE %s)")
        params += [_like(search), _like(search)]
    sql = "SELECT * FROM application_details"
    if conditions:
        sql += " WHERE " + " AND ".join(conditions)
    sql += " ORDER BY application_date DESC, application_id DESC"
    return [_decode_application(r) for r in query_all(sql, tuple(params))]


def get_application(application_id):
    return _decode_application(
        query_one("SELECT * FROM application_details WHERE application_id = %s",
                  (application_id,))
    )


def _application_params(data):
    interview = json.dumps(data["interview_data"]) if data["interview_data"] else None
    return (data["job_id"], data["application_date"], data["status"],
            data["resume_version"], data["cover_letter_sent"], interview)


def create_application(data):
    new_id, _ = execute(
        """INSERT INTO applications (job_id, application_date, status, resume_version,
                                     cover_letter_sent, interview_data)
           VALUES (%s, %s, %s, %s, %s, %s)""",
        _application_params(data),
    )
    return new_id


def update_application(application_id, data):
    _, count = execute(
        """UPDATE applications
           SET job_id = %s, application_date = %s, status = %s, resume_version = %s,
               cover_letter_sent = %s, interview_data = %s
           WHERE application_id = %s""",
        _application_params(data) + (application_id,),
    )
    return count


def delete_application(application_id):
    _, count = execute("DELETE FROM applications WHERE application_id = %s",
                       (application_id,))
    return count


# ---------------------------------------------------------------------------
# CONTACTS
# ---------------------------------------------------------------------------

CONTACT_SELECT = """
    SELECT ct.*, c.company_name
    FROM contacts ct
    LEFT JOIN companies c ON c.company_id = ct.company_id
"""


def get_contacts(search=None, company_id=None):
    conditions, params = [], []
    if search:
        conditions.append("(ct.contact_name LIKE %s OR ct.title LIKE %s OR c.company_name LIKE %s)")
        params += [_like(search)] * 3
    if company_id:
        conditions.append("ct.company_id = %s")
        params.append(company_id)
    sql = CONTACT_SELECT
    if conditions:
        sql += " WHERE " + " AND ".join(conditions)
    sql += " ORDER BY ct.contact_name"
    return query_all(sql, tuple(params))


def get_contact(contact_id):
    return query_one(CONTACT_SELECT + " WHERE ct.contact_id = %s", (contact_id,))


def _contact_params(data):
    return (data["company_id"], data["contact_name"], data["title"], data["email"],
            data["phone"], data["linkedin_url"], data["notes"])


def create_contact(data):
    new_id, _ = execute(
        """INSERT INTO contacts (company_id, contact_name, title, email, phone,
                                 linkedin_url, notes)
           VALUES (%s, %s, %s, %s, %s, %s, %s)""",
        _contact_params(data),
    )
    return new_id


def update_contact(contact_id, data):
    _, count = execute(
        """UPDATE contacts
           SET company_id = %s, contact_name = %s, title = %s, email = %s,
               phone = %s, linkedin_url = %s, notes = %s
           WHERE contact_id = %s""",
        _contact_params(data) + (contact_id,),
    )
    return count


def delete_contact(contact_id):
    _, count = execute("DELETE FROM contacts WHERE contact_id = %s", (contact_id,))
    return count


# ---------------------------------------------------------------------------
# DASHBOARD
# ---------------------------------------------------------------------------

def get_dashboard_stats():
    counts = query_one(
        """SELECT (SELECT COUNT(*) FROM companies)    AS companies,
                  (SELECT COUNT(*) FROM jobs)         AS jobs,
                  (SELECT COUNT(*) FROM applications) AS applications,
                  (SELECT COUNT(*) FROM contacts)     AS contacts"""
    )

    by_status = {row["status"]: row["total"] for row in query_all(
        "SELECT status, COUNT(*) AS total FROM applications GROUP BY status"
    )}

    recent = [_decode_application(r) for r in query_all(
        """SELECT * FROM application_details
           ORDER BY application_date DESC, application_id DESC LIMIT 5"""
    )]

    # JSON_TABLE turns each application's interview_data.rounds array into rows.
    upcoming = query_all(
        """SELECT a.application_id, j.job_title, c.company_name,
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
           LIMIT 5"""
    )

    top_skills = get_all_skills()[:8]

    return {"counts": counts, "by_status": by_status, "recent": recent,
            "upcoming": upcoming, "top_skills": top_skills}
