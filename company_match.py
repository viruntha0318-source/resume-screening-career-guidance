import json
import re

# Common company acronyms and their known corporate / brand names
COMPANY_ALIASES = {
    "tcs": ["Tata Consultancy Services", "TCS", "Tata Consultancy Services Limited"],
    "cts": ["Cognizant", "Cognizant Technology Solutions"],
    "cognizant": ["Cognizant", "Cognizant Technology Solutions"],
    "infosys": ["Infosys", "Infosys Limited"],
    "wipro": ["Wipro", "Wipro Limited"],
    "hcl": ["HCL Technologies", "HCLTech", "HCL"],
    "l&t": ["Larsen & Toubro", "LTIMindtree", "L&T Technology Services"],
    "lti": ["LTIMindtree", "Larsen & Toubro"],
    "accenture": ["Accenture"],
    "zoho": ["Zoho", "Zoho Corporation"],
    "novitech": ["Novitech", "Novitech R&D"],
    "amazon": ["Amazon", "Amazon Web Services", "AWS"],
    "microsoft": ["Microsoft"],
    "google": ["Google"],
    "ibm": ["IBM", "IBM India"],
    "capgemini": ["Capgemini"],
    "tech mahindra": ["Tech Mahindra"],
}


# ============================================================
# BASIC HELPERS
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


def safe_list(value):
    if isinstance(value, list):
        return value
    return []


def unique_list(values):
    result = []
    seen = set()

    for value in safe_list(values):
        value = clean_text(value)
        if not value:
            continue

        key = normalize_key(value)
        if key in seen:
            continue

        seen.add(key)
        result.append(value)

    return result


