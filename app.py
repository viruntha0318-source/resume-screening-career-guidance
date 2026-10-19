
import os
import json
import re
import uuid

from dotenv import load_dotenv

# Load environment variables before importing config.
load_dotenv()

from flask import (
    Flask,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)

from werkzeug.utils import secure_filename
from google import genai

from config import (
    UPLOAD_FOLDER,
    FLASK_SECRET_KEY,
    ALLOWED_EXTENSIONS,
    GEMINI_API_KEY,
    GEMINI_MODEL,
)

from resume_parser import (
    extract_resume_text,
    analyze_text_resume,
)

from resume_validator import (
    validate_text_resume,
    validate_gemini_result,
)

from vacancy_finder import get_resume_based_vacancies


# ============================================================
# APP SETUP
# ============================================================

app = Flask(
    __name__,
    template_folder="templates"
)

app.secret_key = FLASK_SECRET_KEY

# Maximum upload size: 15 MB.
app.config["MAX_CONTENT_LENGTH"] = 15 * 1024 * 1024

os.makedirs(
    UPLOAD_FOLDER,
    exist_ok=True
)


# ============================================================
# GEMINI SETUP
# ============================================================

gemini_client = None

if GEMINI_API_KEY:
    try:
        gemini_client = genai.Client(
            api_key=GEMINI_API_KEY
        )

    except Exception as error:
        print(
            "GEMINI CLIENT ERROR:",
            repr(error)
        )


# ============================================================
# FILE VALIDATION
# ============================================================

def allowed_file(filename):
    if not filename or "." not in filename:
        return False

    extension = filename.rsplit(".", 1)[1].lower()

    return extension in ALLOWED_EXTENSIONS


# ============================================================
# NORMALIZE RESUME RESULT
# ============================================================

def normalize_result(result):
    if not isinstance(result, dict):
        return {}

    default_fields = {
        "candidate_name": "",
        "skills": [],
        "education": [],
        "certifications": [],
        "projects": [],
        "internship": [],
        "experience": [],
        "probable_roles": [],
        "recommended_courses": [],
    }

    for field, default_value in default_fields.items():
        result.setdefault(field, default_value)

    # Ensure fields used as lists are lists.
    list_fields = [
        "skills",
        "education",
        "certifications",
        "projects",
        "internship",
        "experience",
        "probable_roles",
        "recommended_courses",
    ]

    for field in list_fields:
        if not isinstance(result.get(field), list):
            result[field] = []

    return result


# ============================================================
# VALIDATION RESULT NORMALIZER
# ============================================================

def normalize_validation_result(validation):
    if isinstance(validation, dict):
        return {
            "is_resume": bool(
                validation.get("is_resume", False)
            ),
            "message": str(
                validation.get("message", "")
            ),
        }

    if validation is True:
        return {
            "is_resume": True,
            "message": "",
        }

    return {
        "is_resume": False,
        "message": "The uploaded file is not a valid resume.",
    }


# ============================================================
# IMAGE RESUME ANALYSIS
# ============================================================

