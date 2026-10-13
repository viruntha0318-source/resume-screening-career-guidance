import re


# ============================================================
# BASIC HELPERS
# ============================================================

def clean_text(value):
    if value is None:
        return ""

    return str(value).strip()


def normalize_key(value):
    value = clean_text(value).lower()

    value = re.sub(
        r"[^a-z0-9+#.\- ]+",
        " ",
        value
    )

    value = re.sub(
        r"\s+",
        " ",
        value
    )

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

        if not key or key in seen:
            continue

        seen.add(key)
        result.append(value)

    return result


# ============================================================
# INVALID DOCUMENT INDICATORS
# ============================================================

INVALID_DOCUMENT_TERMS = {
    "question paper",
    "question bank",
    "study material",
    "study notes",
    "lecture notes",
    "tutorial",
    "textbook",
    "assignment",
    "worksheet",
    "exam paper",
    "model question paper",
    "important questions",
    "unit questions",
    "chapter questions",
    "practice questions",
    "sample questions",
    "mcq",
    "multiple choice questions"
}


# ============================================================
# RESUME SECTION INDICATORS
# ============================================================

RESUME_SECTION_TERMS = {
    "objective",
    "career objective",
    "profile",
    "summary",
    "education",
    "academic qualification",
    "academic qualifications",
    "skills",
    "technical skills",
    "technical skill",
    "projects",
    "project",
    "certifications",
    "certification",
    "experience",
    "work experience",
    "internship",
    "internships",
    "achievements",
    "languages",
    "interests"
}


# ============================================================
# CONTACT INDICATORS
# ============================================================

EMAIL_PATTERN = re.compile(
    r"\b[A-Za-z0-9._%+-]+@"
    r"[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"
)

PHONE_PATTERN = re.compile(
    r"(?<!\d)"
    r"(?:\+91[\s\-]?)?"
    r"[6-9]\d{9}"
    r"(?!\d)"
)


# ============================================================
# SINGLE-LETTER SKILL PROTECTION
# ============================================================

def clean_skills(skills):
    cleaned = []

    for skill in safe_list(skills):

        skill = clean_text(skill)

        normalized = normalize_key(skill)

        # Never allow C, R, A, etc.
        if len(normalized) <= 1:
            continue

        cleaned.append(skill)

    return unique_list(cleaned)


# ============================================================
# DOCUMENT TYPE CHECK
# ============================================================

def contains_invalid_document_terms(text):
    normalized_text = normalize_key(text)

    for term in INVALID_DOCUMENT_TERMS:

        if normalize_key(term) in normalized_text:
            return True

    return False


# ============================================================
# RESUME SECTION CHECK
# ============================================================

def count_resume_sections(text):
    lines = [
        normalize_key(line)
        for line in text.splitlines()
        if normalize_key(line)
    ]

    found = set()

    for line in lines:

        if line in RESUME_SECTION_TERMS:
            found.add(line)

    return found


# ============================================================
# CONTACT CHECK
# ============================================================

def has_contact_information(text):
    has_email = bool(
        EMAIL_PATTERN.search(text)
    )

    has_phone = bool(
        PHONE_PATTERN.search(text)
    )

    return has_email or has_phone


# ============================================================
# CANDIDATE NAME CHECK
# ============================================================

def has_candidate_name(candidate_name):
    candidate_name = clean_text(
        candidate_name
    )

    if not candidate_name:
        return False

    words = re.findall(
        r"[A-Za-z][A-Za-z.\-']*",
        candidate_name
    )

    return 2 <= len(words) <= 7


# ============================================================
# MAIN TEXT RESUME VALIDATION
# ============================================================

def validate_text_resume(
    text,
    parsed_result=None
):
    """
    Strict validation before company matching
    and vacancy searching.

    Invalid documents must stop the pipeline.
    """

    text = clean_text(text)

    if not text:
        return False

    # --------------------------------------------------------
    # Reject obvious non-resume documents.
    # --------------------------------------------------------

    if contains_invalid_document_terms(text):
        return False

    # --------------------------------------------------------
    # Text must contain enough actual content.
    # --------------------------------------------------------

    if len(text) < 120:
        return False

    sections = count_resume_sections(text)

    # --------------------------------------------------------
    # A proper resume should contain multiple resume sections.
    # --------------------------------------------------------

    section_score = len(sections)

    if section_score < 2:
        return False

    # --------------------------------------------------------
    # Check parsed resume data if available.
    # --------------------------------------------------------

    if isinstance(parsed_result, dict):

        skills = clean_skills(
            parsed_result.get(
                "skills",
                []
            )
        )

        education = unique_list(
            parsed_result.get(
                "education",
                []
            )
        )

        projects = unique_list(
            parsed_result.get(
                "projects",
                []
            )
        )

        certifications = unique_list(
            parsed_result.get(
                "certifications",
                []
            )
        )

        internship = unique_list(
            parsed_result.get(
                "internship",
                []
            )
        )

        experience = unique_list(
            parsed_result.get(
                "experience",
                []
            )
        )

        candidate_name = clean_text(
            parsed_result.get(
                "candidate_name",
                ""
            )
        )

        # ----------------------------------------------------
        # Resume must contain meaningful candidate evidence.
        # ----------------------------------------------------

        evidence_count = 0

        if has_candidate_name(
            candidate_name
        ):
            evidence_count += 1

        if has_contact_information(text):
            evidence_count += 1

        if skills:
            evidence_count += 1

        if education:
            evidence_count += 1

        if projects:
            evidence_count += 1

        if certifications:
            evidence_count += 1

        if internship:
            evidence_count += 1

        if experience:
            evidence_count += 1

        # ----------------------------------------------------
        # At least two meaningful resume signals are required.
        # ----------------------------------------------------

        if evidence_count < 2:
            return False

    return True


# ============================================================
# GEMINI IMAGE RESULT VALIDATION
# ============================================================

def validate_gemini_result(result):
    """
    Validate and clean Gemini's image-resume result.

    Gemini alone is NOT trusted to decide whether
    a document is valid.
    """

    if not isinstance(result, dict):
        return {
            "is_resume": False
        }

    skills = clean_skills(
        result.get(
            "skills",
            []
        )
    )

    education = unique_list(
        result.get(
            "education",
            []
        )
    )

    certifications = unique_list(
        result.get(
            "certifications",
            []
        )
    )

    projects = unique_list(
        result.get(
            "projects",
            []
        )
    )

    internship = unique_list(
        result.get(
            "internship",
            []
        )
    )

    experience = unique_list(
        result.get(
            "experience",
            []
        )
    )

    probable_roles = unique_list(
        result.get(
            "probable_roles",
            []
        )
    )

    candidate_name = clean_text(
        result.get(
            "candidate_name",
            ""
        )
    )

    cleaned_result = {
        "is_resume": bool(
            result.get(
                "is_resume",
                False
            )
        ),
        "candidate_name": candidate_name,
        "skills": skills,
        "education": education,
        "certifications": certifications,
        "projects": projects,
        "internship": internship,
        "experience": experience,
        "probable_roles": probable_roles,
        "courses": []
    }

    # --------------------------------------------------------
    # Minimum evidence for an image resume.
    # --------------------------------------------------------

    evidence_count = 0

    if has_candidate_name(
        candidate_name
    ):
        evidence_count += 1

    if skills:
        evidence_count += 1

    if education:
        evidence_count += 1

    if projects:
        evidence_count += 1

    if certifications:
        evidence_count += 1

    if internship:
        evidence_count += 1

    if experience:
        evidence_count += 1

    if evidence_count < 2:
        cleaned_result["is_resume"] = False

    return cleaned_result