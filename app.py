import os
import json
import re
import uuid

from flask import (
    Flask,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)

from werkzeug.utils import secure_filename
from dotenv import load_dotenv
from google import genai

from config import (
    UPLOAD_FOLDER,
    FLASK_SECRET_KEY,
    ALLOWED_EXTENSIONS,
    GEMINI_API_KEY,
    GEMINI_MODEL,
)

from services.resume_parser import (
    extract_resume_text,
    analyze_text_resume,
)

from services.resume_validator import (
    validate_text_resume,
    validate_gemini_result,
)

from services.company_match import (
    get_company_current_jobs,
    gemini_company_match,
)

from services.vacancy_finder import (
    adzuna_request,
    get_resume_based_vacancies,
)


# ============================================================
# APP SETUP
# ============================================================

load_dotenv()

app = Flask(
    __name__,
    template_folder="templates"
)

app.secret_key = FLASK_SECRET_KEY

os.makedirs(
    UPLOAD_FOLDER,
    exist_ok=True
)


# ============================================================
# GEMINI
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

        gemini_client = None


# ============================================================
# FILE VALIDATION
# ============================================================

def allowed_file(filename):

    if not filename:
        return False

    if "." not in filename:
        return False

    extension = (
        filename.rsplit(
            ".",
            1
        )[1]
        .lower()
    )

    return extension in ALLOWED_EXTENSIONS


# ============================================================
# NORMALIZE RESUME RESULT
# ============================================================

def normalize_result(result):

    if not isinstance(result, dict):
        return {}

    result.setdefault(
        "candidate_name",
        ""
    )

    result.setdefault(
        "skills",
        []
    )

    result.setdefault(
        "education",
        []
    )

    result.setdefault(
        "certifications",
        []
    )

    result.setdefault(
        "projects",
        []
    )

    result.setdefault(
        "internship",
        []
    )

    result.setdefault(
        "experience",
        []
    )

    result.setdefault(
        "probable_roles",
        []
    )

    return result


# ============================================================
# VALIDATION RESULT NORMALIZER
# ============================================================

def normalize_validation_result(
    validation
):

    # Correct format:
    # {"is_resume": True, "message": ""}

    if isinstance(
        validation,
        dict
    ):

        return {
            "is_resume": bool(
                validation.get(
                    "is_resume",
                    False
                )
            ),
            "message": str(
                validation.get(
                    "message",
                    ""
                )
            ),
        }

    # Validator returned True
    if validation is True:

        return {
            "is_resume": True,
            "message": "",
        }

    # Validator returned False
    return {
        "is_resume": False,
        "message": (
            "The uploaded file is not a valid resume."
        ),
    }


# ============================================================
# IMAGE RESUME ANALYSIS
# ============================================================

