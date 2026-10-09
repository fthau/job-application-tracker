"""
app.py - Flask routes for the Job Application Tracker.

Pages:
    /                       Dashboard (statistics overview)
    /companies ...          Companies CRUD
    /jobs ...               Jobs CRUD
    /applications ...       Applications CRUD
    /contacts ...           Contacts CRUD
    /job-match              Rank jobs by how well they match your skills

Run with:  python app.py   then open http://127.0.0.1:5000
"""

import math
import os
import re
from datetime import datetime

import mysql.connector
from mysql.connector import errorcode
from flask import Flask, abort, flash, redirect, render_template, request, url_for

import database as db

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "dev-only-change-me")

JOB_TYPES = ["Full-time", "Part-time", "Contract", "Internship"]
STATUSES = ["Applied", "Screening", "Interview", "Offer", "Rejected", "Withdrawn"]
INTERVIEW_TYPES = ["Phone Screen", "Technical", "Behavioral", "Panel", "Onsite", "Final"]

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PHONE_RE = re.compile(r"^[0-9+()\-.\s]{7,20}$")


# ===========================================================================
# Template helpers
# ===========================================================================

@app.context_processor
def inject_constants():
    return {"JOB_TYPES": JOB_TYPES, "STATUSES": STATUSES,
            "INTERVIEW_TYPES": INTERVIEW_TYPES}


@app.template_filter("money")
def money(value):
    return f"${value:,.0f}" if value is not None else ""


@app.template_filter("salary_range")
def salary_range(job):
    lo, hi = job.get("salary_min"), job.get("salary_max")
    if lo is None and hi is None:
        return "Not listed"
    if lo is not None and hi is not None:
        return f"{money(lo)} – {money(hi)}"
    return f"{money(lo or hi)}"


@app.template_filter("nice_date")
def nice_date(value):
    if not value:
        return ""
    if isinstance(value, str):
        try:
            value = datetime.strptime(value, "%Y-%m-%d").date()
        except ValueError:
            return value
    return value.strftime("%b %d, %Y")


# ===========================================================================
# Form validation helpers
# Each validate_* function returns (clean_data, errors). errors maps a field
# name to a message; an empty dict means the form is valid.
# ===========================================================================

def _text(form, name, label, max_len, errors, required=False):
    value = (form.get(name) or "").strip()
    if required and not value:
        errors[name] = f"{label} is required."
    elif len(value) > max_len:
        errors[name] = f"{label} must be {max_len} characters or fewer."
    return value or None


def _url(form, name, label, max_len, errors):
    value = _text(form, name, label, max_len, errors)
    if value and not value.lower().startswith(("http://", "https://")):
        errors[name] = f"{label} must start with http:// or https://"
    return value


def _date(form, name, label, errors, required=False):
    value = (form.get(name) or "").strip()
    if not value:
        if required:
            errors[name] = f"{label} is required."
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        errors[name] = f"{label} must be a valid date (YYYY-MM-DD)."
        return None


def _int(form, name, label, errors):
    value = (form.get(name) or "").strip().replace(",", "").replace("$", "")
    if not value:
        return None
    if not value.isdigit():
        errors[name] = f"{label} must be a whole, positive number."
        return None
    return int(value)


def _choice(form, name, label, choices, errors):
    value = form.get(name)
    if value not in choices:
        errors[name] = f"Please choose a valid {label.lower()}."
    return value


def _foreign_key(form, name, label, valid_ids, errors, required=True):
    value = (form.get(name) or "").strip()
    if not value:
        if required:
            errors[name] = f"{label} is required."
        return None
    if not value.isdigit() or int(value) not in valid_ids:
        errors[name] = f"Please choose a valid {label.lower()}."
        return None
    return int(value)


def validate_company(form):
    errors = {}
    data = {
        "company_name": _text(form, "company_name", "Company name", 100, errors, required=True),
        "industry": _text(form, "industry", "Industry", 50, errors),
        "website": _url(form, "website", "Website", 200, errors),
        "city": _text(form, "city", "City", 50, errors),
        "state": _text(form, "state", "State", 50, errors),
        "notes": _text(form, "notes", "Notes", 5000, errors),
    }
    return data, errors