def analyze_image_resume(file_path):
    if not gemini_client:
        return {
            "is_resume": False,
            "candidate_name": "",
            "skills": [],
            "education": [],
            "certifications": [],
            "projects": [],
            "internship": [],
            "experience": [],
            "probable_roles": [],
            "recommended_courses": [],
        }

    prompt = """
Analyze the uploaded document/image.

Determine whether it is a resume or CV.

Return ONLY valid JSON using this structure:

{
    "is_resume": true,
    "candidate_name": "",
    "skills": [],
    "education": [],
    "certifications": [],
    "projects": [],
    "internship": [],
    "experience": [],
    "probable_roles": [],
    "recommended_courses": []
}

Rules:
1. Do not invent information.
2. Extract skills explicitly supported by the resume.
3. Do not return a single-letter skill such as "C".
4. Extract education only from visible details.
5. Extract certifications only when visible.
6. Extract projects only when visible.
7. Extract internship and experience only from visible content.
8. Suggest probable career roles based on resume evidence.
9. Recommend relevant courses based on the person's skills,
   education, projects, and career roles.
10. Course recommendations may be suggestions, but do not
    claim the person has completed those courses.
11. If the document is a study note, question paper,
    textbook, assignment, article, or unrelated document,
    set "is_resume" to false.
12. Return valid JSON only. Do not use Markdown fences.
"""

    try:
        extension = file_path.rsplit(".", 1)[1].lower()

        mime_types = {
            "jpg": "image/jpeg",
            "jpeg": "image/jpeg",
            "png": "image/png",
            "webp": "image/webp",
        }

        mime_type = mime_types.get(extension)

        if not mime_type:
            return {}

        with open(file_path, "rb") as file:
            uploaded_data = file.read()

        models_to_try = [GEMINI_MODEL]

        # Preserve the existing fallback model.
        fallback_model = "gemini-3.5-flash"

        if fallback_model not in models_to_try:
            models_to_try.append(fallback_model)

        response = None

        for model_name in models_to_try:
            try:
                response = gemini_client.models.generate_content(
                    model=model_name,
                    contents=[
                        prompt,
                        {
                            "inline_data": {
                                "mime_type": mime_type,
                                "data": uploaded_data,
                            }
                        },
                    ],
                )

                if response and response.text:
                    break

            except Exception as error:
                print(
                    f"IMAGE RESUME GEMINI ERROR ({model_name}):",
                    repr(error)
                )

        if not response or not response.text:
            return {}

        text = response.text.strip()

        text = re.sub(
            r"^```(?:json)?\s*",
            "",
            text,
            flags=re.IGNORECASE
        )

        text = re.sub(
            r"\s*```$",
            "",
            text
        ).strip()

        try:
            result = json.loads(text)

        except json.JSONDecodeError:
            start = text.find("{")
            end = text.rfind("}")

            if start == -1 or end == -1:
                return {}

            result = json.loads(
                text[start:end + 1]
            )

        return normalize_result(result)

    except Exception as error:
        print(
            "IMAGE RESUME ANALYSIS ERROR:",
            repr(error)
        )

        return {}


# ============================================================
# RESULT DATA
# ============================================================

def build_result_data(
    candidate_name,
    register_number,
    resume_result,
    vacancies,
):
    resume_result = normalize_result(resume_result)

    return {
        "candidate_name": candidate_name,
        "register_number": register_number,
        "skills": resume_result.get("skills", []),
        "education": resume_result.get("education", []),
        "certifications": resume_result.get("certifications", []),
        "projects": resume_result.get("projects", []),
        "internship": resume_result.get("internship", []),
        "experience": resume_result.get("experience", []),
        "probable_roles": resume_result.get("probable_roles", []),
        "recommended_courses": resume_result.get(
            "recommended_courses", []
        ),
        "vacancies": vacancies,
    }


# ============================================================
# HOME
# ============================================================

@app.route("/")
def index():
    return render_template("index.html")


# ============================================================
# UPLOAD
# ============================================================