def analyze_image_resume(
    file_path
):

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
        }

    prompt = """
Analyze this uploaded document/image.

Determine whether it is actually a resume/CV.

Return ONLY valid JSON:

{
    "is_resume": true,
    "candidate_name": "",
    "skills": [],
    "education": [],
    "certifications": [],
    "projects": [],
    "internship": [],
    "experience": [],
    "probable_roles": []
}

Strict rules:

1. Do not invent information.
2. Skills must be explicitly visible in the resume.
3. Never return a single-letter skill such as "C".
4. Education must come only from visible education details.
5. Certifications must come only from visible certifications.
6. Projects must come only from visible projects.
7. Internship and experience must come only from visible content.
8. probable_roles must be based only on visible resume evidence.
9. If this is a study note, question paper, textbook,
   assignment, article, or unrelated document,
   is_resume must be false.
10. Do not treat ordinary educational content as a resume.
"""

    try:

        extension = (
            file_path
            .rsplit(
                ".",
                1
            )[1]
            .lower()
        )

        mime_types = {
            "jpg": "image/jpeg",
            "jpeg": "image/jpeg",
            "png": "image/png",
            "webp": "image/webp",
        }

        mime_type = mime_types.get(
            extension,
            "image/jpeg"
        )

        with open(
            file_path,
            "rb"
        ) as file:

            uploaded_data = file.read()

        models_to_try = [GEMINI_MODEL]
        if "gemini-3.5-flash" not in models_to_try:
            models_to_try.append("gemini-3.5-flash")

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
            except Exception as err:
                err_str = str(err)
                print(f"IMAGE RESUME GEMINI ERROR ({model_name}):", repr(err))
                if any(code in err_str for code in ["503", "UNAVAILABLE", "429"]):
                    continue
                else:
                    break

        text = (
            response.text
            if response
            else ""
        )

        text = text.strip()

        text = re.sub(
            r"^```json",
            "",
            text,
            flags=re.IGNORECASE
        )

        text = re.sub(
            r"^```",
            "",
            text
        )

        text = re.sub(
            r"```$",
            "",
            text
        )

        text = text.strip()

        try:

            result = json.loads(
                text
            )

        except Exception:

            start = text.find("{")
            end = text.rfind("}")

            if (
                start == -1
                or
                end == -1
            ):
                return {}

            result = json.loads(
                text[
                    start:
                    end + 1
                ]
            )

        return normalize_result(
            result
        )

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
    target_company,
    resume_result,
    company_match,
    vacancies,
):

    resume_result = normalize_result(
        resume_result
    )

    if not isinstance(
        company_match,
        dict
    ):
        company_match = {}

    missing_skills = company_match.get(
        "missing_skills",
        []
    )

    recommended_courses = company_match.get(
        "recommended_courses",
        []
    )

    if not missing_skills:
        recommended_courses = []

    return {
        "candidate_name": candidate_name,
        "register_number": register_number,
        "target_company": target_company,

        "skills": resume_result.get(
            "skills",
            []
        ),

        "education": resume_result.get(
            "education",
            []
        ),

        "certifications": resume_result.get(
            "certifications",
            []
        ),

        "projects": resume_result.get(
            "projects",
            []
        ),

        "internship": resume_result.get(
            "internship",
            []
        ),

        "experience": resume_result.get(
            "experience",
            []
        ),

        "probable_roles": resume_result.get(
            "probable_roles",
            []
        ),

        "match_percentage": company_match.get(
            "match_percentage"
        ),

        "missing_skills": missing_skills,

        "recommended_courses": (
            recommended_courses
        ),

        "company_message": company_match.get(
            "message",
            ""
        ),

        "vacancies": vacancies,
    }


# ============================================================
# HOME
# ============================================================

@app.route("/")
def index():

    return render_template(
        "index.html"
    )


# ============================================================
# UPLOAD
# ============================================================