def validate_job(form):
    errors = {}
    company_ids = {c["company_id"] for c in db.get_company_options()}
    data = {
        "company_id": _foreign_key(form, "company_id", "Company", company_ids, errors),
        "job_title": _text(form, "job_title", "Job title", 100, errors, required=True),
        "job_type": _choice(form, "job_type", "Job type", JOB_TYPES, errors),
        "salary_min": _int(form, "salary_min", "Minimum salary", errors),
        "salary_max": _int(form, "salary_max", "Maximum salary", errors),
        "job_url": _url(form, "job_url", "Job URL", 300, errors),
        "date_posted": _date(form, "date_posted", "Date posted", errors),
        "requirements": parse_skills(form.get("requirements", "")),
    }
    if (data["salary_min"] is not None and data["salary_max"] is not None
            and data["salary_max"] < data["salary_min"]):
        errors["salary_max"] = "Maximum salary must be greater than or equal to the minimum."
    if any(len(skill) > 100 for skill in data["requirements"]):
        errors["requirements"] = "Each skill must be 100 characters or fewer."
    return data, errors


def parse_interview_rounds(form):
    """Collect the repeating interview-round rows into a list of dicts."""
    dates = form.getlist("round_date")
    types = form.getlist("round_type")
    people = form.getlist("round_interviewer")
    notes = form.getlist("round_notes")
    rounds, errors = [], {}
    for i in range(len(dates)):
        row = {
            "date": (dates[i] if i < len(dates) else "").strip(),
            "type": (types[i] if i < len(types) else "").strip(),
            "interviewer": (people[i] if i < len(people) else "").strip()[:100],
            "notes": (notes[i] if i < len(notes) else "").strip()[:1000],
        }
        if not any(row.values()):
            continue  # skip completely blank rows
        if not row["date"]:
            errors["interview_data"] = "Each interview round needs a date."
        else:
            try:
                datetime.strptime(row["date"], "%Y-%m-%d")
            except ValueError:
                errors["interview_data"] = "Interview dates must be valid dates."
        if row["type"] and row["type"] not in INTERVIEW_TYPES:
            errors["interview_data"] = "Please choose a valid interview type."
        rounds.append(row)
    rounds.sort(key=lambda r: r["date"])
    return rounds, errors


def validate_application(form):
    errors = {}
    job_ids = {j["job_id"] for j in db.get_job_options()}
    rounds, round_errors = parse_interview_rounds(form)
    errors.update(round_errors)
    data = {
        "job_id": _foreign_key(form, "job_id", "Job", job_ids, errors),
        "application_date": _date(form, "application_date", "Application date", errors,
                                  required=True),
        "status": _choice(form, "status", "Status", STATUSES, errors),
        "resume_version": _text(form, "resume_version", "Resume version", 50, errors),
        "cover_letter_sent": form.get("cover_letter_sent") == "on",
        "interview_data": {"rounds": rounds} if rounds else None,
    }
    return data, errors


def validate_contact(form):
    errors = {}
    company_ids = {c["company_id"] for c in db.get_company_options()}
    data = {
        "company_id": _foreign_key(form, "company_id", "Company", company_ids, errors,
                                   required=False),
        "contact_name": _text(form, "contact_name", "Name", 100, errors, required=True),
        "title": _text(form, "title", "Title", 100, errors),
        "email": _text(form, "email", "Email", 100, errors),
        "phone": _text(form, "phone", "Phone", 20, errors),
        "linkedin_url": _url(form, "linkedin_url", "LinkedIn URL", 200, errors),
        "notes": _text(form, "notes", "Notes", 5000, errors),
    }
    if data["email"] and "email" not in errors and not EMAIL_RE.match(data["email"]):
        errors["email"] = "Please enter a valid email address."
    if data["phone"] and "phone" not in errors and not PHONE_RE.match(data["phone"]):
        errors["phone"] = "Phone may contain only digits, spaces, and + ( ) - ."
    return data, errors


def _is_duplicate(err):
    return err.errno == errorcode.ER_DUP_ENTRY


# ===========================================================================
# Job Match algorithm
# ===========================================================================

def normalize_skill(skill):
    """'  power   BI ' -> 'power bi' so comparisons ignore case and spacing."""
    return " ".join(str(skill).lower().split())