@app.route("/upload", methods=["POST"])
def upload():
    candidate_name = request.form.get(
        "name", ""
    ).strip()

    register_number = request.form.get(
        "register_number", ""
    ).strip()

    uploaded_file = request.files.get("resume")

    # --------------------------------------------------------
    # BASIC VALIDATION
    # --------------------------------------------------------

    if not candidate_name:
        flash("Please enter your name.")
        return redirect(url_for("index"))

    if not register_number:
        flash("Please enter your register number.")
        return redirect(url_for("index"))

    if not uploaded_file or not uploaded_file.filename:
        flash("Please upload your resume.")
        return redirect(url_for("index"))

    if not allowed_file(uploaded_file.filename):
        flash("Unsupported file format.")
        return redirect(url_for("index"))

    # --------------------------------------------------------
    # SAVE FILE WITH A UNIQUE NAME
    # --------------------------------------------------------

    original_filename = secure_filename(
        uploaded_file.filename
    )

    if not original_filename or "." not in original_filename:
        flash("Invalid filename.")
        return redirect(url_for("index"))

    extension = original_filename.rsplit(".", 1)[1].lower()

    filename = f"{uuid.uuid4().hex}.{extension}"

    file_path = os.path.join(
        UPLOAD_FOLDER,
        filename
    )

    try:
        uploaded_file.save(file_path)

    except Exception as error:
        print(
            "FILE SAVE ERROR:",
            repr(error)
        )
        flash("Unable to save the uploaded file.")
        return redirect(url_for("index"))

    try:
        # ----------------------------------------------------
        # PROCESS RESUME
        # ----------------------------------------------------

        if extension in {"pdf", "docx", "txt", "rtf"}:
            resume_text = extract_resume_text(file_path)

            if not resume_text or not resume_text.strip():
                flash("Could not extract text from this file.")
                return redirect(url_for("index"))

            resume_result = analyze_text_resume(
                resume_text
            )

            validation = validate_text_resume(
                resume_text,
                resume_result
            )

        else:
            resume_result = analyze_image_resume(
                file_path
            )

            validation = validate_gemini_result(
                resume_result
            )

        validation = normalize_validation_result(
            validation
        )

        if not validation["is_resume"]:
            flash(
                validation["message"]
                or "The uploaded file is not a valid resume."
            )
            return redirect(url_for("index"))

        resume_result = normalize_result(
            resume_result
        )

        # ----------------------------------------------------
        # DEBUG INFORMATION
        # ----------------------------------------------------

        print("\n========== RESUME DEBUG ==========")
        print("Upload ID:", filename)
        print("Form Candidate Name:", candidate_name)
        print(
            "Parsed Resume Name:",
            resume_result.get("candidate_name")
        )
        print("Skills:", resume_result.get("skills"))
        print("Education:", resume_result.get("education"))
        print(
            "Certifications:",
            resume_result.get("certifications")
        )
        print("Projects:", resume_result.get("projects"))
        print(
            "Career Roles:",
            resume_result.get("probable_roles")
        )
        print(
            "Recommended Courses:",
            resume_result.get("recommended_courses")
        )
        print("==================================\n")

        # ----------------------------------------------------
        # RESUME-BASED VACANCIES
        # Existing Adzuna search logic is preserved.
        # Do not change this call without checking vacancy_finder.py.
        # ----------------------------------------------------

        resume_skills = resume_result.get("skills", [])
        probable_roles = resume_result.get("probable_roles", [])

        try:
            vacancies = get_resume_based_vacancies(
                resume_skills=resume_skills,
                probable_roles=probable_roles
            )

        except Exception as error:
            print(
                "VACANCY SEARCH ERROR:",
                repr(error)
            )
            vacancies = []

        # ----------------------------------------------------
        # RESULT
        # ----------------------------------------------------

        result_data = build_result_data(
            candidate_name=candidate_name,
            register_number=register_number,
            resume_result=resume_result,
            vacancies=vacancies,
        )

        return render_template(
            "result.html",
            **result_data
        )

    except Exception as error:
        print(
            "RESUME PROCESSING ERROR:",
            repr(error)
        )

        flash("Unable to process the uploaded resume.")
        return redirect(url_for("index"))

    finally:
        # Remove the temporary uploaded file after processing.
        try:
            if os.path.isfile(file_path):
                os.remove(file_path)

        except OSError as error:
            print(
                "TEMPORARY FILE CLEANUP ERROR:",
                repr(error)
            )


# ============================================================
# FILE TOO LARGE
# ============================================================

@app.errorhandler(413)
def file_too_large(error):
    flash("The uploaded file exceeds the 15 MB limit.")
    return redirect(url_for("index"))


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":
    app.run(
        host="127.0.0.1",
        port=5001,
        debug=True
    )
```