@app.route(
    "/upload",
    methods=["POST"]
)
def upload():

    candidate_name = (
        request.form.get(
            "name",
            ""
        ).strip()
    )

    register_number = (
        request.form.get(
            "register_number",
            ""
        ).strip()
    )

    target_company = (
        request.form.get(
            "target_company",
            ""
        ).strip()
    )

    uploaded_file = request.files.get(
        "resume"
    )

    # --------------------------------------------------------
    # BASIC VALIDATION
    # --------------------------------------------------------

    if not candidate_name:

        flash(
            "Please enter your name."
        )

        return redirect(
            url_for("index")
        )

    if not register_number:

        flash(
            "Please enter your register number."
        )

        return redirect(
            url_for("index")
        )

    if not target_company:

        flash(
            "Please enter the target company."
        )

        return redirect(
            url_for("index")
        )

    if not uploaded_file:

        flash(
            "Please upload your resume."
        )

        return redirect(
            url_for("index")
        )

    if not uploaded_file.filename:

        flash(
            "Please select a resume file."
        )

        return redirect(
            url_for("index")
        )

    if not allowed_file(
        uploaded_file.filename
    ):

        flash(
            "Unsupported file format."
        )

        return redirect(
            url_for("index")
        )

    # --------------------------------------------------------
    # SAVE FILE - UNIQUE NAME FOR EVERY UPLOAD
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

    uploaded_file.save(file_path)

    # --------------------------------------------------------
    # PROCESS RESUME
    # --------------------------------------------------------

    try:

        # ====================================================
        # PDF / DOCX / TXT / RTF
        # ====================================================

        if extension in {
            "pdf",
            "docx",
            "txt",
            "rtf",
        }:

            resume_text = extract_resume_text(
                file_path
            )

            resume_result = analyze_text_resume(
                resume_text
            )

            validation = (
                validate_text_resume(
                    resume_text,
                    resume_result
                )
            )

            validation = (
                normalize_validation_result(
                    validation
                )
            )

            if not validation["is_resume"]:

                flash(
                    validation["message"]
                    or
                    "The uploaded file is not a valid resume."
                )

                return redirect(
                    url_for("index")
                )

        # ====================================================
        # IMAGE
        # ====================================================

        else:

            resume_result = analyze_image_resume(
                file_path
            )

            validation = (
                validate_gemini_result(
                    resume_result
                )
            )

            validation = (
                normalize_validation_result(
                    validation
                )
            )

            if not validation["is_resume"]:

                flash(
                    validation["message"]
                    or
                    "The uploaded file is not a valid resume."
                )

                return redirect(
                    url_for("index")
                )

            resume_result = normalize_result(
                resume_result
            )

    except Exception as error:

        print(
            "RESUME PROCESSING ERROR:",
            repr(error)
        )

        flash(
            "Unable to process the uploaded resume."
        )

        return redirect(
            url_for("index")
        )

    # --------------------------------------------------------
    # NORMALIZE RESUME
    # --------------------------------------------------------

    resume_result = normalize_result(
        resume_result
    )
        # --------------------------------------------------------
    # DEBUG: VERIFY DATA FROM THE CURRENT UPLOAD
    # --------------------------------------------------------

    print("\n========== RESUME DEBUG ==========")
    print("Upload ID:", filename)
    print("Form Candidate Name:", candidate_name)
    print("Parsed Resume Name:", resume_result.get("candidate_name"))
    print("Education:", resume_result.get("education"))
    print("Certifications:", resume_result.get("certifications"))
    print("Projects:", resume_result.get("projects"))
    print("==================================\n")

    resume_skills = resume_result.get(
        "skills",
        []
    )

    probable_roles = resume_result.get(
        "probable_roles",
        []
    )

    # --------------------------------------------------------
    # RESUME-BASED VACANCIES
    #
    # TARGET COMPANY IS NOT USED.
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # COMPANY CURRENT JOBS
    #
    # ONLY FOR COMPANY MATCHING.
    # --------------------------------------------------------

    try:

        company_jobs = get_company_current_jobs(
            company=target_company,
            probable_roles=probable_roles,
            adzuna_request=adzuna_request
        )

    except Exception as error:

        print(
            "COMPANY JOB SEARCH ERROR:",
            repr(error)
        )

        company_jobs = []

    # --------------------------------------------------------
    # COMPANY MATCH
    # --------------------------------------------------------

    try:

        company_match = gemini_company_match(
            company=target_company,
            resume_result=resume_result,
            company_jobs=company_jobs,
            gemini_client=gemini_client,
            gemini_model=GEMINI_MODEL
        )

    except Exception as error:

        print(
            "COMPANY MATCH ERROR:",
            repr(error)
        )

        company_match = {
            "match_percentage": None,
            "missing_skills": [],
            "recommended_courses": [],
            "message": (
                "Company match could not be calculated."
            )
        }

    # --------------------------------------------------------
    # RESULT
    # --------------------------------------------------------

    result_data = build_result_data(
        candidate_name=candidate_name,
        register_number=register_number,
        target_company=target_company,
        resume_result=resume_result,
        company_match=company_match,
        vacancies=vacancies,
    )
    return render_template(
    "result.html",
    **result_data
)


 # ============================================================
# RUN
# ============================================================

if __name__ == "__main__":
    app.run(
        host="127.0.0.1",
        port=5001,
        debug=True
    )