def parse_skills(raw):
    """Turn 'Python, SQL,  flask' (or a list) into a clean, de-duplicated list.

    Keeps the first spelling the user typed, removes blanks and duplicates
    (case-insensitive). Commas, semicolons and new lines all separate skills.
    """
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
    """Compare the user's skills with one job's required skills.

    match % = (required skills the user has) / (total required skills) * 100
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


# ===========================================================================
# Dashboard
# ===========================================================================

@app.route("/")
def dashboard():
    stats = db.get_dashboard_stats()
    by_status = stats["by_status"]
    total = stats["counts"]["applications"] or 0
    interviews_or_better = by_status.get("Interview", 0) + by_status.get("Offer", 0)
    summary = {
        "active": sum(by_status.get(s, 0) for s in ("Applied", "Screening", "Interview")),
        "offers": by_status.get("Offer", 0),
        "interview_rate": round(interviews_or_better / total * 100) if total else 0,
    }
    return render_template("dashboard.html", stats=stats, summary=summary)


# ===========================================================================
# Companies CRUD
# ===========================================================================

@app.route("/companies")
def companies():
    search = request.args.get("q", "").strip()
    return render_template("companies.html", companies=db.get_companies(search), search=search)


@app.route("/companies/<int:company_id>")
def company_detail(company_id):
    company = db.get_company(company_id) or abort(404)
    return render_template("company_detail.html", company=company,
                           jobs=db.get_jobs(company_id=company_id),
                           contacts=db.get_contacts(company_id=company_id))


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


@app.route("/companies/<int:company_id>/edit", methods=["GET", "POST"])
def company_edit(company_id):
    company = db.get_company(company_id) or abort(404)
    values, errors = company, {}
    if request.method == "POST":
        data, errors = validate_company(request.form)
        values = request.form.to_dict()
        if not errors:
            try:
                db.update_company(company_id, data)
                flash("Company updated.", "success")
                return redirect(url_for("company_detail", company_id=company_id))
            except mysql.connector.IntegrityError as err:
                if not _is_duplicate(err):
                    raise
                errors["company_name"] = "A company with this name already exists."
    return render_template("company_form.html", values=values, errors=errors, company=company)


@app.post("/companies/<int:company_id>/delete")
def company_delete(company_id):
    company = db.get_company(company_id) or abort(404)
    db.delete_company(company_id)
    flash(f"Company “{company['company_name']}” and its jobs/applications were deleted.",
          "success")
    return redirect(url_for("companies"))


# ===========================================================================
# Jobs CRUD
# ===========================================================================

@app.route("/jobs")
def jobs():
    search = request.args.get("q", "").strip()
    job_type = request.args.get("type", "")
    job_type = job_type if job_type in JOB_TYPES else ""
    return render_template("jobs.html", jobs=db.get_jobs(search, job_type),
                           search=search, job_type=job_type)


@app.route("/jobs/<int:job_id>")
def job_detail(job_id):
    job = db.get_job(job_id) or abort(404)
    return render_template("job_detail.html", job=job,
                           applications=db.get_applications(job_id=job_id))


def _job_form_values(job):
    """DB row -> values the form expects (requirements list -> 'A, B, C')."""
    return {**job, "requirements": ", ".join(job["requirements"])}


@app.route("/jobs/new", methods=["GET", "POST"])
def job_new():
    values = {"company_id": request.args.get("company_id", ""), "job_type": "Full-time"}
    errors = {}
    if request.method == "POST":
        data, errors = validate_job(request.form)
        values = request.form.to_dict()
        if not errors:
            new_id = db.create_job(data)
            flash(f"Job “{data['job_title']}” added.", "success")
            return redirect(url_for("job_detail", job_id=new_id))
    return render_template("job_form.html", values=values, errors=errors, job=None,
                           companies=db.get_company_options())


@app.route("/jobs/<int:job_id>/edit", methods=["GET", "POST"])
def job_edit(job_id):
    job = db.get_job(job_id) or abort(404)
    values, errors = _job_form_values(job), {}
    if request.method == "POST":
        data, errors = validate_job(request.form)
        values = request.form.to_dict()
        if not errors:
            db.update_job(job_id, data)
            flash("Job updated.", "success")
            return redirect(url_for("job_detail", job_id=job_id))
    return render_template("job_form.html", values=values, errors=errors, job=job,
                           companies=db.get_company_options())


@app.post("/jobs/<int:job_id>/delete")
def job_delete(job_id):
    job = db.get_job(job_id) or abort(404)
    db.delete_job(job_id)
    flash(f"Job “{job['job_title']}” and its applications were deleted.", "success")
    return redirect(url_for("jobs"))


# ===========================================================================
# Applications CRUD
# ===========================================================================

@app.route("/applications")
def applications():
    status = request.args.get("status", "")
    status = status if status in STATUSES else ""
    search = request.args.get("q", "").strip()
    return render_template("applications.html",
                           applications=db.get_applications(status=status, search=search),
                           status=status, search=search)


@app.route("/applications/<int:application_id>")
def application_detail(application_id):
    application = db.get_application(application_id) or abort(404)
    return render_template("application_detail.html", app_row=application)


@app.route("/applications/new", methods=["GET", "POST"])
def application_new():
    values = {"job_id": request.args.get("job_id", ""), "status": "Applied",
              "application_date": datetime.now().date().isoformat()}
    rounds, errors = [], {}
    if request.method == "POST":
        data, errors = validate_application(request.form)
        values = request.form.to_dict()
        rounds = (data["interview_data"] or {}).get("rounds", [])
        if not errors:
            new_id = db.create_application(data)
            flash("Application added.", "success")
            return redirect(url_for("application_detail", application_id=new_id))
    return render_template("application_form.html", values=values, rounds=rounds,
                           errors=errors, app_row=None, jobs=db.get_job_options())


@app.route("/applications/<int:application_id>/edit", methods=["GET", "POST"])
def application_edit(application_id):
    application = db.get_application(application_id) or abort(404)
    values, rounds, errors = application, application["rounds"], {}
    if request.method == "POST":
        data, errors = validate_application(request.form)
        values = request.form.to_dict()
        rounds = (data["interview_data"] or {}).get("rounds", [])
        if not errors:
            db.update_application(application_id, data)
            flash("Application updated.", "success")
            return redirect(url_for("application_detail", application_id=application_id))
    return render_template("application_form.html", values=values, rounds=rounds,
                           errors=errors, app_row=application, jobs=db.get_job_options())


@app.post("/applications/<int:application_id>/delete")
def application_delete(application_id):
    db.get_application(application_id) or abort(404)
    db.delete_application(application_id)
    flash("Application deleted.", "success")
    return redirect(url_for("applications"))


# ===========================================================================
# Contacts CRUD
# ===========================================================================

@app.route("/contacts")
def contacts():
    search = request.args.get("q", "").strip()
    return render_template("contacts.html", contacts=db.get_contacts(search), search=search)


@app.route("/contacts/<int:contact_id>")
def contact_detail(contact_id):
    contact = db.get_contact(contact_id) or abort(404)
    return render_template("contact_detail.html", contact=contact)


@app.route("/contacts/new", methods=["GET", "POST"])
def contact_new():
    values, errors = {"company_id": request.args.get("company_id", "")}, {}
    if request.method == "POST":
        data, errors = validate_contact(request.form)
        values = request.form.to_dict()
        if not errors:
            new_id = db.create_contact(data)
            flash(f"Contact “{data['contact_name']}” added.", "success")
            return redirect(url_for("contact_detail", contact_id=new_id))
    return render_template("contact_form.html", values=values, errors=errors, contact=None,
                           companies=db.get_company_options())


@app.route("/contacts/<int:contact_id>/edit", methods=["GET", "POST"])
def contact_edit(contact_id):
    contact = db.get_contact(contact_id) or abort(404)
    values, errors = contact, {}
    if request.method == "POST":
        data, errors = validate_contact(request.form)
        values = request.form.to_dict()
        if not errors:
            db.update_contact(contact_id, data)
            flash("Contact updated.", "success")
            return redirect(url_for("contact_detail", contact_id=contact_id))
    return render_template("contact_form.html", values=values, errors=errors, contact=contact,
                           companies=db.get_company_options())


@app.post("/contacts/<int:contact_id>/delete")
def contact_delete(contact_id):
    contact = db.get_contact(contact_id) or abort(404)
    db.delete_contact(contact_id)
    flash(f"Contact “{contact['contact_name']}” deleted.", "success")
    return redirect(url_for("contacts"))


# ===========================================================================
# Job Match
# ===========================================================================

@app.route("/job-match")
def job_match():
    raw = request.args.get("skills", "")
    show_all = request.args.get("show_all") == "1"
    user_skills = parse_skills(raw)
    results = rank_jobs(user_skills, db.get_jobs_for_matching(), show_all) if user_skills else []
    return render_template("job_match.html", raw=raw, user_skills=user_skills,
                           results=results, show_all=show_all,
                           all_skills=db.get_all_skills())


# ===========================================================================
# Error pages
# ===========================================================================

@app.errorhandler(404)
def not_found(_err):
    return render_template("error.html", title="Page not found",
                           message="That record or page doesn't exist."), 404


@app.errorhandler(mysql.connector.Error)
def database_error(err):
    app.logger.exception("Database error")
    hint = ("Check that MySQL is running, that your .env file has the right "
            "DB_USER / DB_PASSWORD, and that you have run schema.sql.")
    return render_template("error.html", title="Database error",
                           message=str(err), hint=hint), 500


if __name__ == "__main__":
    app.run(debug=True)
