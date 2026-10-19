import os
import re

import pymupdf as fitz
from docx import Document


# =========================================================
# BASIC HELPERS
# =========================================================

def clean_text(value):
    if value is None:
        return ""
    return str(value).strip()


def normalize_key(value):
    value = clean_text(value).lower()
    value = re.sub(r"[^a-z0-9+#./&\- ]+", " ", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def unique_list(values):
    result = []
    seen = set()

    if not isinstance(values, list):
        return result

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


# =========================================================
# TEXT EXTRACTION
# =========================================================

def extract_pdf_text(file_path):
    """
    Extract text using sort=True to preserve visual/reading order
    across multi-column layouts, sidebars, and multi-page resumes.
    """
    pages = []

    with fitz.open(file_path) as pdf:
        for page in pdf:
            text = page.get_text("text", sort=True)
            if not text or not text.strip():
                text = page.get_text("text")

            if text and text.strip():
                text = text.replace("\ufffd", "•").replace("\r", "\n")
                pages.append(text.strip())

    return "\n\n".join(pages).strip()


def extract_docx_text(file_path):
    """
    Extract paragraphs and table contents from DOCX files.
    """
    document = Document(file_path)
    lines = []

    for paragraph in document.paragraphs:
        text = clean_text(paragraph.text)
        if text:
            lines.append(text)

    for table in document.tables:
        for row in table.rows:
            row_cells = [clean_text(cell.text) for cell in row.cells if clean_text(cell.text)]
            if row_cells:
                unique_cells = []
                for cell_text in row_cells:
                    if not unique_cells or cell_text != unique_cells[-1]:
                        unique_cells.append(cell_text)
                if unique_cells:
                    lines.append(" | ".join(unique_cells))

    return "\n".join(lines).strip()


def extract_text_file(file_path):
    extension = os.path.splitext(file_path)[1].lower()
    encodings = ["utf-8", "utf-8-sig", "latin-1"]

    for encoding in encodings:
        try:
            with open(file_path, "r", encoding=encoding, errors="ignore") as file:
                text = file.read()

            if extension == ".rtf":
                text = re.sub(r"\\'[0-9a-fA-F]{2}", " ", text)
                text = re.sub(r"\\[a-zA-Z]+\d* ?", " ", text)
                text = re.sub(r"[{}]", " ", text)

            return text.strip()

        except Exception:
            continue

    return ""


def extract_resume_text(file_path):
    extension = os.path.splitext(file_path)[1].lower()

    if extension == ".pdf":
        return extract_pdf_text(file_path)

    if extension == ".docx":
        return extract_docx_text(file_path)

    if extension in {".txt", ".rtf"}:
        return extract_text_file(file_path)

    return ""


# =========================================================
# SECTION HEADINGS
# =========================================================

SECTION_ALIASES = {
    "objective": {
        "objective",
        "career objective",
        "profile",
        "professional summary",
        "summary",
        "about me",
        "personal profile",
        "career profile",
    },

    "education": {
        "education",
        "educational details",
        "educational qualification",
        "education qualification",
        "academic details",
        "academic qualification",
        "educational background",
        "qualification",
        "qualifications",
        "academics",
        "education details",
        "academic background",
        "educational qualifications",
    },

    "certifications": {
        "certification",
        "certifications",
        "certificate",
        "certificates",
        "certification courses",
        "professional certifications",
        "courses and certifications",
        "courses & certifications",
        "licenses and certifications",
        "licenses & certifications",
        "certified courses",
        "certifications and licenses",
        "online courses",
        "trainings and certifications",
        "trainings & certifications",
    },

    "projects": {
        "project",
        "projects",
        "academic projects",
        "personal projects",
        "project details",
        "projects undertaken",
        "mini projects",
        "major projects",
        "academic project",
        "project work",
    },

    "skills": {
        "skills",
        "technical skills",
        "technical skill",
        "technical",
        "key skills",
        "core skills",
        "technical competencies",
        "skills summary",
        "technical expertise",
        "areas of expertise",
        "it skills",
        "computer skills",
        "programming languages",
        "software skills",
        "core competencies",
        "tools and technologies",
        "tools & technologies",
        "technical proficiencies",
        "skills and abilities",
        "skills & abilities",
    },

    "experience": {
        "experience",
        "work experience",
        "professional experience",
        "employment",
        "employment history",
        "work history",
        "career history",
        "professional background",
        "relevant experience",
        "work experiences",
    },

    "internship": {
        "internship",
        "internships",
        "internship experience",
        "summer internship",
        "industrial training",
        "internship training",
        "internship details",
        "internship experiences",
    },

    "languages": {
        "languages",
        "language",
        "languages known",
        "language proficiency",
    },

    "interests": {
        "interests",
        "interest",
        "areas of interest",
        "area of interest",
        "career interests",
        "fields of interest",
        "hobbies",
    },

    "achievements": {
        "achievements",
        "achievement",
        "awards",
        "award",
        "honors",
        "accomplishments",
        "extracurricular activities",
        "co-curricular activities",
    },

    "ignore": {
        "declaration",
        "references",
        "reference",
        "personal details",
        "contact",
        "personal information",
    },
}


def canonical_heading(line):
    text = clean_text(line)

    text = re.sub(r"^[\s•●▪◦\-–—\u2022*]+", "", text)
    text = re.sub(r"[:|]+$", "", text)
    text = re.sub(r"\s+", " ", text).strip()

    normalized = normalize_key(text)

    if not normalized:
        return None

    if len(normalized.split()) > 6:
        return None

    for section, aliases in SECTION_ALIASES.items():
        normalized_aliases = {
            normalize_key(alias) for alias in aliases
        }

        if normalized in normalized_aliases:
            return section

    return None
def clean_lines(text):
    raw_lines = text.replace("\r", "\n").split("\n")
    lines = []

    for line in raw_lines:
        line = clean_text(line)
        if not line:
            continue
        line = re.sub(r"[ \t]+", " ", line)
        lines.append(line)

    return lines


def extract_sections(text):
    """
    Separates the resume into recognized sections.
    Uses canonical_heading detection to avoid section leakage.
    """
    lines = clean_lines(text)

    sections = {}
    current_section = "header"
    sections[current_section] = []

    for line in lines:
        heading = canonical_heading(line)

        if heading:
            current_section = heading
            if current_section not in sections:
                sections[current_section] = []
            continue

        sections.setdefault(current_section, []).append(line)

    for key in sections:
        sections[key] = [
            clean_text(line)
            for line in sections[key]
            if clean_text(line)
        ]

    return sections


# =========================================================
# NAME
# =========================================================

def extract_candidate_name(text, sections=None):
    if sections is None:
        sections = extract_sections(text)

    header_lines = sections.get("header", [])

    for line in header_lines[:8]:
        candidate = clean_text(line)
        if not candidate:
            continue

        lower = candidate.lower()

        if "@" in candidate or re.search(r"\d{5,}", candidate):
            continue

        if any(word in lower for word in [
            "resume", "curriculum vitae", "objective", "email", "phone",
            "mobile", "linkedin", "github", "address", "profile"
        ]):
            continue

        words = candidate.split()
        if 2 <= len(words) <= 6:
            if all(re.match(r"^[A-Za-z][A-Za-z.'-]*$", word) for word in words):
                return candidate.upper()

    return ""


# =========================================================
# SKILLS
# =========================================================

KNOWN_SKILLS = {
    "python": "Python",
    "java": "Java",
    "javascript": "JavaScript",
    "typescript": "TypeScript",
    "html": "HTML",
    "html5": "HTML",
    "css": "CSS",
    "css3": "CSS",
    "react": "React",
    "react.js": "React",
    "reactjs": "React",
    "angular": "Angular",
    "vue": "Vue.js",
    "vue.js": "Vue.js",
    "node": "Node.js",
    "node.js": "Node.js",
    "nodejs": "Node.js",
    "flask": "Flask",
    "django": "Django",
    "fastapi": "FastAPI",
    "sql": "SQL",
    "mysql": "MySQL",
    "sqlite": "SQLite",
    "mongodb": "MongoDB",
    "postgresql": "PostgreSQL",
    "nlp": "NLP",
    "natural language processing": "NLP",
    "machine learning": "Machine Learning",
    "deep learning": "Deep Learning",
    "artificial intelligence": "Artificial Intelligence",
    "data analysis": "Data Analysis",
    "pandas": "Pandas",
    "numpy": "NumPy",
    "scikit-learn": "Scikit-Learn",
    "tensorflow": "TensorFlow",
    "pytorch": "PyTorch",
    "git": "Git",
    "github": "GitHub",
    "gitlab": "GitLab",
    "docker": "Docker",
    "kubernetes": "Kubernetes",
    "aws": "AWS",
    "azure": "Azure",
    "gcp": "GCP",
    "linux": "Linux",
    "figma": "Figma",
    "ui/ux": "UI/UX Design",
    "ui/ux design": "UI/UX Design",
    "ui/ux designer": "UI/UX Design",
    "ui_ux": "UI/UX Design",
    "ui_ux design": "UI/UX Design",
    "ui_ux designer": "UI/UX Design",
    "ui ux": "UI/UX Design",
    "ui ux design": "UI/UX Design",
    "ui ux designer": "UI/UX Design",
    "cybersecurity": "Cybersecurity",
    "bootstrap": "Bootstrap",
    "tailwind": "Tailwind CSS",
    "tailwind css": "Tailwind CSS",
    "php": "PHP",
    "c++": "C++",
    "c#": "C#",
    "c": "C",
    "power bi": "Power BI",
    "powerbi": "Power BI",
    "tableau": "Tableau",
    "excel": "Excel",
    "rest api": "REST API",
    "express": "Express.js",
    "express.js": "Express.js",
    "spring": "Spring",
    "spring boot": "Spring Boot",
    "opencv": "OpenCV",
    "keras": "Keras",
}

FALSE_POSITIVE_WORDS = {
    "status", "on going", "duration", "present", "semester", "description",
    "college", "academy", "university", "engineering", "student", "women",
    "developing", "working", "designing", "allows", "displays", "helps",
    "programminglanguage", "programming language", "technologies", "tech stack",
    "speak", "write", "read", "english", "tamil", "hindi", "language", "languages",
    "resume", "curriculum", "vitae", "profile", "project", "projects", "education"
}


def extract_skills_from_text(text, sections):
    """
    Extracts skills strictly from:
    1. Explicit Skills section
    2. Project technology stacks
    3. Technical interests where genuine technical skills appear.

    Strict rules:
    - Never detect single-letter 'C' unless explicit C programming is identified.
    - Remove duplicate and false-positive words.
    - Normalize naming (e.g. Python, UI/UX Design, HTML, CSS).
    """
    sources = []

    # 1. Technical skills section
    sources.extend(sections.get("skills", []))

    # 2. Project tech stacks
    for line in sections.get("projects", []):
        lower = line.lower()
        if any(keyword in lower for keyword in [
            "tech stack", "technologies", "technology", "tools", "built using", "using"
        ]):
            sources.append(line)

    # 3. Interests (e.g. UI/UX Designer, Cybersecurity)
    sources.extend(sections.get("interests", []))

    combined_sources = " \n ".join(sources)
    found_skills = []
    seen = set()

    # Rule: Single letter C is only extracted if explicit C programming is present
    has_explicit_c = bool(re.search(
        r"\b(?:c\s*programming|c\s*language|c\s*/\s*c\+\+|programming\s*in\s*c|c\s*(?:and|&)\s*c\+\+)\b",
        combined_sources,
        flags=re.IGNORECASE
    ))
    if has_explicit_c:
        found_skills.append("C")
        seen.add("c")

    for raw in sources:
        cleaned = re.sub(
            r"^(?:programming\s*languages?|languages?|technologies|tech\s*stack|tools|skills|technical\s*skills?)\s*:\s*",
            "",
            raw,
            flags=re.IGNORECASE
        )

        # Protect slashes in known compound terms before splitting
        cleaned_protected = re.sub(r"\bui\s*/\s*ux\b", "ui_ux", cleaned, flags=re.IGNORECASE)
        cleaned_protected = re.sub(r"\bc\s*/\s*c\+\+", "c_cpp", cleaned_protected, flags=re.IGNORECASE)
        cleaned_protected = re.sub(r"\bci\s*/\s*cd\b", "ci_cd", cleaned_protected, flags=re.IGNORECASE)

        tokens = re.split(r"[,|;/•●\n]+", cleaned_protected)

        for token in tokens:
            t = token.strip().lower()
            t = re.sub(r"^[^\w+#.]+|[^\w+#.]+$", "", t)

            if not t or t in FALSE_POSITIVE_WORDS:
                continue

            if len(t) < 2:
                continue

            # Direct dictionary match
            if t in KNOWN_SKILLS:
                canonical = KNOWN_SKILLS[t]
                if canonical.lower() not in seen:
                    seen.add(canonical.lower())
                    found_skills.append(canonical)
            else:
                if re.search(r"\bui_ux\b|\bui\s+ux\b", t):
                    if "ui/ux design" not in seen:
                        seen.add("ui/ux design")
                        found_skills.append("UI/UX Design")
                    continue

                for k, canonical in KNOWN_SKILLS.items():
                    if k == "c":
                        continue
                    pattern = r"\b" + re.escape(k) + r"\b"
                    if re.search(pattern, t):
                        if canonical.lower() not in seen:
                            seen.add(canonical.lower())
                            found_skills.append(canonical)

    return unique_list(found_skills)


# =========================================================
# EDUCATION
# =========================================================

def clean_education_lines(lines):
    result = []
    for line in lines:
        line = clean_text(line)
        if not line:
            continue
        lower = line.lower()

        if any(keyword in lower for keyword in [
            "technical skills", "technical skill", "objective",
            "certifications", "certificate", "languages", "interests",
            "declaration"
        ]):
            continue

        result.append(line)

    return result


def extract_education(text, sections=None):
    """
    Extracts education qualifications into distinct, readable entries.
    Each entry contains only degree, institution, duration, CGPA/marks.
    """
    if sections is None:
        sections = extract_sections(text)

    lines = clean_education_lines(sections.get("education", []))

    if not lines:
        return []

    qualifications = []
    current_entry = []

    degree_indicators = [
        "bachelor", "master", "b.sc", "m.sc", "b.tech", "m.tech", "b.e", "m.e",
        "bba", "mba", "bca", "mca", "b.com", "m.com", "diploma", "higher secondary",
        "secondary", "hsc", "sslc", "class xii", "class x", "12th", "10th"
    ]

    for line in lines:
        lower = line.lower()
        has_degree_word = any(deg in lower for deg in degree_indicators)

        if has_degree_word and current_entry:
            qualifications.append(" | ".join(current_entry))
            current_entry = [line]
        else:
            current_entry.append(line)

    if current_entry:
        qualifications.append(" | ".join(current_entry))

    cleaned_entries = []
    for q in qualifications:
        q_clean = re.sub(r"\s+", " ", q).strip()
        q_clean = re.sub(r",\s*\|", " |", q_clean)
        q_clean = re.sub(r"([A-Za-z])\(", r"\1 (", q_clean)
        if q_clean:
            cleaned_entries.append(q_clean)

    return cleaned_entries


# =========================================================
# CERTIFICATIONS
# =========================================================

def extract_certifications(text, sections=None):
    """
    Extracts certifications containing only certification names,
    providers, and dates.
    """
    if sections is None:
        sections = extract_sections(text)

    lines = sections.get("certifications", [])
    if not lines:
        return []

    result = []
    for line in lines:
        line = clean_text(line)
        if not line:
            continue

        lower = line.lower()
        if lower in {"certifications", "certification", "certificates", "certificate"}:
            continue

        if canonical_heading(line):
            continue

        if any(term in lower for term in ["speak/write/read", "cgpa", "duration:", "status:"]):
            continue

        line_clean = re.sub(r"^[\s•●▪◦\-–—\u2022*]+", "", line).strip()
        # Clean rogue semicolons
        line_clean = re.sub(r"&;\s*", "& ", line_clean)
        line_clean = re.sub(r";\s*", " ", line_clean).strip()

        # Normalize spacing before brackets & clean camelCase
        line_clean = re.sub(r"([A-Za-z])\(", r"\1 (", line_clean)
        line_clean = re.sub(r"(\d+)\s*(days|months|years|hrs|hours)", r"\1 \2", line_clean, flags=re.IGNORECASE)
        line_clean = re.sub(r"([a-z])([A-Z])", r"\1 \2", line_clean)

        if line_clean:
            result.append(line_clean)

    return unique_list(result)


# =========================================================
# PROJECTS
# =========================================================

def extract_projects(text, sections=None):
    """
    Extracts distinct projects with title, tech stack, and description.
    """
    if sections is None:
        sections = extract_sections(text)

    lines = sections.get("projects", [])
    if not lines:
        return []

    projects = []
    curr = None

    for line in lines:
        line = clean_text(line)
        if not line:
            continue

        lower = line.lower()

        # 1. Tech stack indicator
        if lower.startswith(("tech stack:", "technologies:", "technology:", "tools:", "tech stack", "technologies")):
            if curr:
                stack = re.sub(r"^(?:tech stack|technologies|tools|technology)\s*:\s*", "", line, flags=re.IGNORECASE).strip()
                curr["tech_stack"] = stack
            continue

        # 2. Status line (skip)
        if lower.startswith("status:"):
            continue

        # 3. Description heading label (skip)
        if lower in {"description:", "description", "summary:", "responsibilities:", "key features:"}:
            continue

        # 4. Explicit bullet point
        is_bullet = bool(re.match(r"^[\s•●▪◦\-–—\u2022*]+", line))

        # 5. Check if line represents a project title
        has_date_tag = bool(re.search(r"\[[^\]]{3,40}\]|\((?:20\d\d|19\d\d)[^)]*\)", line))
        has_project_prefix = bool(re.match(r"^(?:project\s*\d*[:.-]|#\d+|\d+[\.)])\s*", lower))

        is_new_title = False
        if has_date_tag or has_project_prefix:
            is_new_title = True
        elif curr is None:
            is_new_title = True
        elif not is_bullet and curr and (curr["tech_stack"] or curr["description"]):
            if len(line.split()) <= 12 and not line.endswith((".", ";", ",")):
                is_new_title = True

        if is_new_title:
            if curr and (curr.get("title") or curr.get("tech_stack")):
                projects.append(curr)

            title = line
            title = re.sub(r"([a-z])([A-Z])", r"\1 \2", title)
            title = re.sub(r"([A-Za-z])\[", r"\1 [", title)
            curr = {"title": title.strip(), "tech_stack": "", "description": []}
        else:
            if curr:
                clean_bullet = re.sub(r"^[\s•●▪◦\-–—\u2022*]+\s*", "", line).strip()
                if clean_bullet:
                    curr["description"].append(clean_bullet)

    if curr and (curr.get("title") or curr.get("tech_stack")):
        projects.append(curr)

    cleaned_projects = []
    for p in projects:
        title = clean_text(p.get("title", ""))
        tech_stack = clean_text(p.get("tech_stack", ""))
        desc_list = p.get("description", [])

        if isinstance(desc_list, list):
            description = " ".join(desc_list).strip()
        else:
            description = clean_text(desc_list)

        if not title:
            continue

        cleaned_projects.append({
            "title": title,
            "tech_stack": tech_stack,
            "description": description,
        })

    return cleaned_projects


# =========================================================
# INTERNSHIP
# =========================================================

def extract_internship(text, sections=None):
    if sections is None:
        sections = extract_sections(text)

    lines = sections.get("internship", [])
    if not lines:
        return []

    result = []
    for line in lines:
        line_clean = re.sub(r"^[\s•●▪◦\-–—\u2022*]+", "", line).strip()
        if line_clean and not canonical_heading(line_clean):
            result.append(line_clean)

    return unique_list(result)


# =========================================================
# EXPERIENCE
# =========================================================

def extract_experience(text, sections=None):
    if sections is None:
        sections = extract_sections(text)

    lines = sections.get("experience", [])
    if not lines:
        return []

    result = []
    for line in lines:
        line_clean = re.sub(r"^[\s•●▪◦\-–—\u2022*]+", "", line).strip()
        if line_clean and not canonical_heading(line_clean):
            result.append(line_clean)

    return unique_list(result)

# =========================================================
# PROBABLE ROLES
# =========================================================

def infer_probable_roles(skills, education, projects, text=""):
    roles = []
    skill_keys = {normalize_key(skill) for skill in skills}

    project_text = " ".join(
        clean_text(project.get("title", "")) + " " +
        clean_text(project.get("tech_stack", "")) + " " +
        clean_text(project.get("description", ""))
        for project in projects
        if isinstance(project, dict)
    ).lower()

    education_text = " ".join(education).lower()
    full_text = (
        project_text + " " + education_text + " " +
        clean_text(text).lower()
    )

    # UI/UX Design
    if (
        "ui/ux design" in skill_keys
        or "figma" in skill_keys
        or "ui/ux" in full_text
    ):
        roles.append("UI/UX Designer")

    # Web Development
    if (
        {"html", "css"}.issubset(skill_keys)
        or "javascript" in skill_keys
        or "react" in skill_keys
        or "web development" in full_text
    ):
        roles.append("Web Developer")

    # Python Development
    if (
        "python" in skill_keys
        or "python developer" in full_text
    ):
        roles.append("Python Developer")

    # Java Development
    if "java" in skill_keys:
        roles.append("Java Developer")

    # AI / Machine Learning
    if (
        any(skill in skill_keys for skill in [
            "nlp",
            "machine learning",
            "deep learning",
            "artificial intelligence",
            "tensorflow",
            "pytorch",
            "scikit-learn",
        ])
        or "artificial intelligence" in full_text
    ):
        roles.append("AI/ML Intern")

    # Cybersecurity
    if (
        "cybersecurity" in skill_keys
        or "cybersecurity" in full_text
    ):
        roles.append("Cybersecurity Intern")

    # Data Analysis
    if any(skill in skill_keys for skill in [
        "data analysis",
        "power bi",
        "tableau",
        "excel",
        "sql",
        "pandas",
        "numpy",
    ]):
        roles.append("Data Analyst Trainee")

    # Database roles
    if any(skill in skill_keys for skill in [
        "mysql",
        "postgresql",
        "mongodb",
        "sqlite",
    ]):
        roles.append("Database Developer Trainee")

    # Backend development
    if any(skill in skill_keys for skill in [
        "flask",
        "django",
        "fastapi",
        "node.js",
        "express.js",
        "spring boot",
    ]):
        roles.append("Backend Developer")

    # Cloud / DevOps
    if any(skill in skill_keys for skill in [
        "aws",
        "azure",
        "gcp",
        "docker",
        "kubernetes",
        "linux",
    ]):
        roles.append("Cloud / DevOps Trainee")

    return unique_list(roles)


# =========================================================
# RECOMMENDED COURSES
# =========================================================

def recommend_courses(skills, probable_roles):
    """
    Suggest learning topics based on extracted skills and roles.
    These are suggestions, not claims that the student completed
    any course or has a certification.
    """

    skill_keys = {normalize_key(skill) for skill in skills}
    role_keys = {normalize_key(role) for role in probable_roles}

    courses = []

    def add_course(course):
        if course not in courses:
            courses.append(course)

    # Python
    if (
        "python" in skill_keys
        or "python developer" in role_keys
    ):
        add_course("Advanced Python Programming")
        add_course("Python Application Development")

    # Web development
    if any(skill in skill_keys for skill in [
        "html", "css", "javascript", "react",
        "node.js", "bootstrap", "tailwind css",
    ]) or "web developer" in role_keys:
        add_course("Full-Stack Web Development")
        add_course("Responsive Web Design")

    # Java
    if "java" in skill_keys:
        add_course("Object-Oriented Programming with Java")
        add_course("Java Application Development")

    # AI and Machine Learning
    if any(skill in skill_keys for skill in [
        "machine learning",
        "deep learning",
        "artificial intelligence",
        "nlp",
        "tensorflow",
        "pytorch",
        "scikit-learn",
    ]) or "ai/ml intern" in role_keys:
        add_course("Machine Learning Fundamentals")
        add_course("Introduction to Artificial Intelligence")

    # Data analytics
    if any(skill in skill_keys for skill in [
        "data analysis", "power bi", "tableau",
        "excel", "pandas", "numpy", "sql",
    ]) or "data analyst trainee" in role_keys:
        add_course("Data Analytics Fundamentals")
        add_course("SQL for Data Analysis")

    # UI/UX
    if (
        "ui/ux design" in skill_keys
        or "figma" in skill_keys
        or "ui/ux designer" in role_keys
    ):
        add_course("UI/UX Design Fundamentals")
        add_course("Figma for Interface Design")

    # Cybersecurity
    if (
        "cybersecurity" in skill_keys
        or "cybersecurity intern" in role_keys
    ):
        add_course("Cybersecurity Fundamentals")
        add_course("Network Security Basics")

    # Backend
    if any(skill in skill_keys for skill in [
        "flask", "django", "fastapi",
        "node.js", "express.js", "spring boot",
    ]) or "backend developer" in role_keys:
        add_course("REST API Development")
        add_course("Backend Application Development")

    # Cloud and DevOps
    if any(skill in skill_keys for skill in [
        "aws", "azure", "gcp", "docker",
        "kubernetes", "linux",
    ]) or "cloud / devops trainee" in role_keys:
        add_course("Cloud Computing Fundamentals")
        add_course("Docker and DevOps Fundamentals")

    # Database
    if any(skill in skill_keys for skill in [
        "mysql", "postgresql", "mongodb", "sqlite",
    ]) or "database developer trainee" in role_keys:
        add_course("Database Design and SQL")
        add_course("Database Management Fundamentals")

    # General beginner guidance if no rules matched
    if not courses:
        add_course("Programming Fundamentals")
        add_course("Problem Solving and Data Structures")
        add_course("Git and GitHub Fundamentals")

    return courses[:6]


# =========================================================
# MAIN TEXT RESUME ANALYSIS
# =========================================================

def analyze_text_resume(text):
    text = clean_text(text)
    sections = extract_sections(text)

    candidate_name = extract_candidate_name(text, sections)
    skills = extract_skills_from_text(text, sections)
    education = extract_education(text, sections)
    certifications = extract_certifications(text, sections)
    projects = extract_projects(text, sections)
    internship = extract_internship(text, sections)
    experience = extract_experience(text, sections)

    probable_roles = infer_probable_roles(
        skills=skills,
        education=education,
        projects=projects,
        text=text,
    )

    recommended_courses = recommend_courses(
        skills=skills,
        probable_roles=probable_roles,
    )

    return {
        "candidate_name": candidate_name,
        "skills": skills,
        "education": education,
        "certifications": certifications,
        "projects": projects,
        "internship": internship,
        "experience": experience,
        "probable_roles": probable_roles,
        "recommended_courses": recommended_courses,
    }
