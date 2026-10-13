import re
import time
import requests

from config import (
    ADZUNA_APP_ID,
    ADZUNA_APP_KEY,
    ADZUNA_COUNTRY,
    ADZUNA_BASE_URL,
)


# ============================================================
# HELPERS
# ============================================================

def clean_text(value):
    if value is None:
        return ""
    return str(value).strip()


def normalize_key(value):
    value = clean_text(value).lower()
    value = re.sub(r"[^a-z0-9+#.\- ]+", " ", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def unique_list(values):
    result = []
    seen = set()

    for value in values:
        value = clean_text(value)
        if not value:
            continue

        key = normalize_key(value)
        if key in seen:
            continue

        seen.add(key)
        result.append(value)

    return result


def format_salary(salary_min, salary_max):
    if salary_min and salary_max:
        try:
            s_min = int(float(salary_min))
            s_max = int(float(salary_max))
            return f"INR {s_min:,} - {s_max:,} / yr"
        except Exception:
            return f"INR {salary_min} - {salary_max}"
    elif salary_min:
        try:
            s_min = int(float(salary_min))
            return f"From INR {s_min:,} / yr"
        except Exception:
            return f"From INR {salary_min}"
    elif salary_max:
        try:
            s_max = int(float(salary_max))
            return f"Up to INR {s_max:,} / yr"
        except Exception:
            return f"Up to INR {salary_max}"
    return "Not disclosed"


def format_date(iso_date):
    if not iso_date:
        return ""
    # Format e.g. "2026-10-08T14:32:00Z" -> "Oct 08, 2026"
    try:
        parts = iso_date.split("T")[0].split("-")
        if len(parts) == 3:
            year, month, day = parts
            months = [
                "", "Jan", "Feb", "Mar", "Apr", "May", "Jun",
                "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"
            ]
            m_idx = int(month)
            if 1 <= m_idx <= 12:
                return f"{months[m_idx]} {int(day):02d}, {year}"
    except Exception:
        pass
    return iso_date.split("T")[0] if "T" in str(iso_date) else str(iso_date)


# ============================================================
# ADZUNA REQUEST (WITH RETRY & REGIONAL PARAMETERS)
# ============================================================

def adzuna_request(query, limit=20, where="Tamil Nadu", max_days=30):
    if not ADZUNA_APP_ID or not ADZUNA_APP_KEY:
        return []

    endpoint = f"{ADZUNA_BASE_URL}/jobs/{ADZUNA_COUNTRY}/search/1"

    params = {
        "app_id": ADZUNA_APP_ID,
        "app_key": ADZUNA_APP_KEY,
        "results_per_page": min(max(limit, 1), 20),
        "what": query,
        "max_days_old": max_days,
        "sort_by": "date",
    }

    if where:
        params["where"] = where

    for attempt in range(2):
        try:
            response = requests.get(endpoint, params=params, timeout=15)
            response.raise_for_status()
            data = response.json()
            break
        except Exception as error:
            if attempt == 0:
                time.sleep(1.2)
                continue
            print("ADZUNA REQUEST ERROR:", repr(error))
            return []

    results = []
    for item in data.get("results", []):
        results.append({
            "id": item.get("id"),
            "title": clean_text(item.get("title")),
            "company": clean_text(item.get("company", {}).get("display_name", "")),
            "location": clean_text(item.get("location", {}).get("display_name", "")),
            "description": clean_text(item.get("description")),
            "salary_min": item.get("salary_min"),
            "salary_max": item.get("salary_max"),
            "created": item.get("created"),
            "url": clean_text(item.get("redirect_url") or item.get("url")),
        })

    return results


# ============================================================
# SENIOR & UNSUITABLE JOB FILTER
# ============================================================

SENIOR_TITLE_TERMS = [
    r"\bsenior\b", r"\bsr\.?\b", r"\blead\b", r"\bprincipal\b", r"\bmanager\b",
    r"\barchitect\b", r"\bdirector\b", r"\bhead\b", r"\bvp\b", r"\bavp\b",
    r"\bchief\b", r"\bconsultant\b", r"\bspecialist\b", r"\bexpert\b", r"\bstaff\b"
]

COMPETING_TECHNOLOGIES = [
    "java", ".net", "dotnet", "c#", "php", "angular", "salesforce", "sap",
    "ruby", "ios", "android", "flutter", "golang", "scala", "c++", "abap"
]


def job_is_unsuitable(job, candidate_skills_norm):
    """
    Filters out jobs that are senior, lead, managerial, or require
    high experience, as well as jobs demanding a primary tech stack
    that the candidate does not have.
    """
    title_lower = clean_text(job.get("title", "")).lower()
    desc_lower = clean_text(job.get("description", "")).lower()

    # 1. Reject senior titles
    for pattern in SENIOR_TITLE_TERMS:
        if re.search(pattern, title_lower):
            return True

    # 2. Reject jobs where the title focuses on an unrelated technology
    for tech in COMPETING_TECHNOLOGIES:
        if tech not in candidate_skills_norm:
            # Check if this technology is in title as primary requirement
            pattern = r"\b" + re.escape(tech) + r"\b"
            if re.search(pattern, title_lower):
                return True

    # 3. Reject jobs requiring 3 or more years of experience
    exp_matches = re.findall(
        r"(\d+)\+?\s*(?:to|-)?\s*(\d+)?\s*(?:years?|yrs?)(?:\s+of)?\s+experience",
        desc_lower
    )
    for m in exp_matches:
        try:
            years = int(m[0])
            if years >= 3:
                return True
        except Exception:
            pass

    min_exp_match = re.search(
        r"(?:minimum|min|at\s*least)\s*(\d+)\+?\s*(?:years?|yrs?)",
        desc_lower
    )
    if min_exp_match:
        try:
            years = int(min_exp_match.group(1))
            if years >= 3:
                return True
        except Exception:
            pass

    return False


# ============================================================
# RESUME RELEVANCE SCORING
# ============================================================

def calculate_job_relevance(job, resume_skills, probable_roles):
    """
    Calculates actual match score and identifies matched skills
    between the candidate profile and the vacancy.
    """
    title_norm = normalize_key(job.get("title", ""))
    desc_norm = normalize_key(job.get("description", ""))
    searchable_text = title_norm + " " + desc_norm

    matched_skills = []
    skill_score = 0

    for skill in resume_skills:
        skill_norm = normalize_key(skill)
        if not skill_norm or len(skill_norm) < 2:
            continue

        # Match compound or exact word
        pattern = r"\b" + re.escape(skill_norm) + r"\b"
        if re.search(pattern, searchable_text):
            matched_skills.append(skill)
            skill_score += 15
            # Extra weight if skill is in title
            if re.search(pattern, title_norm):
                skill_score += 25

    # Role matching
    role_score = 0
    for role in probable_roles:
        role_norm = normalize_key(role)
        if not role_norm:
            continue

        if role_norm in title_norm:
            role_score += 40
        else:
            role_words = [w for w in role_norm.split() if len(w) > 3]
            for w in role_words:
                if w in title_norm:
                    role_score += 15

    # Entry-level / fresher bonus
    fresher_bonus = 0
    if any(term in searchable_text for term in ["fresher", "entry level", "junior", "intern", "trainee", "associate"]):
        fresher_bonus = 20

    total_score = skill_score + role_score + fresher_bonus
    return total_score, unique_list(matched_skills)


# ============================================================
# RESUME-BASED TAMIL NADU VACANCY FINDER
#
# IMPORTANT:
# TARGET COMPANY IS NEVER USED HERE.
# ONLY RESUME SKILLS AND PROBABLE ROLES ARE USED.
# LOCATION IS RESTRICTED STRICTLY TO TAMIL NADU.
# ============================================================

def get_resume_based_vacancies(resume_skills, probable_roles):
    resume_skills = unique_list(resume_skills)
    probable_roles = unique_list(probable_roles)

    if not resume_skills and not probable_roles:
        return []

    candidate_skills_norm = {normalize_key(s) for s in resume_skills}

    # Generate targeted search queries for Tamil Nadu
    queries = []

    # 1. Search probable entry-level roles
    for role in probable_roles[:3]:
        if role:
            queries.append(role)

    # 2. Search primary distinctive skills
    for skill in resume_skills[:4]:
        norm = normalize_key(skill)
        if norm not in {"html", "css", "sqlite"} and len(norm) > 2:
            queries.append(skill)

    # 3. Entry-level role combination
    if probable_roles:
        queries.append(f"{probable_roles[0]} Fresher")

    queries = unique_list(queries)

    all_jobs = []
    seen = set()

    for query in queries[:6]:
        try:
            jobs = adzuna_request(
                query=query,
                limit=15,
                where="Tamil Nadu",
                max_days=30
            )
        except Exception as error:
            print("VACANCY FETCH ERROR FOR QUERY:", query, error)
            continue

        for job in jobs:
            job_url = clean_text(job.get("url"))
            job_id = clean_text(str(job.get("id") or job_url))
            if not job_id:
                job_id = normalize_key(job.get("title", "")) + "|" + normalize_key(job.get("company", ""))

            if job_id in seen or (job_url and job_url in seen):
                continue

            seen.add(job_id)
            if job_url:
                seen.add(job_url)

            # Filter out senior, manager, and competing-tech jobs
            if job_is_unsuitable(job, candidate_skills_norm):
                continue

            # Calculate resume relevance
            score, matched_skills = calculate_job_relevance(
                job,
                resume_skills,
                probable_roles
            )

            # Must have at least one matched skill or title role match
            if score < 15:
                continue

            # Format fields for display
            clean_desc = clean_text(job.get("description", ""))
            # Strip html tags if present
            clean_desc = re.sub(r"<[^>]+>", " ", clean_desc)
            clean_desc = re.sub(r"\s+", " ", clean_desc).strip()
            if len(clean_desc) > 300:
                clean_desc = clean_desc[:297] + "..."

            formatted_job = {
                "id": job.get("id"),
                "title": clean_text(job.get("title")),
                "company": clean_text(job.get("company")) or "Hiring Company",
                "location": clean_text(job.get("location")) or "Tamil Nadu",
                "description": clean_desc,
                "matched_skills": matched_skills,
                "salary": format_salary(job.get("salary_min"), job.get("salary_max")),
                "created": format_date(job.get("created")),
                "url": job_url,
                "_relevance_score": score,
            }
            all_jobs.append(formatted_job)

    # Sort strictly by relevance score descending
    all_jobs.sort(key=lambda j: j.get("_relevance_score", 0), reverse=True)

    # Return top 12 clean jobs without internal score key
    final_vacancies = []
    for j in all_jobs[:12]:
        j.pop("_relevance_score", None)
        final_vacancies.append(j)

    return final_vacancies