def clean_json(text):
    if not text:
        return {}

    text = text.strip()
    text = re.sub(r"^```json", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^```", "", text)
    text = re.sub(r"```$", "", text)
    text = text.strip()

    try:
        return json.loads(text)
    except Exception:
        pass

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1:
        try:
            return json.loads(text[start:end + 1])
        except Exception:
            pass

    return {}


# ============================================================
# COMPANY NAME MATCH
# ============================================================

def company_names_match(requested_company, returned_company):
    requested = normalize_key(requested_company)
    returned = normalize_key(returned_company)

    if not requested or not returned:
        return False

    if requested == returned or requested in returned or returned in requested:
        return True

    # Check aliases
    aliases = COMPANY_ALIASES.get(requested, [])
    for alias in aliases:
        norm_alias = normalize_key(alias)
        if norm_alias == returned or norm_alias in returned or returned in norm_alias:
            return True

    requested_words = {word for word in requested.split() if len(word) >= 3}
    returned_words = {word for word in returned.split() if len(word) >= 3}

    if requested_words and returned_words:
        if requested_words & returned_words:
            return True

    return False


# ============================================================
# COMPANY CURRENT JOBS SEARCH
# ============================================================

def get_company_current_jobs(company, probable_roles, adzuna_request):
    """
    Search Adzuna specifically for job postings from the target company.
    Queries Tamil Nadu first; if 0 results, searches across India
    so actual company advertisements are found.
    """
    company = clean_text(company)
    if not company:
        return []

    # Build search terms including aliases
    search_names = [company]
    norm_c = normalize_key(company)
    if norm_c in COMPANY_ALIASES:
        search_names.extend(COMPANY_ALIASES[norm_c])

    company_jobs = []
    seen = set()

    for name in search_names[:3]:
        # Try Tamil Nadu first
        try:
            jobs = adzuna_request(query=name, limit=20, where="Tamil Nadu")
            for job in jobs:
                if company_names_match(company, job.get("company", "")):
                    jid = str(job.get("id") or job.get("url"))
                    if jid not in seen:
                        seen.add(jid)
                        company_jobs.append(job)
        except Exception as error:
            print("ADZUNA COMPANY SEARCH TN ERROR:", repr(error))

    # If no jobs in TN, search across India for that company
    if not company_jobs:
        for name in search_names[:3]:
            try:
                jobs = adzuna_request(query=name, limit=20, where=None)
                for job in jobs:
                    if company_names_match(company, job.get("company", "")):
                        jid = str(job.get("id") or job.get("url"))
                        if jid not in seen:
                            seen.add(jid)
                            company_jobs.append(job)
            except Exception as error:
                print("ADZUNA COMPANY SEARCH ALL-INDIA ERROR:", repr(error))

    return company_jobs[:10]


# ============================================================
# GEMINI COMPANY MATCH
# ============================================================

def gemini_company_match(company, resume_result, company_jobs, gemini_client, gemini_model):
    """
    Calculates company-to-resume match using Gemini.
    - If live advertisements are found, matches against those live ads.
    - If no live ads are in Adzuna, evaluates against verified entry-level hiring criteria.
    - If no verifiable requirements can be identified, returns match_percentage: None.
    - Recommends courses with platform URLs ONLY when skills need improvement.
    - Does NOT hardcode percentages or fake job ads.
    """
    company = clean_text(company)
    if not company:
        return {
            "match_percentage": None,
            "missing_skills": [],
            "recommended_courses": [],
            "message": "No target company was specified."
        }

    if not gemini_client:
        return {
            "match_percentage": None,
            "missing_skills": [],
            "recommended_courses": [],
            "message": "Gemini AI client is not available."
        }

    candidate_skills = resume_result.get("skills", [])
    probable_roles = resume_result.get("probable_roles", [])
    projects = resume_result.get("projects", [])

    has_live_ads = bool(company_jobs)
    job_ads_summary = []
    for job in company_jobs[:6]:
        job_ads_summary.append({
            "title": job.get("title", ""),
            "company": job.get("company", ""),
            "location": job.get("location", ""),
            "description": (job.get("description", "") or "")[:350],
        })

    prompt = f"""
You are an expert technical hiring analyst.

TARGET COMPANY:
{company}

CANDIDATE PROFILE:
- Extracted Skills: {json.dumps(candidate_skills)}
- Probable Roles: {json.dumps(probable_roles)}
- Projects: {json.dumps([{"title": p.get("title"), "tech_stack": p.get("tech_stack")} for p in projects[:3]])}

LIVE COMPANY ADVERTISEMENTS (from job database):
{json.dumps(job_ads_summary, ensure_ascii=False) if has_live_ads else "None found in current job board snapshot."}

TASK & RULES:
1. If live advertisements are provided above, evaluate candidate skills against requirements in those ads.
2. If no live advertisements were returned from the board, evaluate candidate skills against verified, authentic entry-level technical expectations for {company} in the candidate's field (e.g. standard entry-level hiring assessments and technical criteria for software/IT/tech roles).
3. If {company} is a completely unknown, non-existent, or unverifiable entity where authentic requirements cannot be retrieved, set "match_percentage" to null and explain this in "message". DO NOT guess or invent requirements.
4. Calculate "match_percentage" (integer 0 to 100, or null) purely based on the proportion of required skills satisfied by candidate skills. NEVER return a hardcoded or fake percentage. DO NOT treat missing data as 0%.
5. "missing_skills": List only skills required by the company that the candidate does not possess.
6. "recommended_courses":
   - Provide recommended courses ONLY if "missing_skills" is non-empty. If "missing_skills" is empty, return an empty array [].
   - Each course MUST be a realistic learning resource directly targeting one of the missing skills.
   - Each course object must contain:
     * "name": specific course title (e.g. "Meta Front-End Developer", "Python Data Structures")
     * "skill": the specific missing skill covered
     * "provider": educational platform (e.g. Coursera, freeCodeCamp, edX, Kaggle, MDN Web Docs)
     * "status": "Free", "Free Audit", or "Paid"
     * "url": real homepage or catalog URL for that course/platform (e.g. https://www.coursera.org, https://www.freecodecamp.org, https://www.edx.org)
7. Do NOT include a "matching_skills" section.

Return ONLY valid JSON matching this schema:
{{
    "match_percentage": 70,
    "missing_skills": ["SQL", "Docker"],
    "recommended_courses": [
        {{
            "name": "Databases and SQL for Data Science",
            "skill": "SQL",
            "provider": "Coursera / IBM",
            "status": "Free Audit",
            "url": "https://www.coursera.org"
        }}
    ],
    "message": "Based on current verified job requirements for {company}."
}}
"""

    result = {}
    models_to_try = [gemini_model]
    if "gemini-3.5-flash" not in models_to_try:
        models_to_try.append("gemini-3.5-flash")

    last_error = None
    for model_name in models_to_try:
        try:
            response = gemini_client.models.generate_content(
                model=model_name,
                contents=prompt
            )
            result = clean_json(response.text)
            if result:
                break
        except Exception as error:
            last_error = error
            err_str = str(error)
            print(f"GEMINI CALL ERROR ({model_name}):", repr(error))
            if any(code in err_str for code in ["503", "UNAVAILABLE", "429"]):
                # Try next model immediately
                continue
            else:
                break

    if not result:
        return {
            "match_percentage": None,
            "missing_skills": [],
            "recommended_courses": [],
            "message": f"Company match could not be calculated: {last_error}"
        }

    raw_percentage = result.get("match_percentage")
    percentage = None
    if raw_percentage is not None:
        try:
            if isinstance(raw_percentage, str):
                m = re.search(r"\d+(?:\.\d+)?", raw_percentage)
                if m:
                    percentage = float(m.group(0))
            else:
                percentage = float(raw_percentage)

            if percentage is not None:
                percentage = max(0, min(100, round(percentage)))
        except Exception:
            percentage = None

    missing_skills = unique_list(result.get("missing_skills", []))
    raw_courses = result.get("recommended_courses", [])

    # Format courses into structured objects
    formatted_courses = []
    if missing_skills and isinstance(raw_courses, list):
        for c in raw_courses:
            if isinstance(c, dict):
                c_name = clean_text(c.get("name") or c.get("title"))
                c_skill = clean_text(c.get("skill"))
                c_provider = clean_text(c.get("provider") or c.get("platform") or "Online Platform")
                c_status = clean_text(c.get("status") or "Free / Audit Available")
                c_url = clean_text(c.get("url") or "https://www.coursera.org")

                if not c_url.startswith(("http://", "https://")):
                    c_url = "https://" + c_url

                if c_name:
                    formatted_courses.append({
                        "name": c_name,
                        "skill": c_skill,
                        "provider": c_provider,
                        "status": c_status,
                        "url": c_url,
                    })
            elif isinstance(c, str) and clean_text(c):
                # Fallback if string returned
                formatted_courses.append({
                    "name": clean_text(c),
                    "skill": missing_skills[0] if missing_skills else "Skill Upgrade",
                    "provider": "Self-Paced Course",
                    "status": "Available",
                    "url": "https://www.coursera.org",
                })
    # Strict rule: Recommend courses ONLY when improvement skills exist
    if not missing_skills:
        formatted_courses = []

    message = clean_text(result.get("message", ""))
    if percentage is None and not message:
        message = f"Reliable current requirements for '{company}' could not be verified."
    elif percentage is not None and not message:
        if has_live_ads:
            message = f"Calculated from live job postings for {company}."
        else:
            message = f"Calculated from verified entry-level competency benchmarks for {company}."

    return {
        "match_percentage": percentage,
        "missing_skills": missing_skills,
        "recommended_courses": formatted_courses,
        "message": message,
    }