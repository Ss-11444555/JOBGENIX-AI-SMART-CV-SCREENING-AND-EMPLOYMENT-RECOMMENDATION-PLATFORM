from flask import Flask, request, jsonify, current_app, abort, send_from_directory, url_for, render_template_string
from flask_cors import CORS
from flask_bcrypt import Bcrypt
import jwt
import datetime
from functools import wraps
import mysql.connector
from mysql.connector import Error
import os
from dotenv import load_dotenv
import json
from decimal import Decimal
import tempfile
import uuid
from openai import OpenAI
from werkzeug.utils import secure_filename
import re
from NewAIPredict.predictor import predict_job_and_salary

# OCR imports (used when available)
try:
    import pytesseract
    from pdf2image import convert_from_path
    from PIL import Image
    OCR_AVAILABLE = True
except Exception as ocr_import_err:
    OCR_AVAILABLE = False
    pytesseract = None
    convert_from_path = None
    Image = None
    print(f"OCR dependencies not available: {ocr_import_err}")

TESSERACT_CMD = os.getenv('TESSERACT_CMD') or r"C:\Program Files\Tesseract-OCR\tesseract.exe"
POPPLER_BIN = os.getenv('POPPLER_BIN') or os.path.join(os.getcwd(), 'OCR_code', 'poppler-25.11.0', 'Library', 'bin')

if OCR_AVAILABLE:
    try:
        pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD
    except Exception as e:
        print(f"Warning: could not set Tesseract path: {e}")
    if not os.path.isdir(POPPLER_BIN):
        print(f"Warning: POPPLER_BIN does not exist: {POPPLER_BIN}")

app = Flask(__name__, static_folder='frontend', static_url_path='')
app.config['SECRET_KEY'] = 'm&8^VpM&!Hn44pvoaIWsJog$h#eRBZvS' # Change this in production

# Absolute paths for static assets outside the frontend folder
PROJECT_ROOT = os.path.abspath(os.path.dirname(__file__))
STATIC_DIRS = {
    'css': os.path.abspath(os.path.join(PROJECT_ROOT, 'css')),
    'js': os.path.abspath(os.path.join(PROJECT_ROOT, 'js')),
    'pages': os.path.abspath(os.path.join(PROJECT_ROOT, 'pages')),
    'assets': os.path.abspath(os.path.join(PROJECT_ROOT, 'assets')),
    'uploads': os.path.abspath(os.path.join(PROJECT_ROOT, 'uploads')),
}

# Audio output directory for TTS (shared with /uploads static route)
AUDIO_UPLOAD_DIR = os.path.join(PROJECT_ROOT, 'uploads', 'audio')
os.makedirs(AUDIO_UPLOAD_DIR, exist_ok=True)

# Load environment variables from the project root explicitly so OPENAI_API_KEY is available
dotenv_path = os.path.join(PROJECT_ROOT, '.env')
load_dotenv(dotenv_path=dotenv_path)

# Optional OpenAI client for interview Q&A (re-evaluate after loading .env)
openai_api_key = os.getenv("OPENAI_API_KEY")
openai_client = OpenAI(api_key=openai_api_key) if openai_api_key else None

def jsonify_error(message, status=500, detail=None):
    payload = {'error': message}
    if detail:
        payload['detail'] = detail
    return jsonify(payload), status

def assert_admin(current_user_id, conn):
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT user_type FROM users WHERE id=%s", (current_user_id,))
    row = cur.fetchone()
    cur.close()
    if not row or row['user_type'] != 'admin':
        abort(403)

# Enable CORS for all domains for testing
CORS(app, resources={r"/*": {"origins": "*"}})

bcrypt = Bcrypt(app)

# Database Configuration
db_config = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'user': os.getenv('DB_USER', 'root'),
    'password': os.getenv('DB_PASSWORD', ''),
    'database': os.getenv('DB_NAME', 'job_matching_system')
}

def get_db_connection():
    try:
        connection = mysql.connector.connect(**db_config)
        return connection
    except Error as e:
        print(f"Error connecting to MySQL: {e}")
        return None

def generate_token(user_id):
    payload = {
        'user_id': user_id,
        'exp': datetime.datetime.utcnow() + datetime.timedelta(days=1)
    }
    return jwt.encode(payload, app.config['SECRET_KEY'], algorithm='HS256')

# ALLOWED_EMAIL_PATTERN = re.compile(r'^[^@\s]+@(?:gmail\.com|outlook\.com)$')
ALLOWED_EMAIL_PATTERN = re.compile(r'^[a-zA-Z0-9._%+-]+@(?:gmail\.com|outlook\.com|student\.utem\.edu\.my)$')

def normalize_email(email):
    """Return a trimmed, lower-cased email if it matches allowed domains."""
    if not email or not isinstance(email, str):
        return None
    em = email.strip().lower()
    if not ALLOWED_EMAIL_PATTERN.match(em):
        return None
    return em

def pick_reset_table(conn):
    """Return a reset table and reference column based on actual columns."""
    def cols_for(table):
        c = get_table_columns(conn, table) or set()
        if not c:
            return None
        if 'email' in c:
            return (table, 'email')
        if 'user_id' in c:
            return (table, 'user_id')
        return None

    if table_exists(conn, 'password_resets'):
        found = cols_for('password_resets')
        if found:
            return found
    if table_exists(conn, 'password_reset_tokens'):
        found = cols_for('password_reset_tokens')
        if found:
            return found
    return (None, None)

def pick_verification_table(conn):
    """Return a table/column usable for email verification codes."""
    if table_exists(conn, 'email_verifications'):
        return ('email_verifications', 'email')
    if table_exists(conn, 'password_resets'):
        return ('password_resets', 'email')
    if table_exists(conn, 'password_reset_tokens'):
        return ('password_reset_tokens', 'email')
    return (None, None)

def ensure_verification_table(conn):
    """Create a verification-capable table if none found."""
    table_name, ref_col = pick_verification_table(conn)
    if table_name:
        return table_name, ref_col
    cur = conn.cursor()
    try:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS email_verifications (
                id INT AUTO_INCREMENT PRIMARY KEY,
                email VARCHAR(255) NOT NULL,
                token VARCHAR(255) NOT NULL,
                expires_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                used TINYINT(1) NOT NULL DEFAULT 0,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS password_resets (
                id INT AUTO_INCREMENT PRIMARY KEY,
                email VARCHAR(255) NOT NULL,
                token VARCHAR(255) NOT NULL,
                expires_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                used TINYINT(1) NOT NULL DEFAULT 0,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """
        )
        conn.commit()
    except Exception as e:
        current_app.logger.exception("Failed to ensure verification table: %s", e)
    finally:
        try:
            cur.close()
        except Exception:
            pass
    return pick_verification_table(conn)

def ensure_reset_table(conn):
    """Create an email-based password_resets table if none found."""
    table_name, ref_col = pick_reset_table(conn)
    if table_name:
        return table_name, ref_col
    cur = conn.cursor()
    try:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS password_resets (
                id INT AUTO_INCREMENT PRIMARY KEY,
                email VARCHAR(255) NOT NULL,
                token VARCHAR(255) NOT NULL,
                expires_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                used TINYINT(1) NOT NULL DEFAULT 0,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """
        )
        conn.commit()
    except Exception as e:
        current_app.logger.exception("Failed to ensure reset table: %s", e)
    finally:
        try:
            cur.close()
        except Exception:
            pass
    return pick_reset_table(conn)


def smtp_send(to_email, subject, body):
    """Send an email using SMTP settings from environment."""
    import smtplib
    from email.mime.text import MIMEText

    host = os.getenv('SMTP_HOST')
    port = int(os.getenv('SMTP_PORT', '465'))
    user = os.getenv('SMTP_USER')
    password = os.getenv('SMTP_PASS')
    use_ssl = os.getenv('SMTP_USE_SSL', '1') == '1'

    if not all([host, port, user, password]):
        raise RuntimeError("SMTP is not configured")

    msg = MIMEText(body)
    msg['Subject'] = subject
    msg['From'] = user
    msg['To'] = to_email

    if use_ssl:
        with smtplib.SMTP_SSL(host, port) as server:
            server.login(user, password)
            server.send_message(msg)
    else:
        with smtplib.SMTP(host, port) as server:
            server.starttls()
            server.login(user, password)
            server.send_message(msg)

# Mapping helpers to align friendly labels with DB ENUM values
ENUM_MAPS = {
    'job_type': {
        'full-time': 'full-time',
        'full time': 'full-time',
        'part-time': 'part-time',
        'part time': 'part-time',
        'contract': 'contract',
        'internship': 'internship',
        'intern': 'internship',
        'remote': 'remote',
        'hybrid': 'remote',  # no hybrid enum; fall back to remote
    },
    'experience_level': {
        'internship': 'internship',
        'intern': 'internship',
        'entry': 'entry',
        'entry level': 'entry',
        'mid': 'mid',
        'mid level': 'mid',
        'senior': 'senior',
        'lead': 'lead',
        'manager': 'lead',  # map manager to lead
    },
    'education_level': {
        'high-school': 'high-school',
        'high school': 'high-school',
        'associate': 'associate',
        'diploma': 'associate',
        'bachelor': 'bachelor',
        "bachelor's degree": 'bachelor',
        'master': 'master',
        "master's degree": 'master',
        'phd': 'phd',
        'not required': 'any',
        'any': 'any',
    }
}


def normalize_enum(val, kind):
    """Normalize user-facing strings to DB enum values; returns None if unknown/empty."""
    if val is None:
        return None
    key = str(val).strip().lower()
    if not key:
        return None
    direct = ENUM_MAPS[kind].get(key)
    if direct:
        return direct
    # If already a valid enum value, accept it
    if key in ENUM_MAPS[kind].values():
        return key
    return None


def _prepare_job_payload(data, company_id, default_status=None):
    title = (data.get('title') or '').strip()
    description = (data.get('description') or '').strip()
    location = (data.get('location') or '').strip()
    if not title or not description or not location:
        return None, 'Title, description, and location are required.'

    raw_job_type = data.get('type') or data.get('jobType')
    department = data.get('department')
    requirements = data.get('requirements')
    benefits = data.get('benefits')

    salary_min = salary_max = salary_type = None
    if isinstance(data.get('salary'), dict):
        salary_min = data['salary'].get('min')
        salary_max = data['salary'].get('max')
        salary_type = data['salary'].get('type')
    salary_min = salary_min if salary_min is not None else data.get('salaryMin')
    salary_max = salary_max if salary_max is not None else data.get('salaryMax')
    salary_type = salary_type if salary_type is not None else data.get('salaryType')

    experience = data.get('experience') or data.get('experienceLevel') or data.get('experience_level')
    education = data.get('education') or data.get('educationLevel') or data.get('education_level')

    deadline_raw = data.get('deadline') or data.get('applicationDeadline')
    application_deadline = None
    if deadline_raw:
        try:
            application_deadline = datetime.datetime.fromisoformat(deadline_raw)
        except Exception:
            application_deadline = None

    positions = int(data.get('positionsAvailable')) if data.get('positions') else 1
    featured = 1 if data.get('featured') else 0
    urgent = 1 if data.get('urgent') else 0

    required_skills = data.get('requiredSkills') or []
    bonus_skills = data.get('bonusSkills') or []

    job_type = normalize_enum(raw_job_type, 'job_type')
    if not job_type:
        return None, 'Job type is required.'

    experience = normalize_enum(experience, 'experience_level')
    if not experience:
        return None, 'Experience level is required.'

    education = normalize_enum(education, 'education_level')

    if application_deadline and application_deadline.date() < datetime.date.today():
        return None, 'Application deadline must be today or later.'

    payload = {
        'company_id': company_id,
        'title': title,
        'description': description,
        'requirements': requirements,
        'benefits': benefits,
        'job_type': job_type,
        'location': location,
        'department': department,
        'experience_level': experience,
        'education_level': education,
        'salary_min': salary_min,
        'salary_max': salary_max,
        'salary_type': salary_type,
        'positions_available': positions,
        'application_deadline': application_deadline.strftime('%Y-%m-%d %H:%M:%S') if application_deadline else None,
        'is_featured': featured,
        'is_urgent': urgent,
        'required_skills': json.dumps(required_skills, ensure_ascii=False),
        'bonus_skills': json.dumps(bonus_skills, ensure_ascii=False),
    }

    status_value = data.get('status')
    if status_value:
        payload['status'] = status_value.strip().lower()
    elif default_status is not None:
        payload['status'] = default_status
    return payload, None

def get_table_columns(conn, table_name):
    """Return set of column names for the given table."""
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT COLUMN_NAME
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s
            """,
            (db_config.get('database'), table_name)
        )
        return {row[0] for row in cur.fetchall()}
    except Exception as e:
        current_app.logger.exception("Could not introspect columns for %s: %s", table_name, e)
        return set()
    finally:
        cur.close()


def ensure_jobs_skill_columns(conn):
    """Add missing required/bonus skills columns to jobs so the UI can persist them."""
    cur = conn.cursor()
    try:
        cols = get_table_columns(conn, 'jobs') or set()
        added = False
        if 'required_skills' not in cols:
            cur.execute(
                "ALTER TABLE jobs ADD COLUMN required_skills LONGTEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL"
            )
            added = True
        else:
            cur.execute(
                "ALTER TABLE jobs MODIFY COLUMN required_skills LONGTEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL"
            )
        if 'bonus_skills' not in cols:
            cur.execute(
                "ALTER TABLE jobs ADD COLUMN bonus_skills LONGTEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL"
            )
            added = True
        else:
            cur.execute(
                "ALTER TABLE jobs MODIFY COLUMN bonus_skills LONGTEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL"
            )
        if added:
            conn.commit()
    except Exception as exc:
        app.logger.debug("Unable to auto-create job skill columns: %s", exc)
    finally:
        try:
            cur.close()
        except Exception:
            pass

def mark_expired_jobs(conn):
    """Update job statuses for expired or filled postings."""
    job_cols = get_table_columns(conn, 'jobs') or set()
    if 'status' not in job_cols:
        return

    has_deadline = 'application_deadline' in job_cols
    has_positions = 'positions_available' in job_cols
    cur = conn.cursor()
    updated = False
    try:
        if has_deadline:
            cur.execute(
                """
                UPDATE jobs
                SET status = 'expired'
                WHERE application_deadline IS NOT NULL
                  AND application_deadline < UTC_TIMESTAMP()
                  AND COALESCE(LOWER(TRIM(status)), '') <> 'expired'
                """
            )
            if cur.rowcount:
                updated = True

        if has_positions:
            app_cols = get_table_columns(conn, 'job_applications') or set()
            status_col = pick_first_column(app_cols, ['application_status', 'status'])
            if status_col:
                cur.execute(f"""
                    UPDATE jobs j
                    LEFT JOIN (
                        SELECT job_id,
                               COUNT(*) AS accepted_count
                        FROM job_applications
                        WHERE COALESCE(LOWER(TRIM({status_col})), '') IN ('accepted','accept','hired','hire','offer','approved')
                        GROUP BY job_id
                    ) agg ON agg.job_id = j.id
                    SET j.status = 'filled'
                    WHERE j.positions_available IS NOT NULL
                      AND COALESCE(agg.accepted_count, 0) >= j.positions_available
                      AND COALESCE(LOWER(TRIM(j.status)), '') NOT IN ('filled', 'expired')
                """)
                if cur.rowcount:
                    updated = True

        if updated:
            conn.commit()
    except Exception as exc:
        current_app.logger.debug("Expired job marking skipped: %s", exc)
    finally:
        try:
            cur.close()
        except Exception:
            pass


def ensure_application_snapshot_columns(conn):
    """Ensure job_applications can store a snapshot of candidate contact/role info."""
    cur = conn.cursor()
    try:
        cols = get_table_columns(conn, 'job_applications') or set()
        definitions = {
            'applied_full_name': 'VARCHAR(255) NULL',
            'applied_email': 'VARCHAR(255) NULL',
            'applied_phone': 'VARCHAR(65) NULL',
            'applied_job_title': 'VARCHAR(255) NULL',
            'applied_job_location': 'VARCHAR(255) NULL',
            'applied_predicted_role': 'VARCHAR(255) NULL',
            'applied_resume_url': 'VARCHAR(500) NULL'
        }
        added = False
        for col, dtype in definitions.items():
            if col not in cols:
                cur.execute(f"ALTER TABLE job_applications ADD COLUMN {col} {dtype}")
                added = True
        if added:
            conn.commit()
    except Exception as exc:
        app.logger.debug("Unable to auto-create application snapshot columns: %s", exc)
    finally:
        try:
            cur.close()
        except Exception:
            pass

def table_exists(conn, table_name):
    """Return True if table exists in current schema."""
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT COUNT(*)
            FROM information_schema.tables
            WHERE table_schema = %s AND table_name = %s
            """,
            (db_config.get('database'), table_name)
        )
        row = cur.fetchone()
        return bool(row and row[0])
    except Exception:
        return False
    finally:
        cur.close()

def pick_first_column(columns, candidates):
    """Return the first matching column name from candidates that exists in columns."""
    for col in candidates:
        if col in columns:
            return col
    return None

def get_job_seeker_pk_column(conn):
    """Return the primary identifier column for job_seekers table."""
    js_columns = get_table_columns(conn, 'job_seekers') or set()
    return pick_first_column(js_columns, ['id', 'job_seeker_id', 'user_id'])

def get_company_id(conn, user_id):
    cur = conn.cursor()
    try:
        cur.execute("SELECT id FROM companies WHERE user_id = %s", (user_id,))
        row = cur.fetchone()
        return row[0] if row else None
    finally:
        cur.close()

def get_job_seeker_id(conn, user_id):
    """Return the job seeker identifier for a given user_id, respecting schema differences."""
    cur = conn.cursor(dictionary=True)
    try:
        pk_col = get_job_seeker_pk_column(conn)
        if not pk_col:
            return None
        cur.execute(f"SELECT {pk_col} AS js_pk, user_id FROM job_seekers WHERE user_id = %s", (user_id,))
        row = cur.fetchone() or {}
        js_pk = row.get('js_pk')
        if js_pk is None and pk_col != 'user_id':
            js_pk = row.get('user_id')
        return js_pk
    finally:
        cur.close()

def get_job_seeker_skills(conn, job_seeker_id, user_id=None):
    """Return skills for a job seeker using available FK/name columns."""
    if not table_exists(conn, 'job_seeker_skills'):
        return []
    cur = conn.cursor(dictionary=True)
    try:
        cols = get_table_columns(conn, 'job_seeker_skills') or set()
        fk_col = pick_first_column(cols, ['job_seeker_id', 'seeker_id', 'user_id', 'candidate_id'])
        name_col = pick_first_column(cols, ['skill_name', 'name', 'skill'])
        if not fk_col or not name_col:
            return []
        fk_val = job_seeker_id if fk_col != 'user_id' else (user_id or job_seeker_id)
        if fk_val is None:
            return []
        cur.execute(f"SELECT {name_col} AS skill FROM job_seeker_skills WHERE {fk_col} = %s", (fk_val,))
        rows = cur.fetchall() or []
        return [r.get('skill') for r in rows if r.get('skill')]
    except Exception:
        current_app.logger.exception("Failed to load job seeker skills")
        return []
    finally:
        cur.close()

def serialize_job_seeker_profile(row):
    """Return a safe subset of profile fields."""
    if not row:
        return {}
    js_id = row.get('id') or row.get('job_seeker_id') or row.get('user_id')
    full_name = row.get('full_name') or row.get('name')
    if not full_name:
        first = row.get('first_name') or ''
        last = row.get('last_name') or ''
        full_name = f"{first} {last}".strip() or None
    bio_val = row.get('bio') or row.get('summary') or row.get('about') or row.get('description')
    profile = {
        'id': js_id,
        'user_id': row.get('user_id'),
        'full_name': full_name,
        'email': row.get('email'),
        'location': row.get('location'),
        'experience_level': row.get('experience_level'),
        'current_title': row.get('current_title'),
        'bio': bio_val,
        'phone': row.get('phone'),
        'profile_picture_url': row.get('profile_picture_url'),
        'resume_url': row.get('resume_url'),
        'resume_stored_name': row.get('resume_url'),
        'match_score': row.get('match_score'),
        'created_at': row.get('created_at'),
        'updated_at': row.get('updated_at'),
        'education_level': row.get('education_level'),
        'education_summary': row.get('education_summary') or row.get('education_details'),
        'predicted_job_role': row.get('predicted_job_role') or row.get('ai_job_role') or row.get('target_role'),
        'predicted_salary': row.get('predicted_salary'),
        'predicted_experience_years': row.get('predicted_experience_years') or row.get('experience_years'),
        'manual_experience_years': row.get('manual_experience_years'),
    }
    resume_full = build_cv_url(profile.get('resume_url'))
    profile['resume_url_full'] = resume_full
    if resume_full:
        profile['resume_url'] = resume_full
    # Normalize avatar URL
    avatar = profile.get('profile_picture_url')
    if avatar and not avatar.startswith('http'):
        safe_avatar = os.path.basename(avatar)
        # if stored with subdir, keep it
        if os.path.dirname(avatar):
            profile['profile_picture_url'] = f"/uploads/{avatar}"
        else:
            profile['profile_picture_url'] = f"/uploads/avatars/{safe_avatar}"
    return profile

def fetch_job_seeker_profile(conn, user_id):
    cur = conn.cursor(dictionary=True)
    try:
        cur.execute("SELECT * FROM job_seekers WHERE user_id = %s", (user_id,))
        row = cur.fetchone()
        if not row:
            return None
        profile = serialize_job_seeker_profile(row)
        js_id = profile.get('id')
        cv_skills = []

        if not profile.get('email'):
            cur.execute("SELECT email FROM users WHERE id = %s", (profile.get('user_id'),))
            urow = cur.fetchone()
            if urow and isinstance(urow, dict):
                profile['email'] = urow.get('email')

        if js_id and table_exists(conn, 'cv_analysis'):
            cv_cols = get_table_columns(conn, 'cv_analysis') or set()
            select_candidates = [
                'cv_file_url', 'skills_detected', 'experience_level_detected',
                'predicted_job_role', 'predicted_salary', 'predicted_experience_years',
                'match_score', 'ai_prediction', 'education_detected',
                'education_level_detected', 'top_job_roles'
            ]
            select_cols = [col for col in select_candidates if col in cv_cols]
            if select_cols:
                cur.execute(
                    f"""
                    SELECT {', '.join(select_cols)}
                    FROM cv_analysis
                    WHERE job_seeker_id = %s
                    ORDER BY analysis_date DESC, id DESC
                    LIMIT 1
                    """,
                    (js_id,)
                )
                cv = cur.fetchone()
                if cv:
                    skills_raw = cv.get('skills_detected')
                    skills_list = []
                    if isinstance(skills_raw, str):
                        try:
                            skills_list = json.loads(skills_raw)
                        except Exception:
                            skills_list = []
                    elif isinstance(skills_raw, (list, tuple)):
                        skills_list = list(skills_raw)
                    cv_skills = skills_list or cv_skills

                    education_raw = cv.get('education_detected')
                    education_list = []
                    if isinstance(education_raw, str):
                        try:
                            education_list = json.loads(education_raw)
                        except Exception:
                            education_list = []
                    elif isinstance(education_raw, (list, tuple)):
                        education_list = list(education_raw)

                    education_level_detected = cv.get('education_level_detected')

                    top_roles_raw = cv.get('top_job_roles')
                    top_roles = []
                    if isinstance(top_roles_raw, str):
                        try:
                            top_roles = json.loads(top_roles_raw)
                        except Exception:
                            top_roles = []
                    elif isinstance(top_roles_raw, (list, tuple)):
                        top_roles = list(top_roles_raw)

                    cv_file_url_full = build_cv_url(cv.get('cv_file_url'))

                    if not profile.get('predicted_job_role'):
                        profile['predicted_job_role'] = cv.get('predicted_job_role')
                    if profile.get('predicted_salary') is None:
                        profile['predicted_salary'] = cv.get('predicted_salary')
                    if profile.get('predicted_experience_years') is None:
                        profile['predicted_experience_years'] = cv.get('predicted_experience_years')
                    if profile.get('match_score') is None:
                        profile['match_score'] = cv.get('match_score')
                    ai_raw = cv.get('ai_prediction')
                    ai_prediction_data = None
                    if ai_raw:
                        if isinstance(ai_raw, str):
                            try:
                                ai_prediction_data = json.loads(ai_raw)
                            except Exception:
                                ai_prediction_data = None
                        elif isinstance(ai_raw, dict):
                            ai_prediction_data = ai_raw
                    if ai_prediction_data:
                        profile['ai_prediction'] = ai_prediction_data
                        level_predicted = ai_prediction_data.get('education_level_predicted')
                        if level_predicted and not profile.get('education_level'):
                            profile['education_level'] = level_predicted
                    final_top_roles = top_roles
                    if not final_top_roles and ai_prediction_data:
                        potential = ai_prediction_data.get('top_job_roles')
                        if isinstance(potential, (list, tuple)):
                            final_top_roles = list(potential)
                    if final_top_roles:
                        profile['top_job_roles'] = final_top_roles
                    if education_list:
                        profile['education_detected'] = education_list
                    if not profile.get('education_level') and education_level_detected:
                        profile['education_level'] = education_level_detected
                    profile['cv_analysis'] = {
                        'cv_file_url': cv_file_url_full or profile.get('resume_url'),
                        'cv_file_name': os.path.basename(cv.get('cv_file_url') or '') or os.path.basename(profile.get('resume_stored_name') or '') or '',
                        'skills_detected': skills_list,
                        'skills_detected_count': len(skills_list),
                        'experience_level_detected': cv.get('experience_level_detected'),
                        'match_score': cv.get('match_score'),
                        'predicted_job_role': cv.get('predicted_job_role'),
                        'predicted_salary': cv.get('predicted_salary'),
                        'predicted_experience_years': cv.get('predicted_experience_years'),
                        'education_detected': education_list,
                        'education_level_detected': education_level_detected,
                        'top_job_roles': final_top_roles,
                        'ai_prediction': ai_prediction_data
                    }
        if profile.get('id') or profile.get('user_id'):
            skills_from_table = get_job_seeker_skills(conn, profile.get('id'), profile.get('user_id'))
            profile['skills'] = skills_from_table or cv_skills
        else:
            profile['skills'] = cv_skills
        return profile
    finally:
        cur.close()

def generate_role_questions(role, count=5):
    """Generate interview questions tailored to a role using OpenAI if available, else fallback templates."""
    base_role = role or "software engineer"
    if openai_client:
        try:
            prompt = (
                f"Create {count} concise technical interview questions for a {base_role}. "
                "Cover fundamentals, problem-solving, and practical scenarios. "
                "Return only the questions as a numbered list without extra text."
            )
            completion = openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "system", "content": "You generate concise interview questions."},
                          {"role": "user", "content": prompt}],
                max_tokens=400,
                temperature=0.7,
            )
            content = completion.choices[0].message.content
            questions = []
            for line in content.splitlines():
                line = line.strip()
                # strip leading numbers/bullets
                line = re.sub(r"^\d+[\).\s-]*", "", line)
                if line:
                    questions.append(line)
                if len(questions) >= count:
                    break
            if questions:
                return questions
        except Exception as e:
            current_app.logger.warning("OpenAI question generation failed: %s", e)
    # fallback
    templates = [
        f"Describe a recent project where you acted as a {base_role}. What challenges did you solve?",
        f"How do you ensure code quality and reliability in {base_role} work?",
        f"Explain a time you optimized performance or scalability.",
        f"How do you debug a production issue end-to-end?",
        f"What would you improve about a current {base_role} stack you know?",
    ]
    return templates[:count]

def evaluate_answer(question, answer, role=None):
    """Return feedback and a rough score for an answer."""
    if not answer:
        return {"feedback": "No answer captured.", "score": 0}
    if openai_client:
        try:
            prompt = (
                f"You are evaluating an interview answer for a {role or 'candidate'}. "
                "Provide brief, constructive feedback (max 3 sentences) and a score 0-100."
                f"\nQuestion: {question}\nAnswer: {answer}\nRespond as JSON with keys feedback and score."
            )
            completion = openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=200,
                response_format={"type": "json_object"}
            )
            content = completion.choices[0].message.content
            parsed = json.loads(content)
            fb = parsed.get("feedback") or parsed.get("comment") or ""
            score = parsed.get("score")
            try:
                score = int(score)
            except Exception:
                score = None
            return {"feedback": fb or "Captured.", "score": score}
        except Exception as e:
            current_app.logger.warning("OpenAI evaluation failed: %s", e)
    # fallback simple heuristic
    ok = len(answer.split()) >= 10
    fb = "Good start. Add more specifics and examples." if ok else "Please expand your answer with details and examples."
    return {"feedback": fb, "score": 60 if ok else 30}

def normalize_rating(score):
    """Normalize AI score (0-100) into DB-safe rating scale (0-5)."""
    if score is None:
        return None
    try:
        val = float(score)
    except Exception:
        return None
    if val > 5:
        val = val / 20.0
    val = round(val, 1)
    return max(0, min(5, val))

def update_application_interview_score(app_id, rating):
    """Persist the latest interview rating into job_applications.interview_score when available."""
    if rating is None:
        return
    conn = get_db_connection()
    if not conn:
        return
    cur = None
    try:
        cols = get_table_columns(conn, 'job_applications') or set()
        if 'interview_score' not in cols:
            return
        cur = conn.cursor()
        cur.execute("UPDATE job_applications SET interview_score=%s WHERE id=%s", (rating, app_id))
        conn.commit()
    except Exception as e:
        current_app.logger.warning("Failed to update application interview_score for app %s: %s", app_id, e)
    finally:
        try:
            if cur:
                cur.close()
            conn.close()
        except Exception:
            pass

# ===== VirtualMeeting helpers (ported) =====

def vm_transcribe_audio(file_storage):
    """Transcribe an uploaded audio file using OpenAI; returns text or empty string on failure."""
    if not openai_client:
        current_app.logger.warning("OpenAI client not configured; transcription unavailable")
        return ""
    if not file_storage:
        return ""
    tmp_path = None
    try:
        suffix = os.path.splitext(file_storage.filename or "")[1] or ".wav"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp_path = tmp.name
            file_storage.save(tmp_path)
        with open(tmp_path, "rb") as f:
            transcript = openai_client.audio.transcriptions.create(
                model="gpt-4o-transcribe",
                file=f,
            )
        return transcript.text.strip() if transcript else ""
    except Exception as e:
        current_app.logger.warning("VM transcription failed: %s", e)
        return ""
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass


def vm_text_to_speech_to_wav(text):
    """Generate TTS audio for the given text and save under uploads/audio; returns (filename, url) or None."""
    if not openai_client or not text:
        return None
    fname = f"tts_{uuid.uuid4().hex}.wav"
    dest = os.path.join(AUDIO_UPLOAD_DIR, fname)
    try:
        response = openai_client.audio.speech.create(
            model="gpt-4o-mini-tts",
            voice="alloy",
            input=text,
        )
        response.stream_to_file(dest)
        return fname, f"/uploads/audio/{fname}"
    except Exception as e:
        current_app.logger.warning("VM TTS failed: %s", e)
        return None


def _normalize_vm_question(text, question_number: int):
    """Normalize question text and enforce consistent numbering."""
    if not text:
        return text
    # Strip any markdown headers or repeated numbering (e.g., "### Question 2 of 5:")
    text = re.sub(
        r"\s*#+\s*question\s*\d+(?:\s*of\s*\d+)?\s*[:\-\.\)]*\s*",
        " ",
        text,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(
        r"^\s*(?:[*\-]\s*)?(?:#+\s*)?(?:question\s*\d+(?:\s*of\s*\d+)?|q\s*\d+|\d+[\.\)])\s*[:\-\.\)]*\s*",
        "",
        text,
        flags=re.IGNORECASE,
    ).strip()
    return cleaned


def _infer_last_vm_question_number(history):
    """Return the last question number found in assistant history, or 0 if none."""
    if not history:
        return 0
    for msg in reversed(history):
        if msg.get('role') != 'assistant':
            continue
        content = msg.get('content') or ""
        m = re.search(r"\bquestion\s*(\d+)", content, flags=re.IGNORECASE)
        if m:
            try:
                return int(m.group(1))
            except Exception:
                return 0
    return 0


def vm_generate_interview_question(history, job_role: str, question_number: int):
    """Structured question generator (5-question interview) adapted from VirtualMeeting."""
    role = job_role or "candidate"
    if not openai_client:
        raise RuntimeError("OpenAI client not configured")
    if question_number > 5:
        return "Interview complete. Thank you."
    session_seed = uuid.uuid4().hex  # encourage variety between sessions

    # Prevent regressions: if history already contains Question N, next should be N+1
    last_q = _infer_last_vm_question_number(history)
    if last_q >= question_number:
        question_number = last_q + 1

    system_prompt = f"""
    You are an expert technical interviewer for IT positions. Your role is to conduct a structured technical interview for a {role} position.

    INTERVIEW STRUCTURE (5-question interview):
    - Ask exactly 5 technical questions total (numbered 1 through 5)
    - Each question should be relevant to the {role} role
    - Questions should progress from fundamental to advanced concepts
    - Focus on practical skills, problem-solving, and real-world scenarios
    - After each answer, provide brief constructive feedback and ask the next question
    - Keep questions clear and concise

    CURRENT PROGRESS: Question {question_number} of 5

    IMPORTANT:
    - Do NOT include the question number; it will be added automatically by the system
    - Provide brief feedback on the previous answer before asking the next question
    - Make sure questions are job-specific and technical
    - End your response with the next question
    - Rotate topics so first questions are not repeated across sessions; choose from architecture, lifecycle, data, performance, testing, security, tooling, scalability. Avoid reusing prior phrasing.
    - Do not exceed 5 questions in total for this interview.
    - Session seed: {session_seed} (use to vary output)
    """

    user_prompt = (
        f"Start the technical interview for {role} position. Ask the first technical question."
        if question_number == 1 else
        "Based on the conversation history, provide brief feedback and ask the next appropriate technical question."
    )

    try:
        completion = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                *history,
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.95,
            max_tokens=500,
        )
        raw_question = completion.choices[0].message.content.strip()
        return _normalize_vm_question(raw_question, question_number)
    except Exception as e:
        current_app.logger.warning("VM question generation failed: %s", e)
        raise


def vm_generate_interview_review(job_role: str, interview_data: list):
    """Generate a concise review of the interview, adapted from VirtualMeeting."""
    role = job_role or "candidate"
    if not openai_client:
        return "AI review unavailable; please review answers manually."
    system_prompt = f"""
    You are an experienced HR manager and technical hiring expert. Provide a concise assessment of a candidate's performance in a technical interview for a {role} position.

    ASSESSMENT CRITERIA:
    1. Technical Knowledge (40%)
    2. Problem-Solving Skills (30%)
    3. Communication Skills (20%)
    4. Confidence & Honesty (10%)

    INTERVIEW DATA:
    {json.dumps(interview_data, indent=2)}

    Provide:
    - Overall score (0-100)
    - Pass/Fail recommendation
    - Strengths
    - Areas for improvement
    - Brief breakdown per question
    """
    try:
        completion = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Evaluate this interview for {role} and provide the assessment."},
            ],
            temperature=0.3,
            max_tokens=900,
        )
        return completion.choices[0].message.content.strip()
    except Exception as e:
        current_app.logger.warning("VM review generation failed: %s", e)
        return "AI review unavailable; please review answers manually."


def upsert_interview(app_id, payload: dict):
    """Upsert into interviews table using provided payload keys that exist in the table."""
    conn = get_db_connection()
    if not conn:
        return
    cur = None
    try:
        cols = get_table_columns(conn, 'interviews') or set()
        if not cols or 'application_id' not in cols:
            return
        filtered = {k: v for k, v in payload.items() if v is not None and k in cols}
        if not filtered:
            return
        cur = conn.cursor()
        cur.execute("SELECT id FROM interviews WHERE application_id=%s LIMIT 1", (app_id,))
        row = cur.fetchone()
        if row:
            set_parts = ", ".join([f"{c}=%s" for c in filtered.keys()])
            cur.execute(
                f"UPDATE interviews SET {set_parts} WHERE application_id=%s",
                (*filtered.values(), app_id)
            )
        else:
            col_names = ['application_id'] + list(filtered.keys())
            placeholders = ", ".join(["%s"] * len(col_names))
            cur.execute(
                f"INSERT INTO interviews ({', '.join(col_names)}) VALUES ({placeholders})",
                (app_id, *filtered.values())
            )
        conn.commit()
    except Exception as e:
        current_app.logger.warning("Interview upsert failed for app %s: %s", app_id, e)
    finally:
        try:
            if cur:
                cur.close()
            conn.close()
        except Exception:
            pass

def get_interview_row(app_id):
    """Return the latest interview row for an application_id, or None."""
    conn = get_db_connection()
    if not conn:
        return None
    cur = None
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT * FROM interviews WHERE application_id=%s ORDER BY updated_at DESC, id DESC LIMIT 1", (app_id,))
        return cur.fetchone()
    except Exception:
        return None
    finally:
        try:
            if cur:
                cur.close()
            conn.close()
        except Exception:
            pass

def get_conversation_for_seeker(conn, conv_id, js_id, user_id=None):
    cur = conn.cursor(dictionary=True)
    try:
        ids = []
        if js_id:
            ids.append(js_id)
        if user_id and user_id != js_id:
            ids.append(user_id)
        if not ids:
            return None
        placeholders = ",".join(["%s"] * len(ids))
        params = tuple([conv_id] + ids)
        cur.execute(f"SELECT * FROM conversations WHERE id=%s AND job_seeker_id IN ({placeholders})", params)
        return cur.fetchone()
    finally:
        cur.close()

def list_conversations_for_seeker(conn, js_id, user_id=None):
    cur = conn.cursor(dictionary=True)
    try:
        ids = []
        if js_id:
            ids.append(js_id)
        if user_id and user_id != js_id:
            ids.append(user_id)
        if not ids:
            return []
        placeholders = ",".join(["%s"] * len(ids))
        cur.execute(
            f"""
            SELECT c.id, c.company_id, co.company_name AS company_name,
                   c.job_id, j.title AS job_title,
                   c.last_message_text, c.last_message_at,
                   c.unread_count_seeker
            FROM conversations c
            LEFT JOIN companies co ON co.id = c.company_id
            LEFT JOIN jobs j ON j.id = c.job_id
            WHERE c.job_seeker_id IN ({placeholders})
            ORDER BY COALESCE(c.last_message_at, c.created_at) DESC, c.id DESC
            """,
            tuple(ids)
        )
        return cur.fetchall() or []
    finally:
        cur.close()

def compute_match_score(ai_prediction, detected_skills=None, education_level=None, candidate_experience=None):
    """Return a 0-100 score based on role, salary, experience, and detected skills."""
    if not ai_prediction:
        return 0

    def _to_float(value):
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    score = 0.0

    if ai_prediction.get('job_role'):
        score += 25.0

    salary_value = _to_float(ai_prediction.get('salary'))
    if salary_value is not None:
        salary_value = max(0.0, min(200000.0, salary_value))
        score += (salary_value / 200000.0) * 25.0

    exp_value = candidate_experience if candidate_experience is not None else ai_prediction.get('experience_years')
    exp_value = _to_float(exp_value)
    if exp_value is not None:
        exp_value = max(0.0, min(15.0, exp_value))
        score += (exp_value / 15.0) * 20.0

    skills_source = detected_skills if detected_skills is not None else ai_prediction.get('detected_skills') or ai_prediction.get('skills_detected')
    skills_count = 0
    if isinstance(skills_source, (list, tuple, set)):
        skills_count = len(skills_source)
    elif isinstance(skills_source, dict):
        skills_count = len(skills_source)
    elif isinstance(skills_source, str):
        skills_count = 1 if skills_source.strip() else 0
    elif skills_source:
        skills_count = 1
    skills_used = min(skills_count, 10)
    score += (skills_used / 10.0) * 30.0

    score = max(0.0, min(100.0, score))
    return int(round(score))


def _sanitize_for_json(value):
    """Convert Decimal and other non-JSON-native types to safe primitives."""
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dict):
        return {k: _sanitize_for_json(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_sanitize_for_json(v) for v in value]
    return value

ALLOWED_EXTENSIONS = {'pdf', 'png'}
IMAGE_EXTENSIONS = {'png', 'jpg', 'jpeg'}
# Store CV uploads in the shared /uploads/cvs directory (not under frontend)
UPLOAD_FOLDER = os.path.join(PROJECT_ROOT, 'uploads', 'cvs')
AVATAR_FOLDER = os.path.join(os.getcwd(), 'uploads', 'avatars')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(AVATAR_FOLDER, exist_ok=True)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def allowed_image_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in IMAGE_EXTENSIONS

def build_cv_url(filename):
    """Return an external URL for a stored CV filename."""
    if not filename:
        return None
    if filename.startswith('http://') or filename.startswith('https://'):
        return filename
    safe_name = os.path.basename(filename)
    try:
        return url_for('serve_uploaded_cv', filename=safe_name, _external=True)
    except Exception:
        return f"/uploads/cvs/{safe_name}"

def extract_skills_from_text(text):
    """Simple keyword-based skill extractor."""
    if not text:
        return []
    skill_keywords = [
        'python','java','javascript','typescript','react','vue','angular','node',
        'sql','mysql','postgres','mongodb','docker','kubernetes','aws','azure',
        'gcp','terraform','ansible','git','linux','django','flask','fastapi',
        'pandas','numpy','scikit-learn','tensorflow','pytorch','ui/ux','figma',
        'photoshop','illustrator','css','html','sass','less'
    ]
    text_lc = text.lower()
    found = set()
    for kw in skill_keywords:
        pattern = r'(?<![a-z0-9])' + re.escape(kw) + r'(?![a-z0-9])'
        if re.search(pattern, text_lc):
            found.add(kw)
    return sorted(found)

EDUCATION_DEGREE_KEYWORDS = {
    'phd': 'PhD',
    'doctor of': 'PhD',
    'master of business administration': 'MBA',
    'mba': 'MBA',
    'masters': 'MSc',
    "master's": 'MSc',
    'master': 'MSc',
    'master of science': 'MSc',
    'master of engineering': 'MEng',
    'msc': 'MSc',
    'm.sc': 'MSc',
    'graduate diploma': 'Graduate Diploma',
    'graduate certificate': 'Grad Certificate',
    'bachelor of science': 'BSc',
    'b.sc': 'BSc',
    'bachelor of engineering': 'BEng',
    'b eng': 'BEng',
    'bachelor of technology': 'BTech',
    'btech': 'BTech',
    "bachelor's": 'BSc',
    'bachelor': 'BSc',
    'associate degree': 'Associate',
    'associate of science': 'Associate',
    'diploma': 'Diploma',
    'high school': 'High School',
    'secondary school': 'High School',
}

EDUCATION_FIELD_KEYWORDS = {
    'computer science': 'Computer Science',
    'information technology': 'Information Technology',
    'data science': 'Data Science',
    'engineering': 'Engineering',
    'business administration': 'Business Administration',
    'finance': 'Finance',
    'information systems': 'Information Systems',
    'software engineering': 'Software Engineering',
    'electrical engineering': 'Electrical Engineering',
    'mechanical engineering': 'Mechanical Engineering',
    'civil engineering': 'Civil Engineering',
    'mathematics': 'Mathematics',
    'statistics': 'Statistics',
    'psychology': 'Psychology',
    'arts': 'Arts',
    'law': 'Law',
}

EDUCATION_LEVEL_PRIORITY = {
    'phd': 5,
    'master': 4,
    'bachelor': 3,
    'associate': 2,
    'high-school': 1,
    'any': 0,
}

EDUCATION_LEVEL_KEYWORDS = {
    'phd': ['phd', 'doctor', 'dphil'],
    'master': ['master', 'msc', 'mba', 'm.sc', 'm.a', 'm.eng'],
    'bachelor': ['bachelor', 'b.sc', 'b.eng', "bachelor's"],
    'associate': ['associate', 'diploma', 'certificate'],
    'high-school': ['high school', 'secondary school', 'gcse', 'a level'],
}

def _normalize_education_entry(entry):
    if not entry:
        return None
    cleaned = re.sub(r'\s+', ' ', entry.strip())
    if not cleaned:
        return None
    lower = cleaned.lower()
    degree_label = None
    for keyword, label in EDUCATION_DEGREE_KEYWORDS.items():
        if keyword in lower:
            degree_label = label
            break
    if not degree_label:
        if 'bachelor' in lower:
            degree_label = 'BSc'
        elif 'master' in lower or 'msc' in lower or 'm.sc' in lower:
            degree_label = 'MSc'
        elif 'phd' in lower or 'doctor' in lower:
            degree_label = 'PhD'
    fields = []
    for field_keyword, field_label in EDUCATION_FIELD_KEYWORDS.items():
        if field_keyword in lower and field_label not in fields:
            fields.append(field_label)
    if fields:
        field_text = ", ".join(fields)
        if degree_label:
            return f"{degree_label} ({field_text})"
        return field_text
    if degree_label:
        return degree_label
    # fallback: return title-cased snippet if it contains at least one keyword
    if any(kw in lower for kw in EDUCATION_FIELD_KEYWORDS.keys()) or any(
        kw in lower for kw in EDUCATION_LEVEL_KEYWORDS['bachelor'] + EDUCATION_LEVEL_KEYWORDS['master']
    ):
        return cleaned.title()
    return None


def extract_education_entries(text, max_entries=8):
    """Extract normalized education lines from resume text."""
    if not text:
        return []
    lines = [ln.strip() for ln in re.split(r'[\r\n]+', text) if ln.strip()]
    entries = []
    for line in lines:
        lower = line.lower()
        if any(keyword in lower for keyword in EDUCATION_DEGREE_KEYWORDS.keys()) or any(
            keyword in lower for keyword in EDUCATION_FIELD_KEYWORDS.keys()
        ):
            normalized = _normalize_education_entry(line)
            if normalized:
                entries.append(normalized)
        if len(entries) >= max_entries:
            break
    deduped = []
    seen = set()
    for entry in entries:
        if entry not in seen:
            seen.add(entry)
            deduped.append(entry)
    return deduped


def infer_education_level_from_entries(entries):
    """Return the highest inferred education level from detected entries."""
    best = None
    best_score = -1
    for entry in entries:
        lower = entry.lower()
        for level, keywords in EDUCATION_LEVEL_KEYWORDS.items():
            if any(keyword in lower for keyword in keywords):
                score = EDUCATION_LEVEL_PRIORITY.get(level, 0)
                if score > best_score:
                    best_score = score
                    best = level
    return best


def extract_text_from_file(file_path):
    """Best-effort OCR for PDF/PNG using pytesseract."""
    if not OCR_AVAILABLE:
        return ""
    if not os.path.exists(file_path):
        return ""
    ext = os.path.splitext(file_path)[1].lower()
    text = ""
    try:
        print(f"OCR start: {file_path} (ext={ext})")
        if ext == '.pdf' and convert_from_path:
            images = convert_from_path(
                file_path,
                dpi=300,
                poppler_path=POPPLER_BIN if POPPLER_BIN else None
            )
            if images:
                text = pytesseract.image_to_string(images[0])
        elif Image and ext in {'.png', '.jpg', '.jpeg', '.tif', '.tiff'}:
            img = Image.open(file_path)
            text = pytesseract.image_to_string(img)
    except Exception as e:
        print(f"OCR extraction failed for {file_path}: {e}")
    if text:
        text = text.strip()
    print(f"OCR extracted {len(text) if text else 0} chars from {file_path}")
    return text or ""

# ============ FRONTEND PAGES ============
@app.route('/')
def index():
    """Serve the main landing page"""
    return app.send_static_file('index.html')

@app.route('/css/<path:filename>')
def serve_css(filename):
    path = STATIC_DIRS.get('css')
    return send_from_directory(path, filename) if path else ("Not found", 404)

@app.route('/js/<path:filename>')
def serve_js(filename):
    path = STATIC_DIRS.get('js')
    return send_from_directory(path, filename) if path else ("Not found", 404)

@app.route('/pages/<path:filename>')
def serve_pages_static(filename):
    path = STATIC_DIRS.get('pages')
    return send_from_directory(path, filename) if path else ("Not found", 404)

@app.route('/assets/<path:filename>')
def serve_assets(filename):
    path = STATIC_DIRS.get('assets')
    return send_from_directory(path, filename) if path else ("Not found", 404)

@app.route('/uploads/<path:filename>')
def serve_uploads(filename):
    path = STATIC_DIRS.get('uploads')
    return send_from_directory(path, filename) if path else ("Not found", 404)

@app.route('/api', methods=['GET'])
def api_root():
    """Simple health check for frontend status pings."""
    conn = get_db_connection()
    status = "Database Connected" if conn else "Database Failed"
    if conn:
        conn.close()
    return jsonify({'message': 'API Online', 'db_status': status}), 200

@app.route('/api/auth/logout', methods=['POST', 'OPTIONS'])
def api_logout():
    """Stateless logout endpoint for audit/logging; clients clear their own tokens."""
    return jsonify({'message': 'Logged out'}), 200

@app.route('/<path:path>')
def serve_frontend(path):
    """Serve frontend pages"""
    try:
        return app.send_static_file(path)
    except:
        return "Page not found", 404

@app.route('/uploads/cvs/<path:filename>')
def serve_uploaded_cv(filename):
    """Serve uploaded CV files."""
    return send_from_directory(UPLOAD_FOLDER, filename)

# In your Flask app (add these routes and update existing ones)
@app.route('/api/auth/register', methods=['POST'])
def unified_register():
    """Handle registration for all user types"""
    conn = get_db_connection()
    if not conn:
        return jsonify({'error': 'Database connection failed'}), 500
    
    cursor = None
    try:
        data = request.get_json(silent=True)
        if not data:
            data = request.form.to_dict() or {}
        if not data:
            return jsonify({'error': 'Invalid payload'}), 400

        path_user_type = None
        if '/job-seeker/' in request.path:
            path_user_type = 'job_seeker'
        elif '/company/' in request.path:
            path_user_type = 'company'
        
        user_type = (data.get('user_type', '') or path_user_type or '').lower()
        if user_type not in ['job_seeker', 'company']:
            return jsonify({'error': 'Invalid user type. Must be job_seeker or company'}), 400
        
        # Common validation
        email = normalize_email(data.get('email', ''))
        if not email:
            return jsonify({'error': 'You have error in format'}), 400
        password = data.get('password', '')
        
        if not email or not password:
            return jsonify({'error': 'Email and password are required'}), 400
        
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT id FROM users WHERE email = %s", (email,))
        if cursor.fetchone():
            return jsonify({'error': 'Email already exists'}), 400

        # Verify code if provided
        verify_code = data.get('verification_code')
        ok, err = validate_verification(conn, email, verify_code) if verify_code else (False, "Verification required")
        if not ok:
            return jsonify({'error': err or 'Verification failed'}), 400
        
        # Hash password
        hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')
        
        # Create user record
        user_columns = get_table_columns(conn, 'users')
        user_fields = []
        user_values = []
        
        def add_user_field(col, val):
            if col in user_columns:
                user_fields.append(col)
                user_values.append(val)
        
        add_user_field('email', email)
        add_user_field('password_hash', hashed_password)
        add_user_field('user_type', user_type)
        add_user_field('is_active', 1)
        add_user_field('created_at', datetime.datetime.utcnow())
        add_user_field('updated_at', datetime.datetime.utcnow())
        
        # Add name field based on user type
        if user_type == 'job_seeker':
            full_name = data.get('full_name') or data.get('fullName') or email.split('@')[0]
            add_user_field('name', full_name)
        elif user_type == 'company':
            company_name = data.get('company_name') or data.get('companyName') or email.split('@')[0]
            add_user_field('name', company_name)
        
        cursor.execute(
            f"INSERT INTO users ({', '.join(user_fields)}) VALUES ({', '.join(['%s'] * len(user_fields))})",
            tuple(user_values)
        )
        user_id = cursor.lastrowid
        
        # Create user type specific profile
        if user_type == 'job_seeker':
            # Create job seeker profile
            job_seeker_columns = get_table_columns(conn, 'job_seekers')
            js_fields = []
            js_values = []
            
            def add_js_field(col, val):
                if col in job_seeker_columns:
                    js_fields.append(col)
                    js_values.append(val)
            
            add_js_field('user_id', user_id)
            add_js_field('full_name', data.get('full_name') or data.get('fullName') or '')
            add_js_field('phone', data.get('phone', ''))
            add_js_field('location', data.get('location', ''))
            add_js_field('current_title', data.get('current_title') or data.get('currentTitle', ''))
            add_js_field('experience_level', data.get('experience_level') or data.get('experienceLevel', ''))
            exp_years_raw = data.get('experience_years') or data.get('experienceYears')
            exp_years_val = None
            if exp_years_raw is not None and exp_years_raw != '':
                try:
                    exp_years_val = float(exp_years_raw)
                except (TypeError, ValueError):
                    exp_years_val = None
                if exp_years_val is not None:
                    add_js_field('manual_experience_years', exp_years_val)
            add_js_field('bio', data.get('bio', ''))
            add_js_field('created_at', datetime.datetime.utcnow())
            add_js_field('updated_at', datetime.datetime.utcnow())
            
            if js_fields:
                cursor.execute(
                    f"INSERT INTO job_seekers ({', '.join(js_fields)}) VALUES ({', '.join(['%s'] * len(js_fields))})",
                    tuple(js_values)
                )
                # Ensure experience_years stored even if column list changed later
                if exp_years_val is not None:
                    try:
                        cursor.execute(
                            "UPDATE job_seekers SET experience_years = %s WHERE user_id = %s",
                            (exp_years_val, user_id)
                        )
                    except Exception:
                        pass
        
        elif user_type == 'company':
            # Create company profile
            company_columns = get_table_columns(conn, 'companies')
            company_fields = []
            company_values = []
            
            def add_company_field(col, val):
                if col in company_columns:
                    company_fields.append(col)
                    company_values.append(val)
            
            add_company_field('user_id', user_id)
            add_company_field('company_name', data.get('company_name') or data.get('companyName', ''))
            add_company_field('industry', data.get('industry', ''))
            add_company_field('company_size', data.get('company_size') or data.get('companySize', ''))
            add_company_field('website', data.get('website', ''))
            add_company_field('description', data.get('description') or data.get('companyDescription', ''))
            add_company_field('contact_email', email)
            add_company_field('phone', data.get('phone') or data.get('companyPhone', ''))
            add_company_field('created_at', datetime.datetime.utcnow())
            add_company_field('updated_at', datetime.datetime.utcnow())
            
            if company_fields:
                cursor.execute(
                    f"INSERT INTO companies ({', '.join(company_fields)}) VALUES ({', '.join(['%s'] * len(company_fields))})",
                    tuple(company_values)
                )
        
        conn.commit()
        
        # Generate token
        token = generate_token(user_id)
        
        # Return user data
        user_response = {
            'id': user_id,
            'email': email,
            'user_type': user_type,
            'name': data.get('full_name') or data.get('company_name') or email.split('@')[0]
        }
        
        return jsonify({
            'message': f'{user_type.replace("_", " ").title()} registration successful',
            'token': token,
            'user': user_response
        }), 201
        
    except Exception as e:
        if conn:
            conn.rollback()
        app.logger.exception(f"Registration error: {e}")
        return jsonify({'error': 'Registration failed', 'detail': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

# Remove the old registration endpoints and keep only this unified one
@app.route('/api/auth/company/register', methods=['POST'])
def company_register():
    conn = get_db_connection()
    if not conn:
        return jsonify({'error': 'Database connection failed'}), 500
    cursor = None 

    try:
        data = request.get_json(silent=True)
        app.logger.info("Raw body: %s", request.data[:200])
        app.logger.info("Parsed JSON: %s", data)

        if data is None:
            return jsonify({
                'error':"Invalid or missing JSON. Make sure you send a JSON body and set 'Content-Type: application/json'."
            }), 400
        
        required_fields = ['companyName', 'companyEmail', 'password']
        for field in required_fields:
            if not data.get(field):
                return jsonify({'error': f'Missing field:{field}'}), 400

        company_email = normalize_email(data.get('companyEmail', ''))
        if not company_email:
            return jsonify({'error': 'You have error in format'}), 400
        cursor = conn.cursor(dictionary=True)

        cursor.execute("SELECT id FROM users WHERE email = %s", (company_email,))
        if cursor.fetchone():
            return jsonify({'error': 'Email already exists'}), 400

        hashed_password = bcrypt.generate_password_hash(data['password']).decode('utf-8')

        user_columns = get_table_columns(conn, 'users')
        user_fields = []
        user_values = []
        def add_user(col, val):
            if col in user_columns:
                user_fields.append(col)
                user_values.append(val)
        add_user('email', company_email)
        add_user('password_hash', hashed_password)
        add_user('user_type', 'company')
        add_user('is_active', 1)
        add_user('created_at', datetime.datetime.utcnow())
        add_user('updated_at', datetime.datetime.utcnow())

        cursor.execute(
            f"INSERT INTO users ({', '.join(user_fields)}) VALUES ({', '.join(['%s']*len(user_fields))})",
            tuple(user_values)
        )
        user_id = cursor.lastrowid

        cursor.execute(
            """
            INSERT INTO companies(user_id, company_name, industry, company_size, website, description, phone, contact_email) 
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (user_id, data['companyName'], data['industry'], data['companySize'], data['website'], data['companyDescription'], data.get('phone'), data['companyEmail'])
        )

        conn.commit()
        
        token = generate_token(user_id)
        
        return jsonify({
            'message': 'Registration successful',
            'token': token,
            'user': {
                'id': user_id,
                'email': company_email,
                'user_type': 'company',
                'company_name': data['companyName']
            }
        }), 201

    except Error as e:
        if conn:
            conn.rollback()
        app.logger.exception(f"DB Error during company_register: {e}")
        return jsonify({'error':'Database error', 'detail': str(e)}), 500
    
    except Exception as e:
        if conn:
            conn.rollback()
        app.logger.exception(f"Unexpected error during company_register: {e}")
        return jsonify({'error': 'Internal server error', 'detail':str(e)}), 500
    
    finally:
        try:
            if cursor is not None:
                cursor.close()
        except Exception:
            app.logger.exception("Failed to close cursor")
        try:
            if conn is not None:
                conn.close()
        except Exception:
            app.logger.exception("Failed to close DB connection")

@app.route('/api/auth/job-seeker/register', methods=['POST'])
def legacy_job_seeker_register():
    """Backward-compatible endpoint forwarding to unified_register."""
    return unified_register()

@app.route('/api/auth/login', methods=['POST'])
def login():
    conn = get_db_connection()
    if not conn:
        return jsonify({'error': 'Database connection failed'}), 500
    
    cursor = None
    try:
        data = request.get_json(silent=True)
        app.logger.info("Login payload: %s", data)

        if not data or not data.get('email') or not data.get('password'):
            return jsonify({'error': 'Missing email or password'}), 400
        email = data.get('email')
        if not isinstance(email, str):
            return jsonify({'error': 'Invalid email'}), 400
        password = data.get('password')
        if not isinstance(password, str):
            return jsonify({'error': 'Invalid password'}), 400
        email = email.strip().lower()
        
        cursor = conn.cursor(dictionary=True)

        cursor.execute("SELECT * FROM users WHERE email = %s", (email,))
        user = cursor.fetchone()

        if not user:
            return jsonify({'error': 'User not found'}), 404

        try:
            if not bcrypt.check_password_hash(user['password_hash'], data['password']):
                return jsonify({'error': 'Invalid password'}), 401
        except (ValueError, TypeError) as e:
            app.logger.warning("Password hash check failed for user %s: %s", user.get('email'), e)
            return jsonify({'error': 'Invalid password'}), 401

        base_name = user.get('name') if isinstance(user, dict) else None
        user_details = {
            'id': user['id'],
            'email': user['email'],
            'name': base_name or '',
            'user_type': user['user_type']
        }

        if user['user_type'] == 'company':
            cursor.execute("SELECT * FROM companies WHERE user_id = %s", (user['id'],))
            company = cursor.fetchone()
            if company:
                if not user_details['name'] and company.get('company_name'):
                    user_details['name'] = company['company_name']
                user_details['company'] = company
        
        elif user['user_type'] == 'job_seeker':
            cursor.execute("SELECT * FROM job_seekers WHERE user_id = %s", (user['id'],))
            seeker = cursor.fetchone()
            if seeker:
                if not user_details['name'] and seeker.get('full_name'):
                    user_details['name'] = seeker['full_name']
                user_details['profile'] = seeker

        token = generate_token(user['id'])

        return jsonify({
            'message': 'Login successful',
            'token': token,
            'user': user_details
        }), 200

    except Error as e:
        app.logger.exception("Unexpected error in login: %s", e)
        return jsonify({'error': 'Internal server error','detail': str(e)}), 500
    finally:
        try:
            if cursor is not None:
                cursor.close()
        except Exception:
            app.logger.exception("Failed to close cursor in login")
        try:
            if conn is not None:
                conn.close()
        except Exception:
            app.logger.exception("Failed to close DB connection in login")

@app.route('/api/auth/forgot-password', methods=['POST'])
def forgot_password():
    conn = get_db_connection()
    if not conn:
        return jsonify({'error': 'Database connection failed'}), 500
    cursor = None
    try:
        data = request.get_json(silent=True) or request.form.to_dict() or {}
        email = normalize_email(data.get('email'))
        if not email:
            return jsonify({'error': 'You have error in format'}), 400

        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT id FROM users WHERE email = %s", (email,))
        user = cursor.fetchone()
        if not user:
            # Do not leak existence; respond success
            return jsonify({'message': 'If the email exists, a reset link was created.'}), 200

        table_name, ref_col = ensure_reset_table(conn)
        if not table_name:
            return jsonify({'error': 'Reset table not configured'}), 500

        token = str(uuid.uuid4())
        expires_at = datetime.datetime.utcnow() + datetime.timedelta(hours=1)

        cols = ['token', 'expires_at', 'used', 'created_at']
        vals = [token, expires_at, 0, datetime.datetime.utcnow()]
        cols.insert(0, ref_col)
        vals.insert(0, email if ref_col == 'email' else user['id'])

        placeholders = ', '.join(['%s'] * len(cols))
        cursor.execute(
            f"INSERT INTO {table_name} ({', '.join(cols)}) VALUES ({placeholders})",
            tuple(vals)
        )
        conn.commit()

        try:
            smtp_send(
                email,
                "Your JobGenix password reset token",
                f"Use this token to reset your password. It expires in 1 hour.\n\nToken: {token}"
            )
            return jsonify({'message': 'Reset token created and sent'}), 200
        except Exception as e:
            current_app.logger.warning("SMTP send failed for reset token: %s", e)
            return jsonify({
                'message': 'Reset token created (email failed); using returned token for testing',
                'token': token
            }), 200
    except Exception as e:
        if conn:
            conn.rollback()
        app.logger.exception("Forgot password error: %s", e)
        return jsonify({'error': 'Internal server error', 'detail': str(e)}), 500
    finally:
        try:
            if cursor:
                cursor.close()
        except Exception:
            pass
        try:
            conn.close()
        except Exception:
            pass

@app.route('/api/auth/reset-password', methods=['POST'])
def reset_password():
    conn = get_db_connection()
    if not conn:
        return jsonify({'error': 'Database connection failed'}), 500
    cursor = None
    try:
        data = request.get_json(silent=True) or request.form.to_dict() or {}
        email = normalize_email(data.get('email'))
        token = data.get('token')
        new_password = data.get('password')

        if not email or not token or not new_password:
            return jsonify({'error': 'Missing email, token, or password'}), 400
        if len(new_password) < 8:
            return jsonify({'error': 'Password must be at least 8 characters'}), 400

        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM users WHERE email = %s", (email,))
        user = cursor.fetchone()
        if not user:
            return jsonify({'error': 'Invalid token or email'}), 400

        table_name, ref_col = ensure_reset_table(conn)
        if not table_name:
            return jsonify({'error': 'Reset table not configured'}), 500

        where_ref = ref_col
        ref_val = email if ref_col == 'email' else user['id']
        cursor.execute(
            f"SELECT * FROM {table_name} WHERE token = %s AND {where_ref} = %s AND used = 0 ORDER BY created_at DESC LIMIT 1",
            (token, ref_val)
        )
        row = cursor.fetchone()
        if not row:
            return jsonify({'error': 'Invalid or used token'}), 400

        expires_at = row.get('expires_at')
        if expires_at and expires_at < datetime.datetime.utcnow():
            return jsonify({'error': 'Token expired'}), 400

        hashed = bcrypt.generate_password_hash(new_password).decode('utf-8')
        cursor.execute("UPDATE users SET password_hash = %s WHERE id = %s", (hashed, user['id']))
        cursor.execute(f"UPDATE {table_name} SET used = 1 WHERE id = %s", (row['id'],))
        conn.commit()
        return jsonify({'message': 'Password updated'}), 200
    except Exception as e:
        if conn:
            conn.rollback()
        app.logger.exception("Reset password error: %s", e)
        return jsonify({'error': 'Internal server error', 'detail': str(e)}), 500
    finally:
        try:
            if cursor:
                cursor.close()
        except Exception:
            pass
        try:
            conn.close()
        except Exception:
            pass

def validate_verification(conn, email, code):
    """Return True if a valid, unused code exists for email; marks it used."""
    table_name, ref_col = ensure_verification_table(conn)
    if not table_name:
        return False, "Verification table not found"
    cur = conn.cursor(dictionary=True)
    try:
        cur.execute(
            f"SELECT * FROM {table_name} WHERE {ref_col}=%s AND used=0 ORDER BY created_at DESC LIMIT 1",
            (email,)
        )
        row = cur.fetchone()
        if not row:
            return False, "No verification code found"
        expires_at = row.get('expires_at')
        if expires_at and expires_at < datetime.datetime.utcnow():
            return False, "Verification code expired"
        if str(row.get('token') or '').strip() != str(code).strip():
            return False, "Invalid verification code"
        # mark used
        cur.execute(f"UPDATE {table_name} SET used=1 WHERE id=%s", (row['id'],))
        conn.commit()
        return True, None
    except Exception as e:
        current_app.logger.exception("validate_verification error: %s", e)
        return False, "Internal verification error"
    finally:
        try:
            cur.close()
        except Exception:
            pass

@app.route('/api/auth/send-code', methods=['POST'])
def send_verification_code():
    conn = get_db_connection()
    if not conn:
        return jsonify({'error': 'Database connection failed'}), 500
    cursor = None
    try:
        data = request.get_json(silent=True) or request.form.to_dict() or {}
        email = normalize_email(data.get('email'))
        if not email:
            return jsonify({'error': 'You have error in format'}), 400

        table_name, ref_col = ensure_verification_table(conn)
        if not table_name:
            return jsonify({'error': 'Verification table not configured'}), 500

        code = str(uuid.uuid4())[:8].replace('-', '')
        expires_at = datetime.datetime.utcnow() + datetime.timedelta(minutes=15)

        cursor = conn.cursor()
        cursor.execute(
            f"INSERT INTO {table_name} ({ref_col}, token, expires_at, used, created_at) VALUES (%s, %s, %s, %s, %s)",
            (email, code, expires_at, 0, datetime.datetime.utcnow())
        )
        conn.commit()

        # Attempt to send; if fails, return token for testing
        try:
            smtp_send(email, "Your JobGenix verification code", f"Your verification code is: {code}")
            return jsonify({'message': 'Verification code sent'}), 200
        except Exception as e:
            current_app.logger.warning("SMTP send failed: %s", e)
            return jsonify({'message': 'Verification code generated', 'token': code, 'note': 'SMTP send failed; token returned for testing'}), 200
    except Exception as e:
        if conn:
            conn.rollback()
        current_app.logger.exception("Send code error: %s", e)
        return jsonify({'error': 'Internal server error', 'detail': str(e)}), 500
    finally:
        try:
            if cursor:
                cursor.close()
        except Exception:
            pass
        try:
            conn.close()
        except Exception:
            pass

# ============ DASHBOARD ROUTES ============
def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        # Let CORS preflight pass through without auth
        if request.method == 'OPTIONS':
            return jsonify({'status': 'ok'}), 200
        token = request.headers.get('Authorization')
        if not token:
            return jsonify({'error': 'Token is missing'}), 401
        try:
            if token.startswith('Bearer '):
                token = token[7:]
            data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])
            current_user_id = data['user_id']
        except:
            return jsonify({'error': 'Token is invalid'}), 401
        return f(current_user_id, *args, **kwargs)
    return decorated

@app.route('/api/job-seeker/profile', methods=['GET'])
@token_required
def get_job_seeker_profile(current_user_id):
    conn = get_db_connection()
    if not conn:
        return jsonify({'error': 'Database connection failed'}), 500
    try:
        profile = fetch_job_seeker_profile(conn, current_user_id)
        if not profile:
            return jsonify({'error': 'Job seeker profile not found'}), 404
        return jsonify({'profile': profile}), 200
    except Exception as e:
        app.logger.exception("Failed to load job seeker profile: %s", e)
        return jsonify({'error': 'Internal server error', 'detail': str(e)}), 500
    finally:
        try:
            conn.close()
        except Exception:
            pass

@app.route('/api/company/profile', methods=['GET', 'PUT'])
@token_required
def company_profile(current_user_id):
    conn = get_db_connection()
    if not conn:
        return jsonify({'error': 'Database connection failed'}), 500
    cursor = conn.cursor(dictionary=True)
    try:
        company_columns = get_table_columns(conn, 'companies') or set()
        # Find company row for this user
        cursor.execute("SELECT * FROM companies WHERE user_id = %s", (current_user_id,))
        company = cursor.fetchone()

        if request.method == 'GET':
            if not company:
                return jsonify({'error': 'Company profile not found'}), 404
            return jsonify({'company': company}), 200

        # PUT: update or create if missing
        incoming = request.get_json(silent=True) or {}
        payload = {
            'company_name': incoming.get('company_name') or incoming.get('companyName'),
            'industry': incoming.get('industry'),
            'company_size': incoming.get('company_size') or incoming.get('companySize'),
            'website': incoming.get('website'),
            'contact_email': incoming.get('contact_email') or incoming.get('contactEmail'),
            'description': incoming.get('description') or incoming.get('companyDescription')
        }

        if not company:
            # create new company row for this user
            cols = []
            vals = []
            for col, val in [('user_id', current_user_id)] + list(payload.items()):
                if col in company_columns:
                    cols.append(col)
                    vals.append(val)
            if 'created_at' in company_columns:
                cols.append('created_at')
                vals.append(datetime.datetime.utcnow())
            if 'updated_at' in company_columns:
                cols.append('updated_at')
                vals.append(datetime.datetime.utcnow())
            if not cols:
                return jsonify({'error': 'companies table missing expected columns'}), 500
            placeholders = ', '.join(['%s'] * len(cols))
            cursor.execute(f"INSERT INTO companies ({', '.join(cols)}) VALUES ({placeholders})", tuple(vals))
            conn.commit()
            cursor.execute("SELECT * FROM companies WHERE user_id = %s", (current_user_id,))
            company = cursor.fetchone()
            return jsonify({'company': company, 'message': 'Company profile created'}), 201

        # Update existing
        set_clauses = []
        vals = []
        for col, val in payload.items():
            if val is not None and col in company_columns:
                set_clauses.append(f"{col} = %s")
                vals.append(val)
        if 'updated_at' in company_columns:
            set_clauses.append("updated_at = %s")
            vals.append(datetime.datetime.utcnow())

        if not set_clauses:
            return jsonify({'error': 'No valid fields to update'}), 400

        vals.append(company['id'])
        sql = f"UPDATE companies SET {', '.join(set_clauses)} WHERE id = %s"
        cursor.execute(sql, tuple(vals))
        conn.commit()
        return jsonify({'message': 'Company profile updated'}), 200
    except Exception as e:
        if conn:
            conn.rollback()
        app.logger.exception("Failed to update company profile: %s", e)
        return jsonify({'error': 'Internal server error', 'detail': str(e)}), 500
    finally:
        try:
            cursor.close()
        except Exception:
            pass
        try:
            conn.close()
        except Exception:
            pass

@app.route('/api/company/messages', methods=['GET', 'POST'])
@token_required
def company_messages(current_user_id):
    """
    Simple messaging endpoints for company.
    GET:
      - no params: return conversation summaries (latest message per conversation where company participated)
      - conversation_id=<id>: return messages in that conversation ordered by created_at
    POST:
      - body: {conversation_id, message_text, message_type(optional), file_url/file_name/file_size(optional)}
    """
    conn = get_db_connection()
    if not conn:
        return jsonify({'error': 'Database connection failed'}), 500
    cursor = conn.cursor(dictionary=True)
    try:
        # company id
        cursor.execute("SELECT id FROM companies WHERE user_id = %s", (current_user_id,))
        company = cursor.fetchone()
        if not company:
            return jsonify({'error': 'Company profile not found'}), 403
        company_id = company['id']

        if request.method == 'GET':
            conv_id = request.args.get('conversation_id', type=int)
            if conv_id:
                # Load messages plus participant info if conversations table exists
                conv_cols = get_table_columns(conn, 'conversations') or set()
                if conv_cols:
                    js_pk_col = get_job_seeker_pk_column(conn)
                    join_js = ""
                    js_fields = ", js.full_name AS job_seeker_name, js.current_title"
                    if 'job_seeker_id' in conv_cols and js_pk_col:
                        join_js = f" LEFT JOIN job_seekers js ON js.{js_pk_col} = c.job_seeker_id "
                    else:
                        js_fields = ", NULL AS job_seeker_name, NULL AS current_title"
                    cursor.execute(
                        """
                        SELECT m.*, c.job_seeker_id {js_fields}
                        FROM messages m
                        LEFT JOIN conversations c ON c.id = m.conversation_id
                        {join_js}
                        WHERE m.conversation_id = %s
                        ORDER BY m.created_at ASC, m.id ASC
                        """.format(js_fields=js_fields, join_js=join_js),
                        (conv_id,)
                    )
                else:
                    cursor.execute(
                        """
                        SELECT * FROM messages
                        WHERE conversation_id = %s
                        ORDER BY created_at ASC, id ASC
                        """,
                        (conv_id,)
                    )
                rows = cursor.fetchall()
                return jsonify({'messages': rows}), 200

            # conversation summaries for this company
            conv_cols = get_table_columns(conn, 'conversations') or set()
            if conv_cols:
                js_pk_col = get_job_seeker_pk_column(conn)
                join_js = ""
                js_fields = ", js.full_name AS job_seeker_name, js.current_title"
                if 'job_seeker_id' in conv_cols and js_pk_col:
                    join_js = f" LEFT JOIN job_seekers js ON js.{js_pk_col} = c.job_seeker_id "
                else:
                    js_fields = ", NULL AS job_seeker_name, NULL AS current_title"
                cursor.execute(
                    """
                    SELECT c.id AS conversation_id,
                           c.job_seeker_id
                           {js_fields},
                           m1.message_text,
                           m1.message_type,
                           m1.created_at,
                           m1.sender_type,
                           m1.sender_id,
                           u.email AS job_seeker_email
                    FROM conversations c
                    {join_js}
                    LEFT JOIN users u ON u.id = c.job_seeker_id OR u.id = js.user_id
                    LEFT JOIN messages m1 ON m1.id = (
                        SELECT m.id
                        FROM messages m
                        WHERE m.conversation_id = c.id
                        ORDER BY m.created_at DESC, m.id DESC
                        LIMIT 1
                    )
                    WHERE c.company_id = %s
                    ORDER BY m1.created_at DESC
                    """.format(js_fields=js_fields, join_js=join_js),
                    (company_id,)
                )
                summaries = cursor.fetchall()
            else:
                cursor.execute(
                    """
                    SELECT m1.conversation_id,
                           m1.message_text,
                           m1.message_type,
                           m1.created_at,
                           m1.sender_type,
                           m1.sender_id
                    FROM messages m1
                    INNER JOIN (
                        SELECT conversation_id, MAX(created_at) as max_created
                        FROM messages
                        WHERE conversation_id IN (
                            SELECT DISTINCT conversation_id
                            FROM messages
                            WHERE sender_type = 'company' AND sender_id = %s
                        )
                        GROUP BY conversation_id
                    ) latest ON latest.conversation_id = m1.conversation_id AND latest.max_created = m1.created_at
                    ORDER BY m1.created_at DESC
                    """,
                    (company_id,)
                )
                summaries = cursor.fetchall()
            return jsonify({'conversations': summaries}), 200

        # POST: send message
        payload = request.get_json(silent=True) or {}
        conv_id = payload.get('conversation_id')
        msg_text = payload.get('message_text') or ''
        msg_type = payload.get('message_type') or 'text'
        file_url = payload.get('file_url')
        file_name = payload.get('file_name')
        file_size = payload.get('file_size')
        now = datetime.datetime.utcnow()

        if not conv_id:
            return jsonify({'error': 'conversation_id is required'}), 400
        if not msg_text and not file_url:
            return jsonify({'error': 'message_text or file_url required'}), 400

        cursor.execute(
            """
            INSERT INTO messages (conversation_id, sender_type, sender_id, message_text, message_type, file_url, file_name, file_size, is_read, created_at)
            VALUES (%s, 'company', %s, %s, %s, %s, %s, %s, 0, NOW())
            """,
            (conv_id, company_id, msg_text, msg_type, file_url, file_name, file_size)
        )

        # Mirror metadata into conversations for job seeker inbox visibility
        conv_cols = get_table_columns(conn, 'conversations') or set()
        if conv_cols and 'id' in conv_cols:
            set_parts = []
            vals = []
            if 'last_message_text' in conv_cols:
                set_parts.append("last_message_text = %s")
                vals.append(msg_text or file_name or '[file]')
            if 'last_message_at' in conv_cols:
                set_parts.append("last_message_at = %s")
                vals.append(now)
            if 'unread_count_seeker' in conv_cols:
                set_parts.append("unread_count_seeker = COALESCE(unread_count_seeker,0) + 1")
            if set_parts:
                vals.append(conv_id)
                cursor.execute(
                    f"UPDATE conversations SET {', '.join(set_parts)} WHERE id = %s",
                    tuple(vals)
                )
        conn.commit()
        return jsonify({'message': 'Message sent', 'conversation_id': conv_id}), 201
    except Exception as e:
        if conn:
            conn.rollback()
        app.logger.exception("Company messages error: %s", e)
        return jsonify({'error': 'Internal server error', 'detail': str(e)}), 500
    finally:
        try:
            cursor.close()
        except Exception:
            pass
        try:
            conn.close()
        except Exception:
            pass
@app.route('/api/job-seeker/profile', methods=['PUT'])
@token_required
def update_job_seeker_profile(current_user_id):
    conn = get_db_connection()
    if not conn:
        return jsonify({'error': 'Database connection failed'}), 500
    cursor = conn.cursor(dictionary=True)
    try:
        incoming = request.get_json(silent=True) or {}
        if not incoming and request.form:
            incoming = request.form.to_dict()

        cursor.execute("SELECT * FROM job_seekers WHERE user_id = %s", (current_user_id,))
        profile_row = cursor.fetchone()
        if not profile_row:
            return jsonify({'error': 'Job seeker profile not found'}), 404

        job_seeker_id = profile_row.get('id')
        js_columns = get_table_columns(conn, 'job_seekers') or set()
        update_map = {
            'full_name': incoming.get('full_name') or incoming.get('fullName'),
            'location': incoming.get('location'),
            'current_title': incoming.get('current_title') or incoming.get('currentTitle'),
            'experience_level': incoming.get('experience_level') or incoming.get('experienceLevel'),
            'manual_experience_years': incoming.get('manual_experience_years'),
            'phone': incoming.get('phone'),
            'bio': incoming.get('bio')
        }
        incoming_skills = incoming.get('skills')
        if isinstance(incoming_skills, str):
            incoming_skills = [s.strip() for s in incoming_skills.split(',') if s.strip()]
        if incoming_skills is None and 'skills' in incoming and not incoming['skills']:
            incoming_skills = []

        set_clauses = []
        values = []
        for col, val in update_map.items():
            if val is not None and col in js_columns:
                set_clauses.append(f"{col} = %s")
                values.append(val)

        if not set_clauses and incoming_skills is None:
            return jsonify({'error': 'No valid fields provided for update'}), 400

        if set_clauses and 'updated_at' in js_columns:
            set_clauses.append("updated_at = %s")
            values.append(datetime.datetime.utcnow())

        if set_clauses:
            values.append(current_user_id)
            sql = f"UPDATE job_seekers SET {', '.join(set_clauses)} WHERE user_id = %s"
            cursor.execute(sql, tuple(values))

        if incoming_skills is not None and job_seeker_id and table_exists(conn, 'job_seeker_skills'):
            skill_cols = get_table_columns(conn, 'job_seeker_skills')
            cursor.execute("DELETE FROM job_seeker_skills WHERE job_seeker_id = %s", (job_seeker_id,))
            if incoming_skills:
                name_col = 'skill_name' if 'skill_name' in skill_cols else ('name' if 'name' in skill_cols else None)
                if not name_col:
                    name_col = list(skill_cols - {'job_seeker_id'})[0] if len(skill_cols) > 1 else 'skill_name'
                insert_cols = ['job_seeker_id', name_col]
                placeholders = ', '.join(['%s'] * len(insert_cols))
                sql_ins = f"INSERT INTO job_seeker_skills ({', '.join(insert_cols)}) VALUES ({placeholders})"
                for skill in incoming_skills:
                    cursor.execute(sql_ins, (job_seeker_id, skill))

        conn.commit()

        updated = fetch_job_seeker_profile(conn, current_user_id)
        return jsonify({
            'message': 'Profile updated',
            'profile': updated
        }), 200
    except Exception as e:
        conn.rollback()
        app.logger.exception("Failed to update job seeker profile: %s", e)
        return jsonify({'error': 'Internal server error', 'detail': str(e)}), 500
    finally:
        try:
            cursor.close()
        except Exception:
            pass
        try:
            conn.close()
        except Exception:
            pass

@app.route('/api/job-seeker/upload-cv', methods=['POST'])
@token_required
def upload_job_seeker_cv(current_user_id):
    conn = get_db_connection()
    if not conn:
        return jsonify({'error': 'Database connection failed'}), 500
    cursor = None
    saved_file_path = None

    def cleanup_saved_cv():
        if saved_file_path and os.path.exists(saved_file_path):
            try:
                os.remove(saved_file_path)
            except Exception as cleanup_err:
                app.logger.warning("Failed to remove CV after skill detection check: %s", cleanup_err)
    try:
        file_obj = request.files.get('cvFile')
        if not file_obj or file_obj.filename == '':
            return jsonify({'error': 'No resume file uploaded'}), 400
        if not allowed_file(file_obj.filename):
            return jsonify({'error': 'Unsupported file type. Allowed: pdf, png'}), 400

        filename = secure_filename(file_obj.filename)
        timestamp = datetime.datetime.utcnow().strftime('%Y%m%d%H%M%S')
        disk_name = f"js_{current_user_id}_{timestamp}_{filename}"
        saved_file_path = os.path.join(UPLOAD_FOLDER, disk_name)
        file_obj.save(saved_file_path)

        profile_before = fetch_job_seeker_profile(conn, current_user_id)
        if not profile_before:
            return jsonify({'error': 'Job seeker profile not found'}), 404

        job_seeker_id = profile_before.get('id') or get_job_seeker_id(conn, current_user_id)
        job_seeker_columns = get_table_columns(conn, 'job_seekers') or set()

        extracted_text = ""
        try:
            extracted_text = extract_text_from_file(saved_file_path) if saved_file_path else ""
            if extracted_text:
                extracted_text = extracted_text[:64000]
        except Exception as ocr_err:
            app.logger.warning("OCR extraction failed during CV upload: %s", ocr_err)

        detected_skills = extract_skills_from_text(extracted_text) if extracted_text else []
        education_entries = extract_education_entries(extracted_text) if extracted_text else []

        if extracted_text and not detected_skills:
            cleanup_saved_cv()
            return jsonify({
                'error': "The OCR could not detect any skills on your resume. Please highlight your skills section or upload a clearer copy before we analyze it."
            }), 422

        education_level_inferred = infer_education_level_from_entries(education_entries)

        ai_prediction = None
        try:
            if extracted_text:
                ai_prediction = predict_job_and_salary(
                    extracted_text,
                    experience_level=profile_before.get('experience_level'),
                    detected_skills=detected_skills,
                    education_entries=education_entries
                )
        except Exception as ai_err:
            app.logger.exception("AI prediction failed during CV upload: %s", ai_err)


        fallback_exp = None
        if ai_prediction is not None:
            if education_entries:
                ai_prediction['education_detected'] = education_entries
            if education_level_inferred and not ai_prediction.get('education_level_predicted'):
                ai_prediction['education_level_predicted'] = education_level_inferred
            ai_skills = ai_prediction.get('skills_detected')
            if ai_skills:
                detected_skills = ai_skills
            ai_prediction['skills_detected'] = detected_skills if detected_skills else []
            ai_exp_years = ai_prediction.get('experience_years')
            if ai_exp_years is None and profile_before:
                fallback_exp = profile_before.get('manual_experience_years')
            if fallback_exp is not None:
                ai_prediction['experience_years'] = fallback_exp
            ai_level_pred = ai_prediction.get('experience_level_predicted') or ai_prediction.get('experience_level')
            if not ai_level_pred and profile_before:
                ai_level_pred = profile_before.get('experience_level')
            if ai_level_pred:
                ai_prediction['experience_level_predicted'] = ai_level_pred
        experience_input = ai_prediction.get('experience_years') if ai_prediction else None
        match_score = ai_prediction.get('match_score') if ai_prediction else None
        if match_score is None:
            match_score = compute_match_score(
                ai_prediction or {},
                detected_skills if detected_skills else None,
                education_level=education_level_inferred,
                candidate_experience=experience_input
            )
        predicted_role = ai_prediction.get('job_role') if ai_prediction else None
        predicted_salary = ai_prediction.get('salary') if ai_prediction else None
        predicted_exp_years = ai_prediction.get('experience_years') if ai_prediction else None
        education_summary = "; ".join(education_entries) if education_entries else None

        resume_text_col = None
        for candidate_col in ['resume_text', 'resume_raw', 'ocr_text', 'extracted_resume']:
            if candidate_col in job_seeker_columns:
                resume_text_col = candidate_col
                break

        update_cols = []
        values = []

        def add_update(col, val):
            if col in job_seeker_columns:
                update_cols.append(f"{col} = %s")
                values.append(val)

        add_update('resume_url', disk_name)
        if resume_text_col:
            add_update(resume_text_col, extracted_text)
        if predicted_role:
            for role_col in ['predicted_job_role', 'ai_job_role', 'target_role', 'target_title']:
                add_update(role_col, predicted_role)
        if predicted_salary is not None:
            for sal_col in ['predicted_salary', 'expected_salary', 'expected_salary_min']:
                add_update(sal_col, predicted_salary)
        if education_level_inferred:
            add_update('education_level', education_level_inferred)
        if education_summary:
            for summary_col in ['education_summary', 'education_details', 'education_information', 'education_background']:
                add_update(summary_col, education_summary)
        if education_entries:
            education_json = json.dumps(education_entries, ensure_ascii=False)
            for detected_col in ['education_detected', 'education_info', 'education_fields']:
                add_update(detected_col, education_json)
        add_update('match_score', match_score)
        if 'updated_at' in job_seeker_columns:
            add_update('updated_at', datetime.datetime.utcnow())

        if update_cols:
            values.append(current_user_id)
            sql = f"UPDATE job_seekers SET {', '.join(update_cols)} WHERE user_id = %s"
            cursor = conn.cursor(dictionary=True)
            cursor.execute(sql, tuple(values))

        cv_analysis_cols = get_table_columns(conn, 'cv_analysis')
        if cv_analysis_cols and job_seeker_id:
            cursor = cursor or conn.cursor(dictionary=True)
            existing_ca_id = None
            existing_cv_file = None
            try:
                cursor.execute(
                    """
                    SELECT id, cv_file_url
                    FROM cv_analysis
                    WHERE job_seeker_id = %s
                    ORDER BY analysis_date DESC, id DESC
                    LIMIT 1
                    """,
                    (job_seeker_id,)
                )
                row = cursor.fetchone()
                existing_ca_id = row.get('id') if row else None
                existing_cv_file = row.get('cv_file_url') if row else None
            except Exception:
                existing_ca_id = None
                existing_cv_file = None

            set_pairs = []
            ca_values = []

            def add_ca(col, val):
                if col in cv_analysis_cols:
                    set_pairs.append(f"{col} = %s")
                    ca_values.append(val)

            add_ca('job_seeker_id', job_seeker_id)
            add_ca('cv_file_url', disk_name)
            add_ca('analysis_data', extracted_text if extracted_text else None)
            add_ca('skills_detected', json.dumps(detected_skills) if detected_skills else None)
            if education_entries:
                add_ca('education_detected', json.dumps(education_entries, ensure_ascii=False))
            if education_level_inferred:
                add_ca('education_level_detected', education_level_inferred)
            experience_level_detected = None
            if ai_prediction:
                experience_level_detected = ai_prediction.get('experience_level_predicted')
            if not experience_level_detected and profile_before:
                experience_level_detected = profile_before.get('experience_level')
            if experience_level_detected:
                add_ca('experience_level_detected', experience_level_detected)
            if ai_prediction:
                add_ca('predicted_job_role', predicted_role)
                add_ca('predicted_salary', predicted_salary)
                add_ca('predicted_experience_years', predicted_exp_years)
                if ai_prediction.get('top_job_roles'):
                    add_ca('top_job_roles', json.dumps(ai_prediction.get('top_job_roles'), ensure_ascii=False))
                sanitized_prediction = _sanitize_for_json(ai_prediction)
                add_ca('ai_prediction', json.dumps(sanitized_prediction))
            add_ca('match_score', match_score)
            add_ca('analysis_date', datetime.datetime.utcnow())
            if not existing_ca_id:
                add_ca('created_at', datetime.datetime.utcnow())

            target_ca_id = existing_ca_id
            if set_pairs:
                if existing_ca_id:
                    ca_values.append(existing_ca_id)
                    cursor.execute(
                        f"UPDATE cv_analysis SET {', '.join(set_pairs)} WHERE id = %s",
                        tuple(ca_values)
                    )
                else:
                    placeholder = ', '.join(['%s'] * len(set_pairs))
                    cursor.execute(
                        f"INSERT INTO cv_analysis ({', '.join([p.split(' = ')[0] for p in set_pairs])}) VALUES ({placeholder})",
                        tuple(ca_values)
                    )
                    target_ca_id = cursor.lastrowid

            # Cleanup: keep only the latest row and delete older files
            try:
                if target_ca_id:
                    cursor.execute(
                        "DELETE FROM cv_analysis WHERE job_seeker_id = %s AND id <> %s",
                        (job_seeker_id, target_ca_id)
                    )
                old_names = set()
                if existing_cv_file and os.path.basename(existing_cv_file) != disk_name:
                    old_names.add(os.path.basename(existing_cv_file))
                if profile_before.get('resume_url'):
                    old_names.add(os.path.basename(profile_before.get('resume_url')))
                for name in old_names:
                    old_path = os.path.join(UPLOAD_FOLDER, name)
                    if os.path.isfile(old_path):
                        try:
                            os.remove(old_path)
                        except Exception as rm_err:
                            app.logger.warning("Could not remove old CV %s: %s", name, rm_err)
            except Exception as cleanup_err:
                app.logger.warning("CV cleanup failed: %s", cleanup_err)

        conn.commit()

        prev_resume = profile_before.get('resume_url')
        if prev_resume:
            prev_name = os.path.basename(prev_resume)
            if prev_name and prev_name != disk_name:
                old_path = os.path.join(UPLOAD_FOLDER, prev_name)
                if os.path.isfile(old_path):
                    try:
                        os.remove(old_path)
                    except Exception as rm_err:
                        app.logger.warning("Could not remove old CV %s: %s", prev_name, rm_err)

        refreshed = fetch_job_seeker_profile(conn, current_user_id)
        resume_url_full = build_cv_url(disk_name)
        analysis_payload = {
            'predicted_role': predicted_role,
            'predicted_salary': predicted_salary,
            'predicted_experience_years': predicted_exp_years,
            'detected_skills': detected_skills,
            'match_score': match_score
        }

        return jsonify({
            'message': 'Resume uploaded successfully',
            'resume_url': resume_url_full,
            'profile': refreshed,
            'analysis': analysis_payload
        }), 200

    except Exception as e:
        if conn:
            conn.rollback()
        if saved_file_path and os.path.exists(saved_file_path):
            try:
                os.remove(saved_file_path)
            except Exception as rm_err:
                app.logger.warning("Failed to clean saved CV after error: %s", rm_err)
        app.logger.exception("Failed to upload CV: %s", e)
        return jsonify({'error': 'Internal server error', 'detail': str(e)}), 500
    finally:
        try:
            if cursor:
                cursor.close()
        except Exception:
            pass
        try:
            conn.close()
        except Exception:
            pass

@app.route('/api/job-seeker/dashboard', methods=['GET'])
@token_required
def job_seeker_dashboard(current_user_id):
    conn = get_db_connection()
    if not conn:
        return jsonify({'error': 'Database connection failed'}), 500
    cursor = conn.cursor(dictionary=True)
    try:
        profile = fetch_job_seeker_profile(conn, current_user_id)
        if not profile:
            return jsonify({'error': 'Job seeker profile not found'}), 404

        metrics = {
            'total_applications': 0,
            'pending': 0,
            'interviews': 0,
            'hired': 0
        }
        recent_apps = []

        js_identifier = profile.get('id')
        app_cols = get_table_columns(conn, 'job_applications') or set()
        job_cols = get_table_columns(conn, 'jobs') or set()
        company_cols = get_table_columns(conn, 'companies') or set()

        js_fk_col = None
        if 'job_seeker_id' in app_cols:
            js_fk_col = 'job_seeker_id'
        elif 'user_id' in app_cols:
            js_fk_col = 'user_id'

        status_col = None
        for candidate in ['application_status', 'status']:
            if candidate in app_cols:
                status_col = candidate
                break
        applied_col = None
        for candidate in ['applied_at', 'created_at']:
            if candidate in app_cols:
                applied_col = candidate
                break

        identifier_value = js_identifier if js_fk_col == 'job_seeker_id' else current_user_id

        if js_fk_col and identifier_value is not None:
            if status_col:
                cursor.execute(
                    f"""
                    SELECT 
                        COUNT(*) as total_applications,
                        SUM(CASE WHEN {status_col} IN ('applied','pending','review','under_review') THEN 1 ELSE 0 END) as pending,
                        SUM(CASE WHEN {status_col} IN ('interview','interview_scheduled','interviewing') THEN 1 ELSE 0 END) as interviews,
                        SUM(CASE WHEN {status_col} IN ('hired','offer','accepted') THEN 1 ELSE 0 END) as hired
                    FROM job_applications
                    WHERE {js_fk_col} = %s
                    """,
                    (identifier_value,)
                )
                stat_row = cursor.fetchone() or {}
                metrics['total_applications'] = stat_row.get('total_applications', 0) or 0
                metrics['pending'] = stat_row.get('pending', 0) or 0
                metrics['interviews'] = stat_row.get('interviews', 0) or 0
                metrics['hired'] = stat_row.get('hired', 0) or 0
            else:
                cursor.execute(
                    f"SELECT COUNT(*) as total_applications FROM job_applications WHERE {js_fk_col} = %s",
                    (identifier_value,)
                )
                total_row = cursor.fetchone() or {}
                metrics['total_applications'] = total_row.get('total_applications', 0) or 0

            if 'job_id' in app_cols and 'id' in job_cols and 'title' in job_cols:
                company_name_col = None
                if 'company_id' in job_cols:
                    if 'company_name' in company_cols:
                        company_name_col = 'company_name'
                    elif 'name' in company_cols:
                        company_name_col = 'name'

                company_join = ""
                company_select = ""
                if company_name_col:
                    company_join = "LEFT JOIN companies c ON j.company_id = c.id"
                    company_select = f", c.{company_name_col} as company_name"

                status_select = f", ja.{status_col} as status" if status_col else ", NULL as status"
                applied_alias = applied_col if applied_col else 'id'
                applied_select = f", ja.{applied_col} as applied_at" if applied_col else ", ja.id as applied_at"

                recent_sql = f"""
                    SELECT ja.id as application_id{status_select},
                           j.title as job_title{company_select}
                           {applied_select}
                    FROM job_applications ja
                    JOIN jobs j ON ja.job_id = j.id
                    {company_join}
                    WHERE ja.{js_fk_col} = %s
                    ORDER BY ja.{applied_alias} DESC
                    LIMIT 5
                """
                cursor.execute(recent_sql, (identifier_value,))
                rows = cursor.fetchall()
                for r in rows:
                    recent_apps.append({
                        'id': r.get('application_id'),
                        'job_title': r.get('job_title') or '',
                        'company': r.get('company_name') or '',
                        'status': r.get('status') or '',
                        'applied_at': r.get('applied_at')
                    })

        return jsonify({
            'profile': profile,
            'metrics': metrics,
            'recent_applications': recent_apps
        }), 200
    except Exception as e:
        app.logger.exception("Failed to load job seeker dashboard: %s", e)
        return jsonify({'error': 'Internal server error', 'detail': str(e)}), 500
    finally:
        try:
            cursor.close()
        except Exception:
            pass
        try:
            conn.close()
        except Exception:
            pass

@app.route('/api/job-seeker/profile-picture', methods=['POST'])
@token_required
def upload_job_seeker_avatar(current_user_id):
    """Upload and save a profile picture for the current job seeker."""
    conn = get_db_connection()
    if not conn:
        return jsonify({'error': 'Database connection failed'}), 500
    cursor = None
    saved_path = None
    try:
        file_obj = request.files.get('avatar')
        if not file_obj or file_obj.filename == '':
            return jsonify({'error': 'No image uploaded'}), 400
        if not allowed_image_file(file_obj.filename):
            return jsonify({'error': 'Unsupported file type. Allowed: png, jpg, jpeg'}), 400

        filename = secure_filename(file_obj.filename)
        ext = filename.rsplit('.', 1)[1].lower()
        timestamp = datetime.datetime.utcnow().strftime('%Y%m%d%H%M%S')
        disk_name = f"avatar_{current_user_id}_{timestamp}.{ext}"
        saved_path = os.path.join(AVATAR_FOLDER, disk_name)
        file_obj.save(saved_path)

        # Update DB if column exists
        job_seeker_columns = get_table_columns(conn, 'job_seekers') or set()
        if 'profile_picture_url' in job_seeker_columns:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE job_seekers SET profile_picture_url=%s WHERE user_id=%s",
                (f"avatars/{disk_name}", current_user_id)
            )
            conn.commit()

        url = f"/uploads/avatars/{disk_name}"
        return jsonify({'message': 'Avatar uploaded', 'url': url}), 200
    except Exception as e:
        if conn:
            conn.rollback()
        app.logger.exception("Avatar upload failed: %s", e)
        return jsonify({'error': 'Internal server error', 'detail': str(e)}), 500
    finally:
        try:
            if cursor:
                cursor.close()
            if conn:
                conn.close()
        except Exception:
            pass

# ============ Messages ============
@app.route('/api/messages/conversations', methods=['GET'])
@token_required
def api_list_conversations(current_user_id):
    conn = get_db_connection()
    if not conn:
        return jsonify({'error': 'Database connection failed'}), 500
    try:
        js_id = get_job_seeker_id(conn, current_user_id)
        if not js_id:
            return jsonify({'error': 'Job seeker profile not found'}), 404
        conversations = list_conversations_for_seeker(conn, js_id, current_user_id)
        return jsonify({'conversations': conversations}), 200
    except Exception as e:
        if conn:
            conn.rollback()
        app.logger.exception("Failed to list conversations: %s", e)
        return jsonify({'error': 'Internal server error', 'detail': str(e)}), 500
    finally:
        try:
            conn.close()
        except Exception:
            pass

@app.route('/api/messages/conversations/<int:conv_id>/messages', methods=['GET'])
@token_required
def api_list_messages(current_user_id, conv_id):
    conn = get_db_connection()
    if not conn:
        return jsonify({'error': 'Database connection failed'}), 500
    cur = None
    try:
        js_id = get_job_seeker_id(conn, current_user_id)
        if not js_id:
            return jsonify({'error': 'Job seeker profile not found'}), 404
        conv = get_conversation_for_seeker(conn, conv_id, js_id, current_user_id)
        if not conv:
            return jsonify({'error': 'Conversation not found'}), 404

        cur = conn.cursor(dictionary=True)
        cur.execute(
            """
            SELECT id, sender_type, sender_id, message_text, message_type,
                   file_url, file_name, file_size, is_read, created_at
            FROM messages
            WHERE conversation_id = %s
            ORDER BY created_at ASC, id ASC
            """,
            (conv_id,)
        )
        msgs = cur.fetchall() or []

        # Mark as read for seeker side (company-sent messages)
        try:
            cur.execute(
                "UPDATE messages SET is_read=1 WHERE conversation_id=%s AND sender_type='company' AND is_read=0",
                (conv_id,)
            )
            cur.execute(
                "UPDATE conversations SET unread_count_seeker=0 WHERE id=%s",
                (conv_id,)
            )
            conn.commit()
        except Exception as e:
            conn.rollback()
            app.logger.warning("Failed to mark messages read for conv %s: %s", conv_id, e)

        return jsonify({'messages': msgs}), 200
    except Exception as e:
        if conn:
            conn.rollback()
        app.logger.exception("Failed to list messages: %s", e)
        return jsonify({'error': 'Internal server error', 'detail': str(e)}), 500
    finally:
        try:
            if cur:
                cur.close()
            conn.close()
        except Exception:
            pass

@app.route('/api/messages/conversations/<int:conv_id>/messages', methods=['POST'])
@token_required
def api_send_message(current_user_id, conv_id):
    conn = get_db_connection()
    if not conn:
        return jsonify({'error': 'Database connection failed'}), 500
    cur = None
    try:
        payload = request.get_json(silent=True) or {}
        text = (payload.get('text') or '').strip()
        if not text:
            return jsonify({'error': 'Message text is required'}), 400

        js_id = get_job_seeker_id(conn, current_user_id)
        if not js_id:
            return jsonify({'error': 'Job seeker profile not found'}), 404
        conv = get_conversation_for_seeker(conn, conv_id, js_id, current_user_id)
        if not conv:
            return jsonify({'error': 'Conversation not found'}), 404

        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO messages (conversation_id, sender_type, sender_id, message_text, message_type, is_read)
            VALUES (%s, 'job_seeker', %s, %s, 'text', 0)
            """,
            (conv_id, js_id, text)
        )
        # Update conversation last message + unread count for company
        cur.execute(
            """
            UPDATE conversations
            SET last_message_text=%s,
                last_message_at=%s,
                unread_count_company = COALESCE(unread_count_company,0) + 1
            WHERE id=%s
            """,
            (text, datetime.datetime.utcnow(), conv_id)
        )
        conn.commit()
        return jsonify({'message': 'Sent'}), 200
    except Exception as e:
        if conn:
            conn.rollback()
        app.logger.exception("Failed to send message: %s", e)
        return jsonify({'error': 'Internal server error', 'detail': str(e)}), 500
    finally:
        try:
            if cur:
                cur.close()
            conn.close()
        except Exception:
            pass

@app.route('/api/job-seeker/account', methods=['DELETE'])
@token_required
def delete_job_seeker_account(current_user_id):
    conn = get_db_connection()
    if not conn:
        return jsonify({'error': 'Database connection failed'}), 500
    cursor = conn.cursor(dictionary=True)
    try:
        job_seeker_id = get_job_seeker_id(conn, current_user_id)
        if not job_seeker_id:
            # Create a minimal job seeker profile if missing so we can store the CV
            js_cols = get_table_columns(conn, 'job_seekers') or set()
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT email, name FROM users WHERE id = %s", (current_user_id,))
            urow = cursor.fetchone() or {}
            full_name = urow.get('name') or urow.get('email') or "Job Seeker"
            insert_cols = []
            insert_vals = []
            for col, val in [
                ('user_id', current_user_id),
                ('full_name', full_name),
                ('experience_level', 'entry'),
                ('is_profile_complete', 0),
            ]:
                if col in js_cols:
                    insert_cols.append(col)
                    insert_vals.append(val)
            if insert_cols:
                placeholders = ', '.join(['%s'] * len(insert_cols))
                cursor.execute(
                    f"INSERT INTO job_seekers ({', '.join(insert_cols)}) VALUES ({placeholders})",
                    tuple(insert_vals)
                )
                conn.commit()
                job_seeker_id = cursor.lastrowid or get_job_seeker_id(conn, current_user_id)
            else:
                return jsonify({'error': 'Job seeker profile not found'}), 404
        js_pk_col = get_job_seeker_pk_column(conn)

        if table_exists(conn, 'job_applications'):
            app_fk = pick_first_column(get_table_columns(conn, 'job_applications') or set(), ['job_seeker_id', 'seeker_id', 'user_id'])
            if app_fk:
                cursor.execute(
                    f"DELETE FROM job_applications WHERE {app_fk} = %s",
                    (job_seeker_id if app_fk != 'user_id' else current_user_id,)
                )

        if table_exists(conn, 'job_seeker_skills'):
            skill_fk = pick_first_column(get_table_columns(conn, 'job_seeker_skills') or set(), ['job_seeker_id', 'seeker_id', 'user_id', 'candidate_id'])
            if skill_fk:
                cursor.execute(
                    f"DELETE FROM job_seeker_skills WHERE {skill_fk} = %s",
                    (job_seeker_id if skill_fk != 'user_id' else current_user_id,)
                )

        if js_pk_col:
            cursor.execute(
                f"DELETE FROM job_seekers WHERE {js_pk_col} = %s",
                (job_seeker_id if js_pk_col != 'user_id' else current_user_id,)
            )
        else:
            cursor.execute("DELETE FROM job_seekers WHERE user_id = %s", (current_user_id,))
        cursor.execute("DELETE FROM users WHERE id = %s", (current_user_id,))
        conn.commit()
        return jsonify({'message': 'Account deleted'}), 200
    except Exception as e:
        conn.rollback()
        app.logger.exception("Failed to delete account: %s", e)
        return jsonify({'error': 'Internal server error', 'detail': str(e)}), 500
    finally:
        try:
            cursor.close()
        except Exception:
            pass
        try:
            conn.close()
        except Exception:
            pass

@app.route('/api/company/dashboard', methods=['GET'])
@token_required
def company_dashboard(current_user_id):
    conn = get_db_connection()
    if not conn:
        return jsonify({'error': 'Database connection failed'}), 500
    mark_expired_jobs(conn)
    cursor = conn.cursor(dictionary=True)
    
    try:
        cursor.execute("SELECT id FROM companies WHERE user_id = %s", (current_user_id,))
        company = cursor.fetchone()
        
        if not company:
            return jsonify({'error': 'Company profile not found'}), 404
        
        company_id = company['id']

        cursor.execute("SELECT COUNT(*) as count FROM jobs WHERE company_id = %s AND status='active'", (company_id,))
        active_jobs = cursor.fetchone()['count']

        cursor.execute("""
            SELECT COUNT(*) as count 
            FROM job_applications ja 
            JOIN jobs j ON ja.job_id = j.id 
            WHERE j.company_id = %s
        """, (company_id,))
        total_applications = cursor.fetchone()['count']

        return jsonify({
            'metrics': {
                'total_jobs': active_jobs,
                'total_applications': total_applications,
                'active_interviews': 0,
                'recent_hires': 0
            }
            })
    finally:
        cursor.close()
        conn.close()

@app.route('/api/company/candidates', methods=['GET'])
@token_required
def company_candidates(current_user_id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT id FROM companies WHERE user_id = %s", (current_user_id,))
        company = cursor.fetchone()
        if not company:
            company_columns = get_table_columns(conn, 'companies') or set()
            cols = []
            vals = []
            if 'user_id' in company_columns:
                cols.append('user_id'); vals.append(current_user_id)
            if 'created_at' in company_columns:
                cols.append('created_at'); vals.append(datetime.datetime.utcnow())
            if 'updated_at' in company_columns:
                cols.append('updated_at'); vals.append(datetime.datetime.utcnow())
            if cols:
                placeholders = ', '.join(['%s'] * len(cols))
                cursor.execute(f"INSERT INTO companies ({', '.join(cols)}) VALUES ({placeholders})", tuple(vals))
                conn.commit()
                company = {'id': cursor.lastrowid}
            else:
                return jsonify({'error': 'Company profile not found'}), 403

        js_columns = get_table_columns(conn, 'job_seekers') or []
        js_pk_col = get_job_seeker_pk_column(conn) or 'id'
        select_cols = [c for c in ['id', 'job_seeker_id', 'user_id', 'full_name', 'current_title', 'location', 'experience_level',
                    'match_score', 'profile_picture_url', 'resume_url', 'created_at'] if c in js_columns]
        if js_pk_col not in select_cols and js_pk_col in js_columns:
            select_cols.append(js_pk_col)
        if not select_cols:
            select_cols = list(js_columns) if js_columns else ['id']
        col_list = ', '.join([f"js.{c}" for c in select_cols])
        order_col = f"js.{select_cols[-1]}"
        cursor.execute(
            f"""
            SELECT {col_list}
            FROM job_seekers js
            JOIN users u ON u.id = js.user_id
            WHERE u.user_type = 'job_seeker'
            ORDER BY {order_col} DESC
            """
        )
        rows = cursor.fetchall() if select_cols else []

        def safe_val(row, key, default=None):
            return row[key] if key in row else default

        candidates = []
        for r in rows:
            js_pk_val = safe_val(r, js_pk_col) or safe_val(r, 'id') or safe_val(r, 'job_seeker_id')
            candidates.append({
                'id': js_pk_val,
                'job_seeker_id': js_pk_val,
                'user_id': safe_val(r, 'user_id'),
                'full_name': safe_val(r, 'full_name') or '',
                'current_title': safe_val(r, 'current_title') or '',
                'location': safe_val(r, 'location') or '',
                'experience_level': safe_val(r, 'experience_level') or '',
                'match_score': safe_val(r, 'match_score', 0) or 0,
                'avatar_url': safe_val(r, 'profile_picture_url'),
                'resume_url': safe_val(r, 'resume_url'),
                'created_at': safe_val(r, 'created_at')
            })

        return jsonify({'candidates': candidates})
    except Error as e:
        app.logger.exception("Failed to load candidates: %s", e)
        return jsonify({'error': 'Internal server error', 'detail': str(e)}), 500
    finally:
        try:
            cursor.close()
        except Exception:
            pass
        try:
            conn.close()
        except Exception:
            pass

@app.route('/api/company/recent-candidates', methods=['GET'])
@token_required
def recent_candidates(current_user_id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT id FROM companies WHERE user_id = %s", (current_user_id,))
        company = cursor.fetchone()
        if not company:
            company_columns = get_table_columns(conn, 'companies') or set()
            cols = []
            vals = []
            if 'user_id' in company_columns:
                cols.append('user_id'); vals.append(current_user_id)
            if 'created_at' in company_columns:
                cols.append('created_at'); vals.append(datetime.datetime.utcnow())
            if 'updated_at' in company_columns:
                cols.append('updated_at'); vals.append(datetime.datetime.utcnow())
            if cols:
                placeholders = ', '.join(['%s'] * len(cols))
                cursor.execute(f"INSERT INTO companies ({', '.join(cols)}) VALUES ({placeholders})", tuple(vals))
                conn.commit()
                company = {'id': cursor.lastrowid}
            else:
                return jsonify({'error': 'Company profile not found'}), 403

        js_columns = get_table_columns(conn, 'job_seekers') or []
        base_cols = [c for c in ['id', 'user_id', 'full_name', 'current_title', 'location', 'experience_level',
                    'match_score', 'profile_picture_url', 'resume_url', 'created_at'] if c in js_columns]
        if not base_cols:
            base_cols = list(js_columns) if js_columns else ['id']
        order_col = 'created_at' if 'created_at' in base_cols else base_cols[0]
        col_list = ', '.join([f"js.{c}" for c in base_cols])
        cursor.execute(
            f"""
            SELECT {col_list}
            FROM job_seekers js
            JOIN users u ON u.id = js.user_id
            WHERE u.user_type = 'job_seeker'
            ORDER BY js.{order_col} DESC
            LIMIT 6
            """
        )
        rows = cursor.fetchall() if base_cols else []

        def safe_val(row, key, default=None):
            return row[key] if key in row else default

        candidates = []
        for r in rows:
            candidates.append({
                'id': safe_val(r, 'user_id') or safe_val(r, 'id'),
                'user_id': safe_val(r, 'user_id'),
                'full_name': safe_val(r, 'full_name') or '',
                'title': safe_val(r, 'current_title') or '',
                'location': safe_val(r, 'location') or '',
                'experience_level': safe_val(r, 'experience_level') or '',
                'match_score': safe_val(r, 'match_score', 0) or 0,
                'avatar_url': safe_val(r, 'profile_picture_url'),
                'resume_url': safe_val(r, 'resume_url'),
                'created_at': safe_val(r, 'created_at')
            })

        return jsonify({'candidates': candidates})
    except Error as e:
        app.logger.exception("Failed to load recent candidates: %s", e)
        return jsonify({'error': 'Internal server error', 'detail': str(e)}), 500
    finally:
        try:
            cursor.close()
        except Exception:
            pass
        try:
            conn.close()
        except Exception:
            pass

@app.route('/api/company/candidates/<int:candidate_id>', methods=['GET'])
@token_required
def company_candidate_profile(current_user_id, candidate_id):
    """Return a safe profile view for a given job seeker (by job_seekers.id or user_id)."""
    conn = get_db_connection()
    if not conn:
        return jsonify({'error': 'Database connection failed'}), 500
    cur = conn.cursor(dictionary=True)
    try:
        # Ensure requester is a company
        cur.execute("SELECT id FROM companies WHERE user_id=%s", (current_user_id,))
        company = cur.fetchone()
        if not company:
            return jsonify({'error': 'Company profile not found'}), 403

        # Load job seeker by id or user_id (no strict user_type filter to avoid mismatch)
        js_cols = get_table_columns(conn, 'job_seekers') or set()
        js_pk = 'id' if 'id' in js_cols else ('job_seeker_id' if 'job_seeker_id' in js_cols else 'user_id')
        pk_expr = f"js.{js_pk}=%s"
        try:
            cur.execute(
                f"""
                SELECT js.*, u.email
                FROM job_seekers js
                LEFT JOIN users u ON u.id = js.user_id
                WHERE ({pk_expr} OR js.user_id=%s)
                LIMIT 1
                """,
                (candidate_id, candidate_id)
            )
            row = cur.fetchone()
        except Exception as e:
            app.logger.exception("Candidate lookup failed primary query: %s", e)
            # Fallback: try only user_id match
            try:
                cur.execute(
                    """
                    SELECT js.*, u.email
                    FROM job_seekers js
                    LEFT JOIN users u ON u.id = js.user_id
                    WHERE js.user_id=%s
                    LIMIT 1
                    """,
                    (candidate_id,)
                )
                row = cur.fetchone()
            except Exception as e2:
                app.logger.exception("Candidate lookup fallback failed: %s", e2)
                row = None

        if not row:
            return jsonify({'error': 'Candidate not found'}), 404

        profile = serialize_job_seeker_profile(row)
        profile['email'] = profile.get('email') or row.get('email')
        if not profile.get('email') and profile.get('user_id'):
            try:
                cur.execute("SELECT email FROM users WHERE id=%s LIMIT 1", (profile.get('user_id'),))
                urow = cur.fetchone()
                if urow and isinstance(urow, dict):
                    profile['email'] = urow.get('email')
            except Exception:
                pass

        js_pk_val = profile.get('id')
        cv_row = None
        cv_skills = []
        if js_pk_val and table_exists(conn, 'cv_analysis'):
            try:
                cur.execute(
                    """
                    SELECT skills_detected, match_score, predicted_job_role,
                           predicted_salary, predicted_experience_years, ai_prediction, cv_file_url
                    FROM cv_analysis
                    WHERE job_seeker_id = %s
                    ORDER BY analysis_date DESC, id DESC
                    LIMIT 1
                    """,
                    (js_pk_val,)
                )
                cv_row = cur.fetchone()
                if cv_row:
                    skills_raw = cv_row.get('skills_detected')
                    if isinstance(skills_raw, str):
                        try:
                            cv_skills = json.loads(skills_raw)
                        except Exception:
                            cv_skills = []
                    elif isinstance(skills_raw, (list, tuple)):
                        cv_skills = list(skills_raw)
                    if not profile.get('match_score') and cv_row.get('match_score') is not None:
                        profile['match_score'] = cv_row.get('match_score')
                    if not profile.get('predicted_job_role'):
                        profile['predicted_job_role'] = cv_row.get('predicted_job_role')
                    if profile.get('predicted_salary') is None:
                        profile['predicted_salary'] = cv_row.get('predicted_salary')
                    if profile.get('predicted_experience_years') is None:
                        profile['predicted_experience_years'] = cv_row.get('predicted_experience_years')
                    if cv_row.get('cv_file_url') and not profile.get('resume_url'):
                        profile['resume_url'] = build_cv_url(cv_row.get('cv_file_url'))
            except Exception as e:
                app.logger.exception("Failed to load CV analysis for candidate %s: %s", js_pk_val, e)

        skills = []
        if js_pk_val or profile.get('user_id'):
            skills = get_job_seeker_skills(conn, js_pk_val, profile.get('user_id'))
        if not skills:
            skills = cv_skills
        profile['skills'] = skills
        return jsonify({'profile': profile}), 200
    except Exception as e:
        app.logger.exception("Failed to load candidate profile: %s", e)
        return jsonify({'error': 'Internal server error', 'detail': str(e)}), 500
    finally:
        try:
            cur.close()
            conn.close()
        except Exception:
            pass

@app.route('/api/company/jobs', methods=['POST'])
@token_required
def create_job(current_user_id):
    conn = get_db_connection()
    if not conn:
        return jsonify({'error': 'Database connection failed'}), 500

    cursor = None
    try:
        data = request.get_json(silent=True)
        if not data:
            return jsonify({'error': 'Invalid JSON payload'}), 400

        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT id FROM companies WHERE user_id = %s", (current_user_id,))
        company = cursor.fetchone()
        if not company:
            return jsonify({'error': 'Company profile not found for this user'}, 403)

        company_id = company['id']

        ensure_jobs_skill_columns(conn)
        job_payload, payload_error = _prepare_job_payload(data, company_id, default_status='active')
        job_columns = get_table_columns(conn, 'jobs') or []
        if payload_error:
            return jsonify({'error': payload_error}), 400
        if not job_payload:
            return jsonify({'error': 'Invalid job payload'}), 400

        now_str = datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
        if 'created_at' in job_columns and 'created_at' not in job_payload:
            job_payload['created_at'] = now_str
        if 'updated_at' in job_columns:
            job_payload['updated_at'] = now_str

        insert_cols = []
        insert_vals = []
        for col, val in job_payload.items():
            if col in job_columns:
                insert_cols.append(col)
                insert_vals.append(val)

        if not insert_cols:
            return jsonify({'error': 'Database schema mismatch on jobs table', 'detail': 'No matching columns found for insert'}), 500

        placeholders = ', '.join(['%s'] * len(insert_cols))
        columns_joined = ', '.join(insert_cols)
        insert_sql = f"INSERT INTO jobs ({columns_joined}) VALUES ({placeholders})"
        cursor.execute(insert_sql, tuple(insert_vals))

        conn.commit()
        job_id = cursor.lastrowid

        return jsonify({'message': 'Job created', 'job_id': job_id}), 201

    except Error as e:
        if conn:
            conn.rollback()
        app.logger.exception("Failed to create job: %s", e)
        return jsonify({'error': 'Internal server error', 'detail': str(e)}), 500
    finally:
        try:
            if cursor is not None:
                cursor.close()
        except Exception:
            app.logger.exception("Failed to close cursor in create_job")
        try:
            if conn is not None:
                conn.close()
        except Exception:
            app.logger.exception("Failed to close DB connection in create_job")

@app.route('/api/company/jobs', methods=['GET'])
@token_required
def get_company_jobs(current_user_id):
    conn = get_db_connection()
    if not conn:
        return jsonify({'error': 'Database connection failed'}), 500

    mark_expired_jobs(conn)

    cursor = None
    try:
        cursor = conn.cursor(dictionary=True)

        cursor.execute("SELECT id FROM companies WHERE user_id = %s", (current_user_id,))
        company_row = cursor.fetchone()
        if not company_row:
            return jsonify({'error': 'Company profile not found for this user'}), 403

        # Always scope jobs to the authenticated company
        company_id = company_row['id']

        ensure_jobs_skill_columns(conn)
        job_cols = get_table_columns(conn, 'jobs') or set()
        desired_cols = [
            'id', 'company_id', 'title', 'description', 'requirements', 'benefits',
            'required_skills', 'bonus_skills',
            'job_type', 'location', 'department', 'experience_level', 'education_level',
            'salary_min', 'salary_max', 'salary_type', 'positions_available',
            'application_deadline', 'is_featured', 'is_urgent', 'status',
            'view_count', 'applications_count', 'created_at', 'updated_at'
        ]
        select_cols = [c for c in desired_cols if c in job_cols]
        if not select_cols:
            select_cols = ['id', 'company_id', 'title']

        # Optional filters
        status_filter = None
        if 'status' in job_cols:
            requested_status = request.args.get('status')
            if requested_status:
                status_filter = requested_status.strip().lower()

        limit = request.args.get('limit', 50, type=int)
        if not limit or limit < 1:
            limit = 50
        limit = min(limit, 200)

        where_clauses = ["company_id = %s"]
        params = [company_id]
        if status_filter:
            where_clauses.append("status = %s")
            params.append(status_filter)

        sql = f"""
            SELECT {', '.join(select_cols)}
            FROM jobs
            WHERE {' AND '.join(where_clauses)}
            ORDER BY created_at DESC
            LIMIT %s
        """
        params.append(limit)
        cursor.execute(sql, tuple(params))
        rows = cursor.fetchall()

        jobs = []
        for r in rows:
            job_obj = {}
            for c in select_cols:
                job_obj[c] = r.get(c)
            jobs.append(job_obj)

        return jsonify({'jobs': jobs}), 200

    except Error as e:
        app.logger.exception("Failed to load company jobs: %s", e)
        return jsonify({'error': 'Internal server error', 'detail': str(e)}), 500

    finally:
        try:
            if cursor is not None:
                cursor.close()
        except Exception:
            app.logger.exception("Failed to close cursor in get_company_jobs")
        try:
            if conn is not None:
                conn.close()
        except Exception:
            app.logger.exception("Failed to close DB connection in get_company_jobs")


@app.route('/api/company/jobs/<int:job_id>', methods=['PUT'])
@token_required
def update_company_job(current_user_id, job_id):
    conn = get_db_connection()
    if not conn:
        return jsonify({'error': 'Database connection failed'}), 500

    mark_expired_jobs(conn)

    cursor = None
    try:
        data = request.get_json(silent=True)
        if not data:
            return jsonify({'error': 'Invalid JSON payload'}), 400

        ensure_jobs_skill_columns(conn)
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT id FROM companies WHERE user_id = %s", (current_user_id,))
        company = cursor.fetchone()
        if not company:
            return jsonify({'error': 'Company profile not found for this user'}, 403)
        company_id = company['id']

        cursor.execute("SELECT company_id FROM jobs WHERE id = %s", (job_id,))
        job_row = cursor.fetchone()
        if not job_row or job_row.get('company_id') != company_id:
            return jsonify({'error': 'Job not found or access denied'}), 404

        job_payload, payload_error = _prepare_job_payload(data, company_id, default_status=None)
        if payload_error:
            return jsonify({'error': payload_error}), 400
        if not job_payload:
            return jsonify({'error': 'Invalid job payload'}), 400

        job_columns = get_table_columns(conn, 'jobs') or []
        now_str = datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
        updatable = []
        for col, val in job_payload.items():
            if col in job_columns and col != 'company_id':
                updatable.append((col, val))

        if 'updated_at' in job_columns:
            updatable.append(('updated_at', now_str))

        if not updatable:
            return jsonify({'error': 'No valid fields to update'}), 400

        set_parts = []
        vals = []
        for col, val in updatable:
            set_parts.append(f"{col} = %s")
            vals.append(val)
        vals.append(job_id)

        cursor.execute(
            f"UPDATE jobs SET {', '.join(set_parts)} WHERE id = %s",
            tuple(vals)
        )
        conn.commit()
        return jsonify({'message': 'Job updated'}), 200
    except Error as e:
        if conn:
            conn.rollback()
        app.logger.exception("Failed to update job %s: %s", job_id, e)
        return jsonify({'error': 'Internal server error', 'detail': str(e)}), 500
    finally:
        try:
            if cursor is not None:
                cursor.close()
        except Exception:
            app.logger.exception("Failed to close cursor in update_company_job")
        try:
            if conn is not None:
                conn.close()
        except Exception:
            app.logger.exception("Failed to close DB connection in update_company_job")


@app.route('/api/company/jobs/<int:job_id>', methods=['DELETE'])
@token_required
def delete_company_job(current_user_id, job_id):
    conn = get_db_connection()
    if not conn:
        return jsonify({'error': 'Database connection failed'}), 500

    mark_expired_jobs(conn)

    cursor = None
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT id FROM companies WHERE user_id = %s", (current_user_id,))
        company = cursor.fetchone()
        if not company:
            return jsonify({'error': 'Company profile not found for this user'}, 403)
        company_id = company['id']

        cursor.execute("SELECT company_id FROM jobs WHERE id = %s", (job_id,))
        job_row = cursor.fetchone()
        if not job_row or job_row.get('company_id') != company_id:
            return jsonify({'error': 'Job not found or access denied'}), 404

        cursor.execute("DELETE FROM jobs WHERE id = %s", (job_id,))
        conn.commit()
        return jsonify({'message': 'Job deleted'}), 200
    except Error as e:
        if conn:
            conn.rollback()
        app.logger.exception("Failed to delete job %s: %s", job_id, e)
        return jsonify({'error': 'Internal server error', 'detail': str(e)}), 500
    finally:
        try:
            if cursor is not None:
                cursor.close()
        except Exception:
            app.logger.exception("Failed to close cursor in delete_company_job")
        try:
            if conn is not None:
                conn.close()
        except Exception:
            app.logger.exception("Failed to close DB connection in delete_company_job")

@app.route('/api/jobs/search', methods=['GET'])
def search_jobs():
    """Public job search endpoint."""
    conn = get_db_connection()
    if not conn:
        return jsonify({'error': 'Database connection failed'}), 500
    mark_expired_jobs(conn)
    cursor = conn.cursor(dictionary=True)
    try:
        job_cols = get_table_columns(conn, 'jobs') or set()
        selectable = [c for c in [
            'id', 'title', 'description', 'location', 'job_type', 'experience_level',
            'company_id', 'salary_min', 'salary_max', 'salary_type', 'status',
            'created_at', 'updated_at', 'positions_available'
        ] if c in job_cols]
        if not selectable:
            selectable = ['id'] if 'id' in job_cols else []
        select_sql = ', '.join([f"j.{c} as {c}" for c in selectable]) if selectable else 'j.*'

        q = request.args.get('q') or request.args.get('keyword')
        location = request.args.get('location')
        job_type = request.args.get('type') or request.args.get('job_type')
        experience = request.args.get('experience') or request.args.get('experience_level')
        limit = request.args.get('limit', 500, type=int)
        if not limit or limit < 1 or limit > 2000:
            limit = 500

        conditions = []
        params = []
        if q and 'title' in job_cols:
            if 'description' in job_cols:
                conditions.append("(title LIKE %s OR description LIKE %s)")
                params.extend([f"%{q}%", f"%{q}%"])
            else:
                conditions.append("title LIKE %s")
                params.append(f"%{q}%")
        if location and 'location' in job_cols:
            conditions.append("location LIKE %s")
            params.append(f"%{location}%")
        if job_type and 'job_type' in job_cols:
            conditions.append("job_type = %s")
            params.append(job_type)
        if experience and 'experience_level' in job_cols:
            conditions.append("experience_level = %s")
            params.append(experience)

        # Enforce active status by default
        status_filter = None
        if 'status' in job_cols:
            requested_status = request.args.get('status')
            if requested_status:
                status_filter = requested_status.strip().lower()
            else:
                status_filter = 'active'
        if status_filter:
            conditions.append("COALESCE(LOWER(TRIM(j.status)), 'active') = %s")
            params.append(status_filter)

        app_cols = get_table_columns(conn, 'job_applications') or set()
        status_col = None
        for candidate in ['application_status', 'status']:
            if candidate in app_cols:
                status_col = candidate
                break

        join_clause = ""
        hide_filled = False
        if app_cols and status_col and 'positions_available' in job_cols:
            join_clause = f"""
                LEFT JOIN (
                    SELECT job_id,
                           SUM(CASE WHEN {status_col} IN ('accepted','accept','hired','hire','offer','approved') THEN 1 ELSE 0 END) as accepted_count
                    FROM job_applications
                    GROUP BY job_id
                ) ja ON ja.job_id = j.id
            """
            select_sql += ", COALESCE(ja.accepted_count,0) as accepted_count"
            conditions.append("(j.positions_available IS NULL OR COALESCE(ja.accepted_count,0) < j.positions_available)")
            hide_filled = True

        sql = f"SELECT {select_sql} FROM jobs j"
        if join_clause:
            sql += " " + join_clause
        if conditions:
            sql += " WHERE " + " AND ".join(conditions)
        order_col = 'created_at' if 'created_at' in job_cols else ('id' if 'id' in job_cols else None)
        if order_col:
            sql += f" ORDER BY j.{order_col} DESC"
        sql += " LIMIT %s"
        params.append(limit)

        cursor.execute(sql, tuple(params))
        rows = cursor.fetchall()
        if hide_filled:
            rows = [r for r in rows if (r.get('positions_available') is None or (r.get('accepted_count') or 0) < r.get('positions_available'))]
        return jsonify({'jobs': rows}), 200
    except Exception as e:
        app.logger.exception("Failed to search jobs: %s", e)
        return jsonify({'error': 'Internal server error', 'detail': str(e)}), 500
    finally:
        try:
            cursor.close()
        except Exception:
            pass
        try:
            conn.close()
        except Exception:
            pass

@app.route('/api/admin/overview', methods=['GET'])
@token_required
def admin_overview(current_user_id):
    conn = get_db_connection()
    if not conn:
        return jsonify({'error': 'Database connection failed'}), 500

    cursor = None
    try:
        assert_admin(current_user_id, conn)
        cursor = conn.cursor(dictionary=True)

        def scalar_count(query, params=()):
            cursor.execute(query, params)
            row = cursor.fetchone()
            if not row:
                return 0
            return row.get('value') or row.get('count') or row.get('total') or 0

        total_users = scalar_count("SELECT COUNT(*) AS value FROM users")
        job_seekers = scalar_count("SELECT COUNT(*) AS value FROM job_seekers") if table_exists(conn, 'job_seekers') else 0
        companies = scalar_count("SELECT COUNT(*) AS value FROM companies") if table_exists(conn, 'companies') else 0
        total_jobs = scalar_count("SELECT COUNT(*) AS value FROM jobs") if table_exists(conn, 'jobs') else 0
        total_applications = scalar_count("SELECT COUNT(*) AS value FROM job_applications") if table_exists(conn, 'job_applications') else 0

        job_cols = get_table_columns(conn, 'jobs') or set()
        app_cols = get_table_columns(conn, 'job_applications') or set()

        job_status_col = pick_first_column(job_cols, ['status', 'job_status'])
        active_keywords = {'active', 'open', 'published', 'live'}
        pending_keywords = {'pending', 'draft', 'under_review', 'review'}
        active_jobs = 0
        pending_jobs = 0
        if job_status_col:
            cursor.execute(
                f"""
                SELECT COALESCE(LOWER(TRIM({job_status_col})), '') AS status_term,
                       COUNT(*) AS cnt
                FROM jobs
                GROUP BY status_term
                """
            )
            for row in cursor.fetchall() or []:
                status_term = (row.get('status_term') or '').strip()
                cnt = row.get('cnt') or 0
                if status_term in active_keywords:
                    active_jobs += cnt
                if status_term in pending_keywords:
                    pending_jobs += cnt

        app_status_col = pick_first_column(app_cols, ['application_status', 'status'])
        hired_keywords = {'hired', 'hire', 'offer', 'accepted', 'final_round', 'selected'}
        interview_keywords = {'interview', 'technical_test', 'shortlisted', 'offer', 'final_round'}
        hired_count = 0
        interviews_count = 0
        if app_status_col:
            cursor.execute(
                f"""
                SELECT COALESCE(LOWER(TRIM({app_status_col})), '') AS status_term,
                       COUNT(*) AS cnt
                FROM job_applications
                GROUP BY status_term
                """
            )
            for row in cursor.fetchall() or []:
                status_term = (row.get('status_term') or '').strip()
                cnt = row.get('cnt') or 0
                if any(keyword in status_term for keyword in hired_keywords):
                    hired_count += cnt
                if any(keyword in status_term for keyword in interview_keywords):
                    interviews_count += cnt

        match_col = pick_first_column(app_cols, ['match_score'])
        match_rate_value = 0
        ai_matches = 0
        if match_col:
            cursor.execute(
                f"""
                SELECT AVG({match_col}) AS avg_match,
                       SUM(CASE WHEN {match_col} >= 70 THEN 1 ELSE 0 END) AS ai_matches
                FROM job_applications
                WHERE {match_col} IS NOT NULL
                """
            )
            row = cursor.fetchone() or {}
            match_rate_value = float(row.get('avg_match') or 0) if row.get('avg_match') is not None else 0
            ai_matches = int(row.get('ai_matches') or 0)

        success_rate = round((hired_count / total_applications) * 100, 1) if total_applications else 0

        recent_activity = []
        if table_exists(conn, 'job_applications') and table_exists(conn, 'jobs'):
            job_title_col = pick_first_column(job_cols, ['title', 'job_title', 'position', 'name'])
            activity_col = pick_first_column(app_cols, ['applied_at', 'created_at', 'updated_at', 'id']) or 'id'
            if job_title_col and job_title_col in job_cols:
                job_title_select = f"COALESCE(j.{job_title_col}, CONCAT('Job #', ja.job_id)) AS job_title"
            else:
                job_title_select = "CONCAT('Job #', ja.job_id) AS job_title"
            selects = [
                "ja.id AS app_id",
                "ja.job_id",
                job_title_select
            ]
            if app_status_col:
                selects.append(f"ja.{app_status_col} AS status")
            else:
                selects.append("NULL AS status")
            selects.append(f"ja.{activity_col} AS activity_time")
            select_clause = ", ".join(selects)
            cursor.execute(
                f"""
                SELECT {select_clause}
                FROM job_applications ja
                LEFT JOIN jobs j ON ja.job_id = j.id
                ORDER BY ja.{activity_col} DESC
                LIMIT 5
                """
            )
            for row in cursor.fetchall() or []:
                activity_time = row.get('activity_time')
                if isinstance(activity_time, datetime.datetime):
                    activity_time = activity_time.isoformat()
                recent_activity.append({
                    'id': row.get('app_id'),
                    'job_title': row.get('job_title') or f"Job #{row.get('job_id')}",
                    'status': row.get('status') or 'Updated',
                    'time': activity_time or ''
                })

        stats = {
            'totalUsers': int(total_users),
            'jobSeekers': int(job_seekers),
            'companies': int(companies),
            'totalJobs': int(total_jobs),
            'activeJobs': int(active_jobs),
            'pendingJobs': int(pending_jobs),
            'totalApplications': int(total_applications),
            'hired': int(hired_count),
            'interviews': int(interviews_count),
            'aiMatches': int(ai_matches),
            'matchRate': round(match_rate_value, 1),
            'successRate': success_rate
        }

        pending_approvals = []
        pending_statuses = ['pending', 'draft', 'under_review', 'review', 'pending_approval']
        company_cols = get_table_columns(conn, 'companies') or set()
        company_name_candidates = [col for col in ['company_name', 'name'] if col in company_cols]
        if company_name_candidates:
            expressions = ", ".join(f"c.{col}" for col in company_name_candidates)
            company_select = f"COALESCE({expressions}, 'Company') AS company_name"
        else:
            company_select = "'Company' AS company_name"
        if job_status_col and table_exists(conn, 'jobs'):
            status_placeholders = ','.join(['%s'] * len(pending_statuses))
            cursor.execute(
                f"""
                SELECT j.id, j.title,
                       {company_select},
                       j.company_id, j.created_at, j.updated_at
                FROM jobs j
                LEFT JOIN companies c ON c.id = j.company_id
                WHERE LOWER(TRIM(j.{job_status_col})) IN ({status_placeholders})
                ORDER BY j.created_at DESC
                LIMIT 5
                """,
                tuple(pending_statuses)
            )
            for row in cursor.fetchall() or []:
                pending_approvals.append({
                    'jobId': row.get('id'),
                    'title': row.get('title'),
                    'company': row.get('company_name'),
                    'companyId': row.get('company_id'),
                    'createdAt': row.get('created_at'),
                    'updatedAt': row.get('updated_at')
                })

        user_audits = []
        if table_exists(conn, 'notifications'):
            cursor.execute(
                """
                SELECT n.id, n.title, n.message, n.type, n.related_entity_type, n.related_entity_id,
                       n.created_at, u.email AS user_email, u.user_type
                FROM notifications n
                LEFT JOIN users u ON u.id = n.user_id
                ORDER BY n.created_at DESC
                LIMIT 5
                """
            )
            for row in cursor.fetchall() or []:
                user_audits.append({
                    'id': row.get('id'),
                    'title': row.get('title'),
                    'message': row.get('message'),
                    'type': row.get('type'),
                    'relatedEntityType': row.get('related_entity_type'),
                    'relatedEntityId': row.get('related_entity_id'),
                    'createdAt': row.get('created_at'),
                    'userEmail': row.get('user_email'),
                    'userType': row.get('user_type')
                })

        return jsonify({
            'stats': stats,
            'recentActivity': recent_activity,
            'pendingApprovals': pending_approvals,
            'userAudits': user_audits
        }), 200
    except Exception as e:
        if conn:
            conn.rollback()
        app.logger.exception("Failed to load admin overview: %s", e)
        return jsonify({'error': 'Internal server error', 'detail': str(e)}), 500
    finally:
        try:
            if cursor is not None:
                cursor.close()
        except Exception:
            pass
        try:
            conn.close()
        except Exception:
            pass


def _delete_job_applications_for_job_ids(cursor, job_ids):
    if not job_ids:
        return
    placeholders = ", ".join(["%s"] * len(job_ids))
    cursor.execute(
        f"DELETE FROM job_applications WHERE job_id IN ({placeholders})",
        tuple(job_ids)
    )

def _delete_job_seeker_related(conn, cursor, user_id, job_seeker_pk):
    app_cols = get_table_columns(conn, 'job_applications') or set()
    js_fk = None
    for candidate in ['job_seeker_id', 'seeker_id', 'candidate_id', 'user_id']:
        if candidate in app_cols:
            js_fk = candidate
            break
    if js_fk:
        val = job_seeker_pk if js_fk != 'user_id' else user_id
        cursor.execute(f"DELETE FROM job_applications WHERE {js_fk} = %s", (val,))
    if table_exists(conn, 'job_seeker_skills'):
        cols = get_table_columns(conn, 'job_seeker_skills') or set()
        fk_col = pick_first_column(cols, ['job_seeker_id', 'seeker_id', 'candidate_id', 'user_id'])
        if fk_col:
            fk_val = job_seeker_pk if fk_col != 'user_id' else user_id
            cursor.execute(f"DELETE FROM job_seeker_skills WHERE {fk_col} = %s", (fk_val,))
    if table_exists(conn, 'cv_analysis'):
        cursor.execute("DELETE FROM cv_analysis WHERE job_seeker_id = %s OR job_seeker_id = %s", (job_seeker_pk, user_id))
    if job_seeker_pk:
        pk_col = get_job_seeker_pk_column(conn)
        if pk_col:
            cursor.execute(f"DELETE FROM job_seekers WHERE {pk_col} = %s", (job_seeker_pk,))
        else:
            cursor.execute("DELETE FROM job_seekers WHERE user_id = %s", (user_id,))

def _delete_company_related(conn, cursor, company_id):
    if not company_id:
        return
    cursor.execute("SELECT id FROM jobs WHERE company_id = %s", (company_id,))
    job_rows = cursor.fetchall() or []
    job_ids = [r.get('id') for r in job_rows if r.get('id')]
    _delete_job_applications_for_job_ids(cursor, job_ids)
    if job_ids:
        placeholders = ", ".join(["%s"] * len(job_ids))
        cursor.execute(f"DELETE FROM jobs WHERE id IN ({placeholders})", tuple(job_ids))
    cursor.execute("DELETE FROM companies WHERE id = %s", (company_id,))

@app.route('/api/admin/health', methods=['GET'])
@token_required
def admin_health(current_user_id):
    conn = get_db_connection()
    if not conn:
        return jsonify({'error': 'Database connection failed'}), 500

    cursor = None
    try:
        assert_admin(current_user_id, conn)
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT 1")
            cursor.fetchone()
            db_status = {'status': 'ok', 'details': 'Database responsiveness ok'}
        except Exception as db_err:
            db_status = {'status': 'error', 'details': str(db_err)}
        finally:
            cursor.close()
            cursor = None

        table_checks = {}
        for table in ['users', 'companies', 'job_seekers', 'jobs', 'job_applications', 'conversations', 'messages']:
            try:
                table_checks[table] = table_exists(conn, table)
            except Exception as tbl_err:
                table_checks[table] = f"error: {tbl_err}"

        overall_status = 'ok' if db_status['status'] == 'ok' else 'degraded'
        payload = {
            'status': overall_status,
            'database': db_status,
            'tables': table_checks,
            'last_checked': datetime.datetime.utcnow().isoformat() + 'Z'
        }
        return jsonify(payload), 200
    except Exception as e:
        if conn:
            conn.rollback()
        app.logger.exception("Failed to load admin health: %s", e)
        return jsonify({'error': 'Internal server error', 'detail': str(e)}), 500
    finally:
        try:
            if cursor is not None:
                cursor.close()
        except Exception:
            pass
        try:
            conn.close()
        except Exception:
            pass


@app.route('/api/admin/users', methods=['GET'])
@token_required
def admin_users(current_user_id):
    conn = get_db_connection()
    if not conn:
        return jsonify({'error': 'Database connection failed'}), 500
    cursor = None
    try:
        assert_admin(current_user_id, conn)
        cursor = conn.cursor(dictionary=True)

        q = (request.args.get('q') or "").strip()
        filter_type = (request.args.get('type') or "").strip().lower()
        limit = request.args.get('limit', 200, type=int) or 200
        limit = min(max(limit, 10), 500)

        base = """
            SELECT id, name, email, user_type, is_active, created_at, updated_at
            FROM users
        """
        where_clauses = []
        params = []
        if filter_type in {'job_seeker', 'company', 'admin'}:
            where_clauses.append("user_type = %s")
            params.append(filter_type)
        if q:
            where_clauses.append("(LOWER(name) LIKE %s OR LOWER(email) LIKE %s)")
            params.extend([f"%{q.lower()}%", f"%{q.lower()}%"])
        where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
        sql = f"""
            {base}
            {where_sql}
            ORDER BY created_at DESC
            LIMIT %s
        """
        params.append(limit)
        cursor.execute(sql, tuple(params))
        rows = cursor.fetchall() or []
        users = [
            {
                'id': r.get('id'),
                'name': r.get('name') or 'Unspecified',
                'email': r.get('email'),
                'userType': r.get('user_type'),
                'isActive': bool(r.get('is_active')),
                'createdAt': r.get('created_at'),
                'updatedAt': r.get('updated_at'),
            }
            for r in rows
        ]
        return jsonify({'users': users}), 200
    except Exception as e:
        if conn:
            conn.rollback()
        app.logger.exception("Failed to load admin users: %s", e)
        return jsonify({'error': 'Internal server error', 'detail': str(e)}), 500
    finally:
        try:
            if cursor is not None:
                cursor.close()
        except Exception:
            pass
        try:
            conn.close()
        except Exception:
            pass



@app.route('/api/admin/users/<int:user_id>', methods=['DELETE'])
@token_required
def admin_delete_user(current_user_id, user_id):

    conn = get_db_connection()
    if not conn:
        return jsonify({'error': 'Database connection failed'}), 500
    cursor = None
    try:
        assert_admin(current_user_id, conn)
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT user_type FROM users WHERE id=%s", (user_id,))
        row = cursor.fetchone()
        if not row:
            return jsonify({'error': 'User not found'}), 404
        if row.get('user_type') == 'admin':
            return jsonify({'error': 'Cannot delete admin users via this endpoint'}), 403
        user_type = row.get('user_type')
        if user_type == 'job_seeker':
            js_pk = get_job_seeker_id(conn, user_id)
            _delete_job_seeker_related(conn, cursor, user_id, js_pk)
        elif user_type == 'company':
            cursor.execute("SELECT id FROM companies WHERE user_id=%s", (user_id,))
            company_row = cursor.fetchone()
            company_id = company_row.get('id') if company_row else None
            _delete_company_related(conn, cursor, company_id)
        cursor.execute("DELETE FROM users WHERE id=%s", (user_id,))
        conn.commit()
        return jsonify({'message': 'User deleted'}), 200
    except Exception as e:
        if conn:
            conn.rollback()
        app.logger.exception("Failed to delete admin user %s: %s", user_id, e)
        return jsonify({'error': 'Internal server error', 'detail': str(e)}), 500
    finally:
        try:
            if cursor is not None:
                cursor.close()
        except Exception:
            pass
        try:
            conn.close()
        except Exception:
            pass


@app.route('/api/admin/jobs', methods=['GET'])
@token_required
def admin_jobs(current_user_id):
    conn = get_db_connection()
    if not conn:
        return jsonify({'error': 'Database connection failed'}), 500
    cursor = None
    try:
        assert_admin(current_user_id, conn)
        cursor = conn.cursor(dictionary=True)
        params = []
        where = []
        q = (request.args.get('q') or "").strip().lower()
        status_filter = (request.args.get('status') or "").strip().lower()
        job_cols = get_table_columns(conn, 'jobs') or set()
        company_cols = get_table_columns(conn, 'companies') or set()
        join_companies = 'company_id' in job_cols and bool(company_cols)

        if status_filter:
            where.append("LOWER(j.status) = %s")
            params.append(status_filter)
        search_expr = []
        if q:
            search_expr.append("LOWER(j.title) LIKE %s")
            search_expr.append("LOWER(j.description) LIKE %s")
            if join_companies:
                company_search_col = None
                for candidate in ['company_name', 'name']:
                    if candidate in company_cols:
                        company_search_col = candidate
                        break
                if company_search_col:
                    search_expr.append(f"LOWER(c.{company_search_col}) LIKE %s")
            params.extend([f"%{q}%"] * len(search_expr))
        if search_expr:
            where.append(f"({' OR '.join(search_expr)})")
        where_sql = f"WHERE {' AND '.join(where)}" if where else ""
        limit = min(max(request.args.get('limit', 200, type=int) or 200, 10), 500)

        company_display = "'Company'"
        if join_companies:
            candidates = [col for col in ['company_name', 'name'] if col in company_cols]
            if candidates:
                expressions = ", ".join(f"COALESCE(c.{col}, '')" for col in candidates)
                company_display = f"COALESCE(NULLIF({expressions}, ''), 'Company')"

        sql = f"""
            SELECT j.id, j.title, j.location, j.job_type, j.status, j.company_id, j.created_at,
                   {company_display} AS company_name
            FROM jobs j
            {"LEFT JOIN companies c ON c.id = j.company_id" if join_companies else ""}
            {where_sql}
            ORDER BY j.created_at DESC
            LIMIT %s
        """

        params.append(limit)
        cursor.execute(sql, tuple(params))
        jobs = []
        for row in cursor.fetchall() or []:
            jobs.append({
                'id': row.get('id'),
                'title': row.get('title'),
                'location': row.get('location'),
                'jobType': row.get('job_type'),
                'status': row.get('status'),
                'companyId': row.get('company_id'),
                'companyName': row.get('company_name'),
                'createdAt': row.get('created_at'),
            })
        return jsonify({'jobs': jobs}), 200
    except Exception as e:
        if conn:
            conn.rollback()
        app.logger.exception("Failed to load admin jobs: %s", e)
        return jsonify({'error': 'Internal server error', 'detail': str(e)}), 500
    finally:
        try:
            if cursor is not None:
                cursor.close()
        except Exception:
            pass
        try:
            conn.close()
        except Exception:
            pass


@app.route('/api/admin/jobs/<int:job_id>', methods=['DELETE'])
@token_required
def admin_delete_job(current_user_id, job_id):
    conn = get_db_connection()
    if not conn:
        return jsonify({'error': 'Database connection failed'}), 500
    cursor = None
    try:
        assert_admin(current_user_id, conn)
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT id FROM jobs WHERE id = %s", (job_id,))
        job = cursor.fetchone()
        if not job:
            return jsonify({'error': 'Job not found'}), 404
        _delete_job_applications_for_job_ids(cursor, [job_id])
        cursor.execute("DELETE FROM jobs WHERE id = %s", (job_id,))
        conn.commit()
        return jsonify({'message': 'Job deleted'}), 200
    except Exception as e:
        if conn:
            conn.rollback()
        app.logger.exception("Failed to delete admin job %s: %s", job_id, e)
        return jsonify({'error': 'Internal server error', 'detail': str(e)}), 500
    finally:
        try:
            if cursor is not None:
                cursor.close()
        except Exception:
            pass
        try:
            conn.close()
        except Exception:
            pass


@app.route('/api/admin/companies', methods=['GET'])
@token_required
def admin_companies(current_user_id):
    conn = get_db_connection()
    if not conn:
        return jsonify({'error': 'Database connection failed'}), 500
    cursor = None
    try:
        assert_admin(current_user_id, conn)
        cursor = conn.cursor(dictionary=True)
        params = []
        where = []
        status_filter = (request.args.get('status') or "").strip().lower()
        q = (request.args.get('q') or "").strip().lower()
        if status_filter:
            where.append("LOWER(COALESCE(status,'active')) = %s")
            params.append(status_filter)
        if q:
            where.append("(LOWER(company_name) LIKE %s OR LOWER(description) LIKE %s)")
            params.extend([f"%{q}%", f"%{q}%"])
        where_sql = f"WHERE {' AND '.join(where)}" if where else ""
        sql = f"""
            SELECT id, company_name, industry, website, description, contact_email, is_verified, created_at
            FROM companies
            {where_sql}
            ORDER BY created_at DESC
            LIMIT 200
        """
        cursor.execute(sql, tuple(params))
        companies = []
        for row in cursor.fetchall() or []:
            companies.append({
                'id': row.get('id'),
                'companyName': row.get('company_name'),
                'industry': row.get('industry'),
                'website': row.get('website'),
                'description': row.get('description'),
                'contactEmail': row.get('contact_email'),
                'isVerified': bool(row.get('is_verified')),
                'createdAt': row.get('created_at'),
            })
        return jsonify({'companies': companies}), 200
    except Exception as e:
        if conn:
            conn.rollback()
        app.logger.exception("Failed to load companies: %s", e)
        return jsonify({'error': 'Internal server error', 'detail': str(e)}), 500
    finally:
        try:
            if cursor is not None:
                cursor.close()
        except Exception:
            pass
        try:
            conn.close()
        except Exception:
            pass


@app.route('/api/admin/companies/<int:company_id>', methods=['PUT'])
@token_required
def admin_update_company(current_user_id, company_id):
    conn = get_db_connection()
    if not conn:
        return jsonify({'error': 'Database connection failed'}), 500
    cursor = None
    try:
        assert_admin(current_user_id, conn)
        payload = request.get_json(silent=True) or {}
        if not payload:
            return jsonify({'error': 'Invalid payload'}), 400
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM companies WHERE id=%s", (company_id,))
        row = cursor.fetchone()
        if not row:
            return jsonify({'error': 'Company not found'}), 404
        fields = {}
        if 'companyName' in payload:
            fields['company_name'] = payload['companyName']
        if 'description' in payload:
            fields['description'] = payload['description']
        if 'website' in payload:
            fields['website'] = payload['website']
        if 'industry' in payload:
            fields['industry'] = payload['industry']
        if 'isVerified' in payload:
            fields['is_verified'] = 1 if payload['isVerified'] else 0
        if not fields:
            return jsonify({'error': 'No fields to update'}), 400
        set_clause = ", ".join(f"{k}=%s" for k in fields)
        params = list(fields.values())
        params.append(company_id)
        cursor.execute(f"UPDATE companies SET {set_clause} WHERE id=%s", tuple(params))
        conn.commit()
        return jsonify({'message': 'Company updated'}), 200
    except Exception as e:
        if conn:
            conn.rollback()
        app.logger.exception("Failed to update company %s: %s", company_id, e)
        return jsonify({'error': 'Internal server error', 'detail': str(e)}), 500
    finally:
        try:
            if cursor is not None:
                cursor.close()
        except Exception:
            pass
        try:
            conn.close()
        except Exception:
            pass


@app.route('/api/admin/users/<int:user_id>', methods=['PUT'])
@token_required
def admin_update_user(current_user_id, user_id):
    conn = get_db_connection()
    if not conn:
        return jsonify({'error': 'Database connection failed'}), 500
    cursor = None
    try:
        assert_admin(current_user_id, conn)
        payload = request.get_json(silent=True) or {}
        if not payload:
            return jsonify({'error': 'Invalid payload'}), 400
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT user_type FROM users WHERE id=%s", (user_id,))
        row = cursor.fetchone()
        if not row:
            return jsonify({'error': 'User not found'}), 404
        if row.get('user_type') == 'admin' and payload.get('user_type') != 'admin':
            return jsonify({'error': 'Cannot demote super admins via this endpoint'}), 403
        fields = {}
        if payload.get('name') is not None:
            fields['name'] = payload['name'].strip()
        if payload.get('email') is not None:
            fields['email'] = payload['email'].strip().lower()
        if payload.get('user_type') in {'job_seeker', 'company', 'admin'}:
            fields['user_type'] = payload['user_type']
        if 'is_active' in payload:
            fields['is_active'] = 1 if payload['is_active'] else 0
        if not fields:
            return jsonify({'error': 'No valid fields to update'}), 400
        set_parts = ", ".join([f"{k}=%s" for k in fields.keys()])
        cursor.execute(f"UPDATE users SET {set_parts} WHERE id=%s", (*fields.values(), user_id))
        conn.commit()
        return jsonify({'message': 'User updated'}), 200
    except Exception as e:
        if conn:
            conn.rollback()
        app.logger.exception("Failed to update admin user %s: %s", user_id, e)
        return jsonify({'error': 'Internal server error', 'detail': str(e)}), 500
    finally:
        try:
            if cursor is not None:
                cursor.close()
        except Exception:
            pass
        try:
            conn.close()
        except Exception:
            pass

@app.route('/api/jobs/<int:job_id>', methods=['GET'])
def get_job_details(job_id):
    """Return a single job with optional company info."""
    conn = get_db_connection()
    if not conn:
        return jsonify({'error': 'Database connection failed'}), 500
    mark_expired_jobs(conn)
    cur = conn.cursor(dictionary=True)
    try:
        job_cols = get_table_columns(conn, 'jobs') or set()
        if not job_cols:
            return jsonify({'error': 'Jobs table not available'}), 404

        company_cols = get_table_columns(conn, 'companies') or set()
        has_company = 'company_id' in job_cols and bool(company_cols)

        job_select = []
        for col in [
            'id', 'title', 'description', 'requirements', 'benefits', 'location',
            'job_type', 'experience_level', 'education_level', 'salary_min',
            'salary_max', 'salary_type', 'department', 'positions_available',
            'application_deadline', 'required_skills', 'bonus_skills', 'status',
            'created_at', 'updated_at', 'company_id', 'company_name', 'company'
        ]:
            if col in job_cols:
                job_select.append(f"j.{col} as {col}")

        company_select = []
        if has_company:
            if 'name' in company_cols:
                company_select.append("c.name as company_name")
            if 'company_name' in company_cols:
                company_select.append("c.company_name as company_name")
            if 'industry' in company_cols:
                company_select.append("c.industry as company_industry")
            if 'location' in company_cols:
                company_select.append("c.location as company_location")
            if 'website' in company_cols:
                company_select.append("c.website as company_website")
            if 'description' in company_cols:
                company_select.append("c.description as company_description")

        select_sql = ", ".join(job_select + company_select) if (job_select or company_select) else "j.*"
        sql = f"SELECT {select_sql} FROM jobs j"
        params = [job_id]
        if has_company:
            sql += " LEFT JOIN companies c ON j.company_id = c.id"
        sql += " WHERE j.id = %s LIMIT 1"

        cur.execute(sql, tuple(params))
        row = cur.fetchone()
        if not row:
            return jsonify({'error': 'Job not found'}), 404

        status_val = (row.get('status') or '').strip().lower()
        if status_val and status_val != 'active':
            return jsonify({'error': 'Job not available'}), 404

        def _parse_list(val):
            if val is None:
                return []
            if isinstance(val, (list, tuple)):
                return list(val)
            if isinstance(val, str):
                try:
                    parsed = json.loads(val)
                    if isinstance(parsed, list):
                        return parsed
                except Exception:
                    pass
            return []

        row['required_skills'] = _parse_list(row.get('required_skills'))
        row['bonus_skills'] = _parse_list(row.get('bonus_skills'))
        row['benefits'] = _parse_list(row.get('benefits'))

        return jsonify({'job': row}), 200
    except Exception as e:
        app.logger.exception("Failed to fetch job %s: %s", job_id, e)
        return jsonify({'error': 'Internal server error', 'detail': str(e)}), 500
    finally:
        try:
            cur.close()
        except Exception:
            pass
        try:
            conn.close()
        except Exception:
            pass

@app.route('/api/job-seeker/applications', methods=['GET'])
@token_required
def job_seeker_applications(current_user_id):
    """Return all applications for the authenticated job seeker."""
    conn = get_db_connection()
    if not conn:
        return jsonify({'error': 'Database connection failed'}), 500
    cursor = conn.cursor(dictionary=True)
    try:
        # Resolve job seeker identifier
        js_cols = get_table_columns(conn, 'job_seekers') or set()
        js_pk_col = None
        for candidate in ['job_seeker_id', 'id']:
            if candidate in js_cols:
                js_pk_col = candidate
                break
        if not js_pk_col:
            return jsonify({'applications': []}), 200

        cursor.execute(f"SELECT {js_pk_col} FROM job_seekers WHERE user_id = %s LIMIT 1", (current_user_id,))
        row = cursor.fetchone()
        if not row:
            return jsonify({'applications': []}), 200
        js_id = row[js_pk_col]

        app_cols = get_table_columns(conn, 'job_applications') or set()
        job_cols = get_table_columns(conn, 'jobs') or set()
        company_cols = get_table_columns(conn, 'companies') or set()

        if not app_cols:
            return jsonify({'applications': []}), 200

        js_fk = 'job_seeker_id' if 'job_seeker_id' in app_cols else ('user_id' if 'user_id' in app_cols else None)
        if not js_fk:
            return jsonify({'applications': []}), 200
        status_col = 'application_status' if 'application_status' in app_cols else ('status' if 'status' in app_cols else None)
        applied_col = 'applied_at' if 'applied_at' in app_cols else ('created_at' if 'created_at' in app_cols else None)
        match_col = 'match_score' if 'match_score' in app_cols else None
        interview_col = 'interview_score' if 'interview_score' in app_cols else None

        select_parts = ["ja.id as app_id", "ja.job_id"]
        if js_fk:
            select_parts.append(f"ja.{js_fk} as seeker_ref")
        if status_col:
            select_parts.append(f"ja.{status_col} as app_status")
        if applied_col:
            select_parts.append(f"ja.{applied_col} as applied_at")
        if match_col:
            select_parts.append(f"ja.{match_col} as match_score")
        if interview_col:
            select_parts.append(f"ja.{interview_col} as interview_score")

        job_title_col = 'title' if 'title' in job_cols else None
        job_company_col = 'company_id' if 'company_id' in job_cols else None
        if job_title_col:
            select_parts.append(f"j.{job_title_col} as job_title")
        if job_company_col:
            select_parts.append("j.company_id")

        where_col = js_fk
        sql = f"""
            SELECT {', '.join(select_parts)}
            FROM job_applications ja
            LEFT JOIN jobs j ON j.id = ja.job_id
            WHERE {where_col} = %s
            ORDER BY ja.id DESC
        """
        cursor.execute(sql, (js_id if js_fk == 'job_seeker_id' else current_user_id,))
        rows = cursor.fetchall() or []

        applications = []
        for r in rows:
            company_name = None
            if job_company_col and r.get('company_id') and company_cols:
                cursor.execute(
                    f"SELECT company_name FROM companies WHERE id = %s",
                    (r.get('company_id'),)
                )
                crow = cursor.fetchone()
                if crow:
                    company_name = crow.get('company_name')

            applications.append({
                'job_id': r.get('job_id'),
                'id': r.get('app_id'),
                'job_title': r.get('job_title'),
                'company': company_name,
                'status': r.get('app_status') or 'applied',
                'applied_at': r.get('applied_at'),
                'match_score': r.get('match_score'),
                'interview_score': r.get('interview_score'),
            })

        return jsonify({'applications': applications}), 200
    except Exception as e:
        app.logger.exception("Failed to load job seeker applications: %s", e)
        return jsonify({'error': 'Internal server error', 'detail': str(e)}), 500
    finally:
        try:
            cursor.close()
        except Exception:
            pass
        try:
            conn.close()
        except Exception:
            pass


@app.route('/api/job-seeker/top-matches', methods=['GET'])
@token_required
def job_seeker_top_matches(current_user_id):
    """Return top job matches for the current job seeker ordered by match_score/recency."""
    conn = get_db_connection()
    if not conn:
        return jsonify({'matches': []}), 200
    cursor = conn.cursor(dictionary=True)
    try:
        profile = fetch_job_seeker_profile(conn, current_user_id)
        if not profile:
            return jsonify({'matches': []}), 200
        js_id = profile.get('id')

        app_cols = get_table_columns(conn, 'job_applications') or set()
        job_cols = get_table_columns(conn, 'jobs') or set()
        company_cols = get_table_columns(conn, 'companies') or set()

        js_fk = pick_first_column(app_cols, ['job_seeker_id', 'seeker_id', 'user_id'])
        if not js_fk:
            return jsonify({'matches': []}), 200

        status_col = pick_first_column(app_cols, ['application_status', 'status'])
        match_col = 'match_score' if 'match_score' in app_cols else None
        applied_col = pick_first_column(app_cols, ['applied_at', 'created_at'])
        title_col = 'title' if 'title' in job_cols else None
        location_col = 'location' if 'location' in job_cols else None
        type_col = 'job_type' if 'job_type' in job_cols else None
        salary_min_col = 'salary_min' if 'salary_min' in job_cols else None
        salary_max_col = 'salary_max' if 'salary_max' in job_cols else None
        skills_col = 'required_skills' if 'required_skills' in job_cols else None
        company_name_col = None
        if company_cols:
            for c in ['company_name', 'name']:
                if c in company_cols:
                    company_name_col = c
                    break

        select_parts = ["ja.id as app_id", "ja.job_id"]
        if status_col:
            select_parts.append(f"ja.{status_col} as app_status")
        if applied_col:
            select_parts.append(f"ja.{applied_col} as applied_at")
        if match_col:
            select_parts.append(f"ja.{match_col} as match_score")
        if title_col:
            select_parts.append(f"j.{title_col} as job_title")
        if location_col:
            select_parts.append(f"j.{location_col} as job_location")
        if type_col:
            select_parts.append(f"j.{type_col} as job_type")
        if salary_min_col:
            select_parts.append(f"j.{salary_min_col} as salary_min")
        if salary_max_col:
            select_parts.append(f"j.{salary_max_col} as salary_max")
        if skills_col:
            select_parts.append(f"j.{skills_col} as required_skills")
        if company_name_col:
            select_parts.append(f"c.{company_name_col} as company_name")

        company_join = "LEFT JOIN companies c ON c.id = j.company_id" if company_name_col else ""
        sql = f"""
            SELECT {', '.join(select_parts)}
            FROM job_applications ja
            LEFT JOIN jobs j ON ja.job_id = j.id
            {company_join}
            WHERE ja.{js_fk} = %s
            ORDER BY COALESCE(ja.{match_col}, 0) DESC, ja.id DESC
            LIMIT 50
        """
        cursor.execute(sql, (js_id if js_fk == 'job_seeker_id' else current_user_id,))
        rows = cursor.fetchall() or []

        matches = []
        for r in rows:
            skills = []
            raw = r.get('required_skills')
            if isinstance(raw, str):
                try:
                    skills = json.loads(raw)
                    if not isinstance(skills, list):
                        skills = []
                except Exception:
                    skills = []
            elif isinstance(raw, (list, tuple)):
                skills = list(raw)
            matches.append({
                'application_id': r.get('app_id'),
                'job_id': r.get('job_id'),
                'title': r.get('job_title'),
                'company': r.get('company_name'),
                'location': r.get('job_location'),
                'job_type': r.get('job_type'),
                'salary_min': r.get('salary_min'),
                'salary_max': r.get('salary_max'),
                'match_score': r.get('match_score'),
                'required_skills': skills,
                'applied_at': r.get('applied_at'),
            })

        return jsonify({'matches': matches}), 200
    except Exception as e:
        app.logger.exception("Failed to load job seeker top matches: %s", e)
        return jsonify({'matches': []}), 200
    finally:
        try:
            cursor.close()
        except Exception:
            pass
        try:
            conn.close()
        except Exception:
            pass

@app.route('/api/job-seeker/mock-interviews', methods=['GET'])
@token_required
def job_seeker_mock_interviews(current_user_id):
    """Return accepted/scheduled applications and meeting details for the logged-in job seeker."""
    conn = get_db_connection()
    if not conn:
        return jsonify({'error': 'Database connection failed'}), 500
    cursor = conn.cursor(dictionary=True)
    try:
        profile = fetch_job_seeker_profile(conn, current_user_id)
        if not profile:
            return jsonify({'error': 'Job seeker profile not found'}), 404
        js_id = profile.get('id')

        app_cols = get_table_columns(conn, 'job_applications') or set()
        job_cols = get_table_columns(conn, 'jobs') or set()
        company_cols = get_table_columns(conn, 'companies') or set()

        js_fk = pick_first_column(app_cols, ['job_seeker_id', 'seeker_id', 'user_id'])
        if not js_fk:
            return jsonify({'interviews': []}), 200
        status_col = pick_first_column(app_cols, ['application_status', 'status'])
        applied_col = pick_first_column(app_cols, ['applied_at', 'created_at'])
        match_col = 'match_score' if 'match_score' in app_cols else None
        interview_col = 'interview_score' if 'interview_score' in app_cols else None
        schedule_col = pick_first_column(app_cols, ['schedule_date', 'interview_date', 'interview_at', 'interview_time', 'interview_scheduled_at'])
        meeting_col = pick_first_column(app_cols, ['meeting_url', 'join_url', 'virtual_meeting_url', 'meeting_link'])

        select_parts = ["ja.id as app_id", "ja.job_id"]
        if js_fk:
            select_parts.append(f"ja.{js_fk} as seeker_ref")
        if status_col:
            select_parts.append(f"ja.{status_col} as app_status")
        if applied_col:
            select_parts.append(f"ja.{applied_col} as applied_at")
        if match_col:
            select_parts.append(f"ja.{match_col} as match_score")
        if interview_col:
            select_parts.append(f"ja.{interview_col} as interview_score")
        if schedule_col:
            select_parts.append(f"ja.{schedule_col} as scheduled_at")
        if meeting_col:
            select_parts.append(f"ja.{meeting_col} as meeting_url")

        job_title_col = 'title' if 'title' in job_cols else None
        company_id_col = 'company_id' if 'company_id' in job_cols else None
        company_name_col = None
        if company_cols:
            for candidate in ['company_name', 'name']:
                if candidate in company_cols:
                    company_name_col = candidate
                    break
        if job_title_col:
            select_parts.append(f"j.{job_title_col} as job_title")
        if company_id_col:
            select_parts.append("j.company_id")
        if company_name_col:
            select_parts.append(f"c.{company_name_col} as company_name")

        company_join = "LEFT JOIN companies c ON c.id = j.company_id" if company_name_col else ""

        where_col = js_fk
        join_sql = """
            FROM job_applications ja
            LEFT JOIN jobs j ON j.id = ja.job_id
            {company_join}
            WHERE {where_col} = %s
        """.format(company_join=company_join, where_col=where_col)

        filter_statuses = ("accepted", "hired", "offer", "interview", "interviewing", "interview_scheduled")
        params = [js_id if js_fk == 'job_seeker_id' else current_user_id]
        status_filter_sql = ""
        if status_col:
            placeholders = ", ".join(["%s"] * len(filter_statuses))
            status_filter_sql = f" AND (ja.{status_col} IN ({placeholders})"
            params.extend(filter_statuses)
            if schedule_col:
                status_filter_sql += f" OR ja.{schedule_col} IS NOT NULL"
            status_filter_sql += ")"

        sql = f"SELECT {', '.join(select_parts)} {join_sql}{status_filter_sql} ORDER BY ja.id DESC"
        cursor.execute(sql, tuple(params))
        rows = cursor.fetchall() or []

        # Load latest interview status per application (from interviews table) to detect completion
        interviews_map = {}
        app_ids = [r.get('app_id') for r in rows if r.get('app_id')]
        interview_cols = get_table_columns(conn, 'interviews') or set()
        if app_ids and interview_cols and 'application_id' in interview_cols:
            placeholders = ','.join(['%s'] * len(app_ids))
            try:
                cursor.execute(
                    f"""
                    SELECT i.*
                    FROM interviews i
                    JOIN (
                        SELECT application_id, MAX(id) AS latest_id
                        FROM interviews
                        WHERE application_id IN ({placeholders})
                        GROUP BY application_id
                    ) li ON i.id = li.latest_id
                    """,
                    tuple(app_ids)
                )
                for iv in cursor.fetchall() or []:
                    interviews_map[iv.get('application_id')] = iv
            except Exception:
                app.logger.exception("Failed to fetch interviews for mock interview list")

        int_status_col = 'status' if 'status' in interview_cols else None
        int_rating_col = 'rating' if 'rating' in interview_cols else None

        interviews = []
        for r in rows:
            iv = interviews_map.get(r.get('app_id')) or {}
            iv_status = iv.get(int_status_col) if int_status_col else None
            iv_rating = iv.get(int_rating_col) if int_rating_col else None
            interviews.append({
                'application_id': r.get('app_id'),
                'job_id': r.get('job_id'),
                'job_title': r.get('job_title'),
                'company': r.get('company_name'),
                'status': iv_status or r.get('app_status'),
                'interview_status': iv_status,
                'scheduled_at': r.get('scheduled_at'),
                'match_score': r.get('match_score'),
                'interview_score': iv_rating if iv_rating is not None else r.get('interview_score'),
                'meeting_url': r.get('meeting_url'),
                'applied_at': r.get('applied_at'),
            })

        return jsonify({
            'interviews': interviews,
            'predicted_role': profile.get('predicted_job_role'),
            'profile': {'full_name': profile.get('full_name')}
        }), 200
    except Exception as e:
        app.logger.exception("Failed to load mock interviews: %s", e)
        return jsonify({'error': 'Internal server error', 'detail': str(e)}), 500
    finally:
        try:
            cursor.close()
        except Exception:
            pass
        try:
            conn.close()
        except Exception:
            pass

@app.route('/api/job-seeker/mock-interviews/questions', methods=['GET'])
@token_required
def job_seeker_mock_interview_questions(current_user_id):
    """Return generated interview questions for the seeker based on application/job role."""
    app_id = request.args.get('application_id', type=int)
    if not app_id:
        return jsonify({'error': 'application_id is required'}), 400

    conn = get_db_connection()
    if not conn:
        return jsonify({'error': 'Database connection failed'}), 500
    cursor = conn.cursor(dictionary=True)
    try:
        profile = fetch_job_seeker_profile(conn, current_user_id)
        if not profile:
            return jsonify({'error': 'Job seeker profile not found'}), 404
        js_id = profile.get('id')

        app_cols = get_table_columns(conn, 'job_applications') or set()
        js_fk = pick_first_column(app_cols, ['job_seeker_id', 'seeker_id', 'user_id'])
        if not js_fk:
            return jsonify({'error': 'job_applications missing job seeker reference'}), 500

        cursor.execute(
            f"""
            SELECT ja.job_id, ja.{js_fk} as seeker_ref, ja.id as app_id, ja.application_status,
                   j.title as job_title, j.department
            FROM job_applications ja
            LEFT JOIN jobs j ON j.id = ja.job_id
            WHERE ja.id = %s
            """,
            (app_id,)
        )
        app_row = cursor.fetchone()
        if not app_row or str(app_row.get('seeker_ref')) != str(js_id if js_fk == 'job_seeker_id' else current_user_id):
            return jsonify({'error': 'Application not found'}), 404

        role = profile.get('predicted_job_role') or app_row.get('job_title') or app_row.get('department')
        questions = generate_role_questions(role, count=5)
        return jsonify({'questions': questions, 'role': role}), 200
    except Exception as e:
        current_app.logger.exception("Failed to generate mock interview questions: %s", e)
        return jsonify({'error': 'Internal server error', 'detail': str(e)}), 500
    finally:
        try:
            cursor.close()
        except Exception:
            pass
        try:
            conn.close()
        except Exception:
            pass


@app.route('/api/job-seeker/mock-interviews/transcribe', methods=['POST'])
@token_required
def job_seeker_mock_interview_transcribe(current_user_id):
    """Transcribe an uploaded audio answer using OpenAI; uses application ownership for auth."""
    app_id = request.form.get('application_id') or request.args.get('application_id')
    if not app_id:
        return jsonify({'error': 'application_id is required'}), 400

    audio_file = request.files.get('audio') or request.files.get('file')
    if not audio_file:
        return jsonify({'error': 'audio file is required'}), 400

    conn = get_db_connection()
    if not conn:
        return jsonify({'error': 'Database connection failed'}), 500
    cursor = conn.cursor(dictionary=True)
    try:
        profile = fetch_job_seeker_profile(conn, current_user_id)
        if not profile:
            return jsonify({'error': 'Job seeker profile not found'}), 404
        js_id = profile.get('id')

        app_cols = get_table_columns(conn, 'job_applications') or set()
        js_fk = pick_first_column(app_cols, ['job_seeker_id', 'seeker_id', 'user_id'])
        if not js_fk:
            return jsonify({'error': 'job_applications missing job seeker reference'}), 500

        cursor.execute(
            f"SELECT {js_fk} as seeker_ref FROM job_applications WHERE id = %s",
            (app_id,)
        )
        row = cursor.fetchone()
        if not row or str(row.get('seeker_ref')) != str(js_id if js_fk == 'job_seeker_id' else current_user_id):
            return jsonify({'error': 'Application not found'}), 404

        transcript = vm_transcribe_audio(audio_file)
        return jsonify({'transcript': transcript}), 200
    except Exception as e:
        current_app.logger.exception("Failed to transcribe interview audio: %s", e)
        return jsonify({'error': 'Internal server error', 'detail': str(e)}), 500
    finally:
        try:
            cursor.close()
        except Exception:
            pass
        try:
            conn.close()
        except Exception:
            pass


@app.route('/api/job-seeker/mock-interviews/tts', methods=['POST'])
@token_required
def job_seeker_mock_interview_tts(current_user_id):
    """Generate TTS audio for a provided question or prompt."""
    payload = request.get_json(silent=True) or {}
    text = payload.get('text') or payload.get('question') or payload.get('content')
    if not text:
        return jsonify({'error': 'text is required'}), 400
    result = vm_text_to_speech_to_wav(text)
    if not result:
        return jsonify({'error': 'TTS unavailable'}), 500
    fname, url = result
    return jsonify({'filename': fname, 'audio_url': url}), 200


# ===== Audio-native interview session endpoints (full VirtualMeeting-style flow) =====

# In-memory session cache (simple/non-persistent). For production, move to DB/Redis.
VM_SESSIONS = {}

def _vm_session_key(user_id, app_id):
    return f"{user_id}:{app_id}"

def _vm_derive_role(conn, app_id, current_user_id):
    """Return (role_string, app_row) ensuring ownership."""
    profile = fetch_job_seeker_profile(conn, current_user_id)
    if not profile:
        abort(404, description="Job seeker profile not found")
    js_id = profile.get('id')

    app_cols = get_table_columns(conn, 'job_applications') or set()
    job_cols = get_table_columns(conn, 'jobs') or set()
    js_fk = pick_first_column(app_cols, ['job_seeker_id', 'seeker_id', 'user_id'])
    if not js_fk:
        abort(500, description="job_applications missing job seeker reference")

    cursor = conn.cursor(dictionary=True)
    try:
        select_parts = [f"ja.{js_fk} as seeker_ref", "ja.id as app_id", "ja.job_id"]
        select_parts.append("j.title as job_title" if 'title' in job_cols else "j.id as job_title")
        if 'department' in job_cols:
            select_parts.append("j.department")
        cursor.execute(
            f"""
            SELECT {', '.join(select_parts)}
            FROM job_applications ja
            LEFT JOIN jobs j ON j.id = ja.job_id
            WHERE ja.id = %s
            """,
            (app_id,)
        )
        row = cursor.fetchone()
    finally:
        cursor.close()

    if not row or str(row.get('seeker_ref')) != str(js_id if js_fk == 'job_seeker_id' else current_user_id):
        abort(404, description="Application not found")

    role = row.get('job_title') or row.get('department') or profile.get('predicted_job_role') or "candidate"
    return role, row


@app.route('/api/job-seeker/mock-interviews/session', methods=['POST'])
@token_required
def job_seeker_mock_interview_session(current_user_id):
    """
    Start an audio-native interview session:
      - Derives job role from application/job
      - Returns question 1 (text) and optional TTS URL
    """
    if not openai_client:
        return jsonify({'error': 'OpenAI not configured', 'detail': 'Set OPENAI_API_KEY on the server'}), 503
    payload = request.get_json(silent=True) or {}
    app_id = payload.get('application_id') or request.form.get('application_id')
    if not app_id:
        return jsonify({'error': 'application_id is required'}), 400

    conn = get_db_connection()
    if not conn:
        return jsonify({'error': 'Database connection failed'}), 500
    try:
        # Block re-entry if interview already completed
        existing_iv = get_interview_row(app_id)
        if existing_iv:
            iv_status = (existing_iv.get('status') or '').lower()
            if iv_status == 'completed':
                return jsonify({'error': 'Interview already completed for this application'}), 400

        key = _vm_session_key(current_user_id, app_id)
        if VM_SESSIONS.get(key, {}).get('done'):
            return jsonify({'error': 'Interview already completed for this application'}), 400

        # Attempt to resume from in-memory session
        resume_session = VM_SESSIONS.get(key) if VM_SESSIONS.get(key) and not VM_SESSIONS[key].get('done') else None

        # Attempt to resume from DB notes if available
        if not resume_session and existing_iv and (existing_iv.get('status') or '').lower() in ('scheduled', 'in_progress'):
            notes_raw = existing_iv.get('notes')
            if notes_raw:
                try:
                    parsed = json.loads(notes_raw) if isinstance(notes_raw, str) else notes_raw
                    if isinstance(parsed, dict) and not parsed.get('done'):
                        resume_session = parsed
                except Exception:
                    resume_session = None

        role, _ = _vm_derive_role(conn, app_id, current_user_id)

        if resume_session:
            history = resume_session.get('history') or []
            qa = resume_session.get('qa') or []
            q_num = resume_session.get('q_num') or (len(qa) + 1) or 1
            # Extract the last assistant question to replay
            question = None
            for msg in reversed(history):
                if msg.get('role') == 'assistant':
                    question = msg.get('content')
                    break
            if not question:
                question = vm_generate_interview_question(history, role, q_num)
                history.append({'role': 'assistant', 'content': question})
            tts = vm_text_to_speech_to_wav(question)
            # Restore session in memory
            VM_SESSIONS[key] = {
                'history': history,
                'q_num': q_num,
                'role': role,
                'done': False,
                'qa': qa,
                'meeting_url': resume_session.get('meeting_url') or os.getenv('VIRTUAL_MEETING_URL') or f"/pages/jobseeker/mock-interview-room.html?application_id={app_id}",
                'started_at': resume_session.get('started_at') or datetime.datetime.utcnow(),
            }
            resp = {'question': question, 'question_number': q_num, 'role': role, 'resume': True}
            if tts:
                _, url = tts
                resp['tts_url'] = url
            return jsonify(resp), 200

        # Fresh session
        history = []
        q_num = 1
        question = vm_generate_interview_question(history, role, q_num)
        tts = vm_text_to_speech_to_wav(question)
        key = _vm_session_key(current_user_id, app_id)
        VM_SESSIONS[key] = {
            'history': [{'role': 'assistant', 'content': question}],
            'q_num': q_num,
            'role': role,
            'done': False,
            'qa': [],
            'meeting_url': os.getenv('VIRTUAL_MEETING_URL') or f"/pages/jobseeker/mock-interview-room.html?application_id={app_id}",
            'started_at': datetime.datetime.utcnow()
        }
        state = {
            'history': VM_SESSIONS[key]['history'],
            'qa': [],
            'started_at': VM_SESSIONS[key]['started_at'].isoformat(),
            'role': role,
            'q_num': q_num
        }
        upsert_interview(app_id, {
            'interview_type': 'video_call',
            'scheduled_date': datetime.datetime.utcnow(),
            'duration_minutes': 5,
            'interviewers': json.dumps(["AI"], ensure_ascii=False),
            'meeting_url': VM_SESSIONS[key]['meeting_url'],
            'status': 'scheduled',
            'notes': json.dumps(state, ensure_ascii=False)
        })
        resp = {'question': question, 'question_number': q_num, 'role': role}
        if tts:
            _, url = tts
            resp['tts_url'] = url
        return jsonify(resp), 200
    except Exception as e:
        current_app.logger.exception("Failed to start VM interview session: %s", e)
        return jsonify({'error': 'Internal server error', 'detail': str(e)}), 500
    finally:
        try:
            conn.close()
        except Exception:
            pass


@app.route('/api/job-seeker/mock-interviews/respond', methods=['POST'])
@token_required
def job_seeker_mock_interview_respond(current_user_id):
    """
    Handle an audio answer:
      - Transcribe audio
      - Append to history
      - Return feedback + next question (+ optional TTS)
    """
    if not openai_client:
        return jsonify({'error': 'OpenAI not configured', 'detail': 'Set OPENAI_API_KEY on the server'}), 503
    app_id = request.form.get('application_id') or request.args.get('application_id')
    if not app_id:
        return jsonify({'error': 'application_id is required'}), 400
    audio_file = request.files.get('audio') or request.files.get('file')
    if not audio_file:
        return jsonify({'error': 'audio file is required'}), 400

    conn = get_db_connection()
    if not conn:
        return jsonify({'error': 'Database connection failed'}), 500
    try:
        role, _ = _vm_derive_role(conn, app_id, current_user_id)
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        raise e

    key = _vm_session_key(current_user_id, app_id)

    # Load persisted state if any (survives reloads/workers)
    interview_row = get_interview_row(app_id)
    meeting_url = None
    if interview_row and interview_row.get('meeting_url'):
        meeting_url = interview_row.get('meeting_url')
    if not meeting_url:
        meeting_url = os.getenv('VIRTUAL_MEETING_URL') or f"/pages/jobseeker/mock-interview-room.html?application_id={app_id}"
    persisted_state = {}
    if interview_row and interview_row.get('notes'):
        try:
            persisted_state = json.loads(interview_row.get('notes') or "{}")
        except Exception:
            persisted_state = {}

    history = persisted_state.get('history') or []
    qa_list = persisted_state.get('qa') or []
    started_at_val = persisted_state.get('started_at')
    if started_at_val:
        try:
            started_at = datetime.datetime.fromisoformat(started_at_val.replace('Z', '+00:00'))
        except Exception:
            started_at = datetime.datetime.utcnow()
    else:
        started_at = datetime.datetime.utcnow()

    session = {
        'history': history,
        'q_num': len(qa_list),
        'role': role,
        'done': False,
        'qa': qa_list,
        'meeting_url': meeting_url,
        'started_at': started_at
    }

    # Stop immediately if already completed (5 questions answered)
    if len(qa_list) >= 5:
        return jsonify({
            'done': True,
            'message': 'Interview already completed.',
            'qa': qa_list
        }), 200

    # Transcribe
    transcript = vm_transcribe_audio(audio_file)
    if not transcript:
        return jsonify({'error': 'Transcription failed'}), 500

    history = session.get('history', [])
    # Ensure last assistant question is in history; if none, add a generic opener
    if not history or history[-1].get('role') != 'assistant':
        history.append({'role': 'assistant', 'content': "Let's continue the interview."})

    history.append({'role': 'user', 'content': transcript})
    asked_question = ""
    for msg in reversed(history):
        if msg.get('role') != 'assistant':
            continue
        content = msg.get('content') or ""
        if not asked_question:
            asked_question = content
        if re.search(r"\bquestion\s*\d", content, flags=re.IGNORECASE):
            asked_question = content
            break
    eval_result = evaluate_answer(asked_question, transcript, role=role)
    fb_text = eval_result.get('feedback') or 'Captured.'
    score = eval_result.get('score')
    if fb_text:
        history.append({'role': 'assistant', 'content': fb_text})

    qa_list = session.get('qa') or []
    qa_list.append({
        'question': asked_question,
        'answer': transcript,
        'feedback': fb_text,
        'score': score
    })
    session['qa'] = qa_list

    current_q_num = len(qa_list)
    session['q_num'] = current_q_num
    next_q_num = current_q_num + 1

    # Hard stop after 5 questions, even if numbering drifted
    if current_q_num >= 5 or next_q_num > 5:
        session['done'] = True
        VM_SESSIONS[key] = session
        feedback_tts = vm_text_to_speech_to_wav("Interview complete. Thank you.")

        # Mark completion to prevent replay on refresh
        try:
            session['done_flag'] = True
            VM_SESSIONS[key]['done_flag'] = True
        except Exception:
            pass

        interview_data = session.get('qa') or []
        review_text = vm_generate_interview_review(role, interview_data)
        avg_score = None
        try:
            scores = [qa.get('score') for qa in interview_data if qa.get('score') is not None]
            if scores:
                avg_score = int(sum(scores) / len(scores))
        except Exception:
            avg_score = None

        started_at = session.get('started_at')
        duration_minutes = None
        if started_at:
            try:
                diff = datetime.datetime.utcnow() - started_at
                duration_minutes = max(1, int(diff.total_seconds() // 60) or 1)
            except Exception:
                duration_minutes = 5
        meeting_url = session.get('meeting_url') or f"/pages/jobseeker/mock-interview-room.html?application_id={app_id}"
        session_state = {
            'history': history,
            'qa': interview_data,
            'started_at': started_at.isoformat() if isinstance(started_at, datetime.datetime) else started_at,
            'role': role,
            'q_num': session.get('q_num'),
            'done': True
        }
        final_rating = normalize_rating(avg_score)
        upsert_interview(app_id, {
            'interview_type': 'video_call',
            'scheduled_date': started_at or datetime.datetime.utcnow(),
            'duration_minutes': duration_minutes or 5,
            'interviewers': json.dumps(["AI"], ensure_ascii=False),
            'meeting_url': meeting_url,
            'status': 'completed',
            'feedback': review_text,
            'rating': final_rating,
            'notes': json.dumps(session_state, ensure_ascii=False)
        })
        update_application_interview_score(app_id, final_rating)

        resp_done = {
            'transcript': transcript,
            'feedback': review_text or 'Interview complete',
            'score': avg_score,
            'done': True
        }
        if feedback_tts:
            _, fb_url = feedback_tts
            resp_done['feedback_tts_url'] = fb_url
        return jsonify(resp_done), 200

    next_question = vm_generate_interview_question(history, role, next_q_num)
    history.append({'role': 'assistant', 'content': next_question})
    session.update({'history': history, 'q_num': next_q_num})
    VM_SESSIONS[key] = session

    # Persist in-progress status with rolling QA log
    meeting_url = session.get('meeting_url') or f"/pages/jobseeker/mock-interview-room.html?application_id={app_id}"
    session_state = {
        'history': history,
        'qa': qa_list,
        'started_at': session.get('started_at').isoformat() if isinstance(session.get('started_at'), datetime.datetime) else session.get('started_at'),
        'role': role,
        'q_num': session.get('q_num'),
        'done': False
    }
    current_rating = normalize_rating(score)
    upsert_interview(app_id, {
        'interview_type': 'video_call',
        'scheduled_date': session.get('started_at') or datetime.datetime.utcnow(),
        'duration_minutes': 5,
        'interviewers': json.dumps(["AI"], ensure_ascii=False),
        'meeting_url': meeting_url,
        'status': 'in_progress',
        'rating': current_rating,
        'notes': json.dumps(session_state, ensure_ascii=False)
    })
    update_application_interview_score(app_id, current_rating)

    tts = vm_text_to_speech_to_wav(next_question)
    feedback_tts = vm_text_to_speech_to_wav("Got it. Here's your next question.")
    resp = {
        'transcript': transcript,
        'feedback': fb_text,
        'next_question': next_question,
        'next_question_number': next_q_num,
        'done': False,
    }
    if tts:
        _, url = tts
        resp['tts_url'] = url
    if feedback_tts:
        _, fb_url = feedback_tts
        resp['feedback_tts_url'] = fb_url
    return jsonify(resp), 200

@app.route('/api/job-seeker/mock-interviews/answer', methods=['POST'])
@token_required
def job_seeker_mock_interview_answer(current_user_id):
    """Evaluate a given answer and return feedback."""
    payload = request.get_json(silent=True) or {}
    app_id = payload.get('application_id')
    question = payload.get('question') or payload.get('question_text')
    answer = payload.get('answer') or payload.get('answer_text')
    if not app_id or not question:
        return jsonify({'error': 'application_id and question are required'}), 400

    conn = get_db_connection()
    if not conn:
        return jsonify({'error': 'Database connection failed'}), 500
    cursor = conn.cursor(dictionary=True)
    try:
        profile = fetch_job_seeker_profile(conn, current_user_id)
        if not profile:
            return jsonify({'error': 'Job seeker profile not found'}), 404
        js_id = profile.get('id')

        app_cols = get_table_columns(conn, 'job_applications') or set()
        js_fk = pick_first_column(app_cols, ['job_seeker_id', 'seeker_id', 'user_id'])
        if not js_fk:
            return jsonify({'error': 'job_applications missing job seeker reference'}), 500

        cursor.execute(
            f"SELECT {js_fk} as seeker_ref FROM job_applications WHERE id = %s",
            (app_id,)
        )
        row = cursor.fetchone()
        if not row or str(row.get('seeker_ref')) != str(js_id if js_fk == 'job_seeker_id' else current_user_id):
            return jsonify({'error': 'Application not found'}), 404

        role = profile.get('predicted_job_role')
        result = evaluate_answer(question, answer, role=role)
        return jsonify(result), 200
    except Exception as e:
        current_app.logger.exception("Failed to evaluate mock answer: %s", e)
        return jsonify({'error': 'Internal server error', 'detail': str(e)}), 500
    finally:
        try:
            cursor.close()
        except Exception:
            pass
        try:
            conn.close()
        except Exception:
            pass

@app.route('/api/job-seeker/mock-interviews/start', methods=['POST'])
@token_required
def job_seeker_start_mock_interview(current_user_id):
    """Allow a job seeker to start/join their scheduled virtual mock interview."""
    conn = get_db_connection()
    if not conn:
        return jsonify({'error': 'Database connection failed'}), 500
    cursor = conn.cursor(dictionary=True)
    try:
        payload = request.get_json(silent=True) or {}
        app_id = payload.get('application_id')
        if not app_id:
            return jsonify({'error': 'application_id is required'}), 400

        profile = fetch_job_seeker_profile(conn, current_user_id)
        if not profile:
            return jsonify({'error': 'Job seeker profile not found'}), 404
        js_id = profile.get('id')

        app_cols = get_table_columns(conn, 'job_applications') or set()
        job_cols = get_table_columns(conn, 'jobs') or set()
        js_fk = pick_first_column(app_cols, ['job_seeker_id', 'seeker_id', 'user_id'])
        status_col = pick_first_column(app_cols, ['application_status', 'status'])
        schedule_col = pick_first_column(app_cols, ['schedule_date', 'interview_date', 'interview_at', 'interview_time', 'interview_scheduled_at'])
        meeting_col = pick_first_column(app_cols, ['meeting_url', 'join_url', 'virtual_meeting_url', 'meeting_link'])

        if not js_fk:
            return jsonify({'error': 'job_applications missing job seeker reference column'}), 500

        select_parts = ["ja.id as app_id", "ja.job_id"]
        if status_col:
            select_parts.append(f"ja.{status_col} as app_status")
        if schedule_col:
            select_parts.append(f"ja.{schedule_col} as scheduled_at")
        if meeting_col:
            select_parts.append(f"ja.{meeting_col} as meeting_url")
        job_title_col = 'title' if 'title' in job_cols else None
        if job_title_col:
            select_parts.append(f"j.{job_title_col} as job_title")

        cursor.execute(
            f"""
            SELECT {', '.join(select_parts)}
            FROM job_applications ja
            LEFT JOIN jobs j ON j.id = ja.job_id
            WHERE ja.id = %s AND ja.{js_fk} = %s
            """,
            (app_id, js_id if js_fk == 'job_seeker_id' else current_user_id)
        )
        app_row = cursor.fetchone()
        if not app_row:
            return jsonify({'error': 'Application not found'}), 404

        scheduled_at = app_row.get('scheduled_at')
        now = datetime.datetime.utcnow()
        join_allowed = True
        if scheduled_at:
            try:
                if isinstance(scheduled_at, str):
                    scheduled_at_dt = datetime.datetime.fromisoformat(scheduled_at.replace('Z', '+00:00'))
                else:
                    scheduled_at_dt = scheduled_at
                allow_from = scheduled_at_dt - datetime.timedelta(minutes=15)
                join_allowed = now >= allow_from
            except Exception:
                join_allowed = True

        if not join_allowed:
            return jsonify({'error': 'Meeting not available yet', 'detail': 'Join will open 15 minutes before start'}), 403

        meeting_url = app_row.get('meeting_url')
        if not meeting_url:
            meeting_url = os.getenv('VIRTUAL_MEETING_URL') or f"/pages/jobseeker/mock-interview.html#session={app_id}"

        return jsonify({
            'application_id': app_row.get('app_id'),
            'job_title': app_row.get('job_title'),
            'predicted_role': profile.get('predicted_job_role'),
            'meeting_url': meeting_url,
            'status': app_row.get('app_status') or 'accepted'
        }), 200
    except Exception as e:
        app.logger.exception("Failed to start mock interview: %s", e)
        return jsonify({'error': 'Internal server error', 'detail': str(e)}), 500
    finally:
        try:
            cursor.close()
        except Exception:
            pass
        try:
            conn.close()
        except Exception:
            pass

@app.route('/api/job-seeker/applications', methods=['POST'])
@token_required
def job_seeker_apply(current_user_id):
    """Create a job application for the authenticated job seeker."""
    conn = get_db_connection()
    if not conn:
        return jsonify({'error': 'Database connection failed'}), 500
    cursor = conn.cursor(dictionary=True)
    try:
        payload = request.get_json(silent=True) or {}
        app.logger.info("Apply payload: %s", payload)
        job_id = payload.get('job_id') or payload.get('jobId') or payload.get('id')
        if not job_id:
            return jsonify({'error': 'job_id is required'}), 400

        # Resolve job seeker ID
        js_cols = get_table_columns(conn, 'job_seekers') or set()
        if not js_cols:
            return jsonify({'error': 'job_seekers table not found'}), 500

        js_id_col = None
        for candidate in ['job_seeker_id', 'id', 'seeker_id', 'user_id']:
            if candidate in js_cols:
                js_id_col = candidate
                break
        if not js_id_col:
            return jsonify({'error': 'job_seekers missing identifier column'}), 500

        cursor.execute(f"SELECT * FROM job_seekers WHERE user_id = %s LIMIT 1", (current_user_id,))
        js_row = cursor.fetchone()
        if not js_row:
            # Auto-create a minimal job seeker profile so the user can apply
            cursor.execute("SELECT name, email FROM users WHERE id = %s", (current_user_id,))
            user_row = cursor.fetchone() or {}
            full_name = user_row.get('name') or user_row.get('email') or "Job Seeker"
            insert_cols = []
            insert_vals = []
            for col, val in [
                ('user_id', current_user_id),
                ('full_name', full_name),
                ('experience_level', 'entry'),
                ('is_profile_complete', 0),
            ]:
                if col in js_cols:
                    insert_cols.append(col)
                    insert_vals.append(val)
            if not insert_cols:
                return jsonify({'error': 'job_seekers table missing required columns'}), 500
            placeholders = ', '.join(['%s'] * len(insert_cols))
            cursor.execute(
                f"INSERT INTO job_seekers ({', '.join(insert_cols)}) VALUES ({placeholders})",
                tuple(insert_vals)
            )
            conn.commit()
            # fetch again to get the inserted row (including auto id)
            cursor.execute(f"SELECT * FROM job_seekers WHERE user_id = %s LIMIT 1", (current_user_id,))
            js_row = cursor.fetchone()
            if not js_row:
                return jsonify({'error': 'Job seeker profile not found'}), 404
        js_id = js_row[js_id_col]

        # Ensure job exists
        cursor.execute("SELECT * FROM jobs WHERE id = %s LIMIT 1", (job_id,))
        job_row = cursor.fetchone()
        if not job_row:
            return jsonify({'error': 'Job not found'}), 404

        # Require CV analysis and role alignment before applying
        def norm_title(val):
            if not val:
                return ""
            cleaned = "".join(str(val).lower().strip().split())
            # strip common punctuation
            for ch in ["-", "_", ".", ","]:
                cleaned = cleaned.replace(ch, "")
            return cleaned

        if not table_exists(conn, 'cv_analysis'):
            return jsonify({'error': 'Please upload and analyze your CV before applying.'}), 400

        cursor.execute(
            """
            SELECT predicted_job_role, ai_prediction
            FROM cv_analysis
            WHERE job_seeker_id = %s
            ORDER BY analysis_date DESC, id DESC
            LIMIT 1
            """,
            (js_id,)
        )
        cv_guard = cursor.fetchone()
        if not cv_guard:
            # Fallback: some schemas store user_id in job_seeker_id
            cursor.execute(
                """
                SELECT predicted_job_role, ai_prediction
                FROM cv_analysis
                WHERE job_seeker_id = %s
                ORDER BY analysis_date DESC, id DESC
                LIMIT 1
                """,
                (current_user_id,)
            )
            cv_guard = cursor.fetchone()
        if not cv_guard:
            return jsonify({'error': 'Please upload and analyze your CV before applying.'}), 400
        # Gather predicted role and alternatives from multiple sources
        predicted_role_guard = cv_guard.get('predicted_job_role')
        alt_roles = []
        if cv_guard.get('ai_prediction'):
            try:
                ai_pred = cv_guard.get('ai_prediction')
                if isinstance(ai_pred, str):
                    ai_pred = json.loads(ai_pred)
                if isinstance(ai_pred, dict):
                    pred_job_role_val = ai_pred.get('predicted_job_role') or ai_pred.get('job_role')
                    if pred_job_role_val and not predicted_role_guard:
                        predicted_role_guard = pred_job_role_val
                    top_from_ai = ai_pred.get('top_job_roles')
                    if isinstance(top_from_ai, (list, tuple)):
                        alt_roles.extend(top_from_ai)
            except Exception:
                pass
        if not predicted_role_guard:
            predicted_role_guard = js_row.get('predicted_job_role') or js_row.get('ai_job_role') or js_row.get('target_role')

        top_roles_raw = cv_guard.get('top_job_roles')
        if isinstance(top_roles_raw, str):
            try:
                parsed_top = json.loads(top_roles_raw)
            except Exception:
                parsed_top = []
        else:
            parsed_top = top_roles_raw if isinstance(top_roles_raw, (list, tuple)) else []
        if parsed_top:
            alt_roles.extend(parsed_top)

        def _extract_role_title(source):
            if not source:
                return None
            if isinstance(source, str):
                return source
            if isinstance(source, dict):
                return source.get('title') or source.get('role') or source.get('name')
            return str(source)

        allowed_roles = []
        candidate_primary = _extract_role_title(predicted_role_guard)
        if candidate_primary:
            allowed_roles.append(candidate_primary)
        for alt in alt_roles:
            alt_title = _extract_role_title(alt)
            if alt_title:
                allowed_roles.append(alt_title)

        # Normalize job title with fallback to department if title missing
        job_title_guard = job_row.get('title') or job_row.get('department') or job_row.get('job_title')
        # If we still don't have a predicted role but have a job title, allow it to serve as guard to avoid false negatives
        if not predicted_role_guard and job_title_guard:
            predicted_role_guard = job_title_guard
        if not predicted_role_guard or not job_title_guard:
            app.logger.info("Apply guard blocked: predicted_role=%s job_title=%s cv_guard=%s js_row=%s",
                            predicted_role_guard, job_title_guard, cv_guard, js_row)
            return jsonify({'error': f'Your CV must have a predicted role to apply for jobs (found role="{predicted_role_guard}", job title="{job_title_guard}").'}), 400

        job_norm = norm_title(job_title_guard)
        allowed_norms = {norm_title(role) for role in allowed_roles if role}
        if not allowed_norms:
            allowed_norms.add(job_norm)
        if not allowed_roles:
            allowed_roles.append(job_title_guard)
        if job_norm not in allowed_norms:
            allowed_list = ", ".join(sorted({r for r in allowed_roles if r}))
            display_role = candidate_primary or (allowed_list.split(",")[0] if allowed_list else job_title_guard)
            msg = f"You can only apply to roles matching your OCR predictions ({allowed_list or display_role})."
            return jsonify({'error': msg}), 400

        app_cols = get_table_columns(conn, 'job_applications') or set()
        if not app_cols:
            return jsonify({'error': 'job_applications table not found'}), 500

        # choose a fk column that exists
        js_fk = None
        for candidate in ['job_seeker_id', 'seeker_id', 'user_id', 'applicant_id']:
            if candidate in app_cols:
                js_fk = candidate
                break
        if not js_fk:
            return jsonify({'error': 'job_applications missing job seeker reference column'}), 500

        status_col = 'application_status' if 'application_status' in app_cols else ('status' if 'status' in app_cols else None)
        created_col = 'created_at' if 'created_at' in app_cols else None
        updated_col = 'updated_at' if 'updated_at' in app_cols else None
        applied_col = 'applied_at' if 'applied_at' in app_cols else None
        status_updated_col = 'status_updated_at' if 'status_updated_at' in app_cols else None
        match_col = 'match_score' if 'match_score' in app_cols else None
        resume_col = 'resume_url' if 'resume_url' in app_cols else None
        cover_col = 'cover_letter' if 'cover_letter' in app_cols else None
        notes_col = 'notes' if 'notes' in app_cols else None
        ai_col = 'ai_analysis' if 'ai_analysis' in app_cols else None

        # Prevent duplicate application (return existing status)
        cursor.execute(
            f"SELECT id, {status_col} FROM job_applications WHERE job_id = %s AND {js_fk} = %s LIMIT 1",
            (job_id, js_id if js_fk == 'job_seeker_id' else current_user_id)
        )
        dup = cursor.fetchone()
        if dup:
            return jsonify({
                'message': 'Already applied',
                'application_id': dup.get('id'),
                'status': dup.get(status_col) if status_col else None
            }), 200

        # Pull optional resume/match/ai data from job_seeker and cv_analysis (snapshot at apply time)
        resume_val = payload.get('resume_url') or js_row.get('resume_url')
        cover_val = payload.get('cover_letter')
        match_val = payload.get('match_score') or js_row.get('match_score')
        notes_val = js_row.get('predicted_job_role') or None
        ai_val = payload.get('ai_analysis')

        cv_cols = get_table_columns(conn, 'cv_analysis') or set()
        cv_snapshot = None
        if cv_cols:
            cursor.execute(
                """
                SELECT predicted_job_role, match_score, ai_prediction, analysis_data, skills_detected, cv_file_url,
                       predicted_salary, predicted_experience_years
                FROM cv_analysis
                WHERE job_seeker_id = %s
                ORDER BY analysis_date DESC, id DESC
                LIMIT 1
                """,
                (js_id,)
            )
            cv = cursor.fetchone()
            if cv:
                cv_snapshot = cv
                if match_val is None:
                    match_val = cv.get('match_score')
                if not notes_val:
                    notes_val = cv.get('predicted_job_role')
                if cv.get('cv_file_url'):
                    resume_val = cv.get('cv_file_url')
                if not ai_val:
                    # Prefer stored ai_prediction if valid, else build a compact payload
                    raw_ai = cv.get('ai_prediction')
                    try:
                        if raw_ai:
                            ai_val = raw_ai if isinstance(raw_ai, str) else json.dumps(raw_ai)
                        else:
                            ai_val = json.dumps({
                                'predicted_job_role': cv.get('predicted_job_role'),
                                'match_score': cv.get('match_score'),
                                'predicted_salary': cv.get('predicted_salary'),
                                'predicted_experience_years': cv.get('predicted_experience_years'),
                                'analysis_data': cv.get('analysis_data'),
                                'skills_detected': cv.get('skills_detected'),
                                'cv_file_url': cv.get('cv_file_url')
                            })
                    except Exception:
                        ai_val = None
                # Derive match score from AI payload if still missing
                if match_val is None:
                    try:
                        ai_prediction = None
                        if ai_val:
                            ai_prediction = json.loads(ai_val)
                        elif cv.get('ai_prediction'):
                            ai_prediction = json.loads(cv.get('ai_prediction')) if isinstance(cv.get('ai_prediction'), str) else cv.get('ai_prediction')
                        skills_detected = None
                        raw_skills = cv.get('skills_detected')
                        if isinstance(raw_skills, str):
                            try:
                                skills_detected = json.loads(raw_skills)
                            except Exception:
                                skills_detected = None
                        match_val = compute_match_score(
                            ai_prediction or {},
                            skills_detected,
                            education_level=(ai_prediction or {}).get('education_level_predicted'),
                            candidate_experience=(ai_prediction or {}).get('experience_years')
                        )
                    except Exception:
                        match_val = None

        # Snapshot AI analysis into the application if column exists and we built one
        if not ai_val and cv_snapshot:
            try:
                ai_val = json.dumps({
                    'predicted_job_role': cv_snapshot.get('predicted_job_role'),
                    'match_score': cv_snapshot.get('match_score'),
                    'predicted_salary': cv_snapshot.get('predicted_salary'),
                    'predicted_experience_years': cv_snapshot.get('predicted_experience_years'),
                    'skills_detected': cv_snapshot.get('skills_detected'),
                    'cv_file_url': cv_snapshot.get('cv_file_url')
                })
            except Exception:
                ai_val = None

        # Ensure ai_val stored as JSON string for snapshotting
        if isinstance(ai_val, dict):
            try:
                ai_val = json.dumps(ai_val)
            except Exception:
                ai_val = None

        # Final fallbacks
        if match_val is None:
            match_val = 0

        fields = []
        values = []
        def add(col, val):
            if col and col in app_cols:
                fields.append(col)
                values.append(val)

        add('job_id', job_id)
        add(js_fk, js_id if js_fk in ('job_seeker_id','seeker_id') else current_user_id)
        add(status_col, 'applied')
        now = datetime.datetime.utcnow()
        add(created_col, now)
        add(updated_col, now)
        add(applied_col, now)
        add(status_updated_col, now)
        add(match_col, match_val)
        add(resume_col, resume_val)
        add(cover_col, cover_val)
        add(notes_col, notes_val)
        add(ai_col, ai_val)

        if match_val is None:
            match_val = 0

        if not fields or 'job_id' not in fields or js_fk not in fields:
            return jsonify({'error': 'No valid columns to insert'}), 500

        placeholders = ', '.join(['%s'] * len(fields))
        cursor.execute(
            f"INSERT INTO job_applications ({', '.join(fields)}) VALUES ({placeholders})",
            tuple(values)
        )
        conn.commit()
        return jsonify({'message': 'Application submitted', 'application_id': cursor.lastrowid}), 201
    except Exception as e:
        if conn:
            conn.rollback()
        app.logger.exception("Failed to create job application: %s", e)
        return jsonify({'error': 'Internal server error', 'detail': str(e)}), 500
    finally:
        try:
            cursor.close()
        except Exception:
            pass
        try:
            conn.close()
        except Exception:
            pass

@app.route('/api/company/messages/start', methods=['POST', 'OPTIONS'])
@token_required
def start_company_conversation(current_user_id):
    """Ensure a conversation exists between company and a job seeker, optionally send initial text."""
    conn = get_db_connection()
    if not conn:
        return jsonify({'error': 'Database connection failed'}), 500
    cursor = conn.cursor(dictionary=True)
    try:
        if request.method == 'OPTIONS':
            return jsonify({'status': 'ok'}), 200

        cursor.execute("SELECT id FROM companies WHERE user_id = %s", (current_user_id,))
        company = cursor.fetchone()
        if not company:
            return jsonify({'error': 'Company profile not found'}), 403
        company_id = company['id']

        payload = request.get_json(silent=True) or {}
        try:
            job_seeker_identifier = int(payload.get('job_seeker_id'))
        except Exception:
            return jsonify({'error': 'job_seeker_id is required'}), 400

        # Validate job seeker exists
        js_pk_col = get_job_seeker_pk_column(conn)
        if not js_pk_col:
            return jsonify({'error': 'job_seekers table missing identifier column'}), 500
        cursor.execute(
            f"SELECT {js_pk_col} AS js_pk, user_id FROM job_seekers WHERE {js_pk_col} = %s OR user_id = %s LIMIT 1",
            (job_seeker_identifier, job_seeker_identifier)
        )
        js_row = cursor.fetchone() or {}
        if not js_row:
            return jsonify({'error': 'Job seeker not found'}), 404
        job_seeker_id = js_row.get('js_pk') or js_row.get('user_id')

        # Prefer conversations table if available
        conversation_id = None
        conv_cols = get_table_columns(conn, 'conversations') or set()
        if conv_cols:
            cursor.execute(
                "SELECT id FROM conversations WHERE company_id=%s AND job_seeker_id=%s LIMIT 1",
                (company_id, job_seeker_id)
            )
            row = cursor.fetchone()
            if row and row.get('id'):
                conversation_id = row['id']
            else:
                cursor.execute(
                    "INSERT INTO conversations (company_id, job_seeker_id, created_at) VALUES (%s, %s, %s)",
                    (company_id, job_seeker_id, datetime.datetime.utcnow())
                )
                conversation_id = cursor.lastrowid
                conn.commit()
        else:
            cursor.execute(
                "SELECT conversation_id FROM messages WHERE (sender_type='company' AND sender_id=%s) OR (sender_type='job_seeker' AND sender_id=%s) ORDER BY conversation_id ASC LIMIT 1",
                (company_id, job_seeker_id)
            )
            row = cursor.fetchone()
            conversation_id = row['conversation_id'] if row else None
            if not conversation_id:
                cursor.execute("SELECT COALESCE(MAX(conversation_id), 0) + 1 AS next_id FROM messages")
                row = cursor.fetchone()
                conversation_id = row['next_id'] if row and row.get('next_id') else 1

        initial_text = payload.get('message_text')
        if not initial_text:
            initial_text = "Hello, we'd like to start a conversation."

        msg_cols = get_table_columns(conn, 'messages') or set()
        if not msg_cols:
            return jsonify({'error': 'messages table missing or inaccessible'}), 500

        insert_cols = []
        insert_vals = []
        def add(col, val):
            if col in msg_cols:
                insert_cols.append(col)
                insert_vals.append(val)
        add('conversation_id', conversation_id)
        add('sender_type', 'company')
        add('sender_id', company_id)
        add('message_text', initial_text)
        add('message_type', payload.get('message_type') or 'text')
        add('file_url', payload.get('file_url'))
        add('file_name', payload.get('file_name'))
        add('file_size', payload.get('file_size'))
        add('is_read', 0)
        if 'created_at' in msg_cols:
            add('created_at', datetime.datetime.utcnow())

        if not insert_cols or 'conversation_id' not in insert_cols or 'sender_type' not in insert_cols or 'sender_id' not in insert_cols:
            return jsonify({'error': 'messages table missing required columns'}), 500

        placeholders = ', '.join(['%s'] * len(insert_cols))
        cursor.execute(
            f"INSERT INTO messages ({', '.join(insert_cols)}) VALUES ({placeholders})",
            tuple(insert_vals)
        )
        # Update conversation metadata for both inboxes
        conv_cols = get_table_columns(conn, 'conversations') or set()
        if conv_cols and 'id' in conv_cols:
            set_parts = []
            vals = []
            if 'last_message_text' in conv_cols:
                set_parts.append("last_message_text = %s")
                vals.append(initial_text)
            if 'last_message_at' in conv_cols:
                set_parts.append("last_message_at = %s")
                vals.append(datetime.datetime.utcnow())
            if 'unread_count_seeker' in conv_cols:
                set_parts.append("unread_count_seeker = COALESCE(unread_count_seeker,0) + 1")
            if set_parts:
                vals.append(conversation_id)
                cursor.execute(
                    f"UPDATE conversations SET {', '.join(set_parts)} WHERE id = %s",
                    tuple(vals)
                )
        conn.commit()

        return jsonify({'conversation_id': conversation_id}), 200
    except Exception as e:
        if conn:
            conn.rollback()
        app.logger.exception("Failed to start conversation: %s", e)
        return jsonify({'error': 'Internal server error', 'detail': str(e)}), 500
    finally:
        try:
            cursor.close()
        except Exception:
            pass
        try:
            conn.close()
        except Exception:
            pass

@app.route('/api/company/analytics', methods=['GET'])
@token_required
def company_analytics(current_user_id):
    """
    Returns basic analytics for the company:
    - metrics: open_roles, applications, interviews, hires
    - applications_trend: list of counts over last 14 days
    - top_roles: [{title, count}]
    - funnel: applied, interview, offer, hired
    - recent_activity: last 5 application events
    """
    conn = get_db_connection()
    if not conn:
        return jsonify({'error': 'Database connection failed'}), 500
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT id FROM companies WHERE user_id = %s", (current_user_id,))
        company = cursor.fetchone()
        if not company:
            return jsonify({'error': 'Company profile not found'}), 403
        company_id = company['id']

        jobs_cols = get_table_columns(conn, 'jobs') or set()
        apps_cols = get_table_columns(conn, 'job_applications') or set()

        # Open roles
        open_roles = 0
        if 'id' in jobs_cols and 'company_id' in jobs_cols:
            where_status = ""
            params = [company_id]
            if 'status' in jobs_cols:
                where_status = " AND status = 'active'"
            cursor.execute(
                f"SELECT COUNT(*) as cnt FROM jobs WHERE company_id = %s{where_status}",
                tuple(params)
            )
            row = cursor.fetchone() or {}
            open_roles = row.get('cnt', 0) or 0

        # Applications total
        total_apps = 0
        if {'job_id', 'id'}.issubset(apps_cols) and 'company_id' in jobs_cols:
            cursor.execute(
                """
                SELECT COUNT(*) as cnt
                FROM job_applications ja
                JOIN jobs j ON ja.job_id = j.id
                WHERE j.company_id = %s
                """,
                (company_id,)
            )
            row = cursor.fetchone() or {}
            total_apps = row.get('cnt', 0) or 0

        # Simple funnel placeholders
        funnel = {'applied': total_apps, 'interview': 0, 'offer': 0, 'hired': 0}

        # Applications trend (last 14 days)
        trend = []
        if {'job_id', 'id'}.issubset(apps_cols) and 'company_id' in jobs_cols:
            cursor.execute(
                """
                SELECT DATE(ja.created_at) as d, COUNT(*) as c
                FROM job_applications ja
                JOIN jobs j ON ja.job_id = j.id
                WHERE j.company_id = %s AND ja.created_at >= DATE_SUB(CURDATE(), INTERVAL 14 DAY)
                GROUP BY DATE(ja.created_at)
                ORDER BY d ASC
                """,
                (company_id,)
            )
            rows = cursor.fetchall() or []
            trend_map = {str(r['d']): r['c'] for r in rows if r.get('d')}
            import datetime as dt
            today = dt.date.today()
            for i in range(14):
                day = today - dt.timedelta(days=13 - i)
                trend.append(trend_map.get(str(day), 0))

        # Top roles by applications
        top_roles = []
        if {'job_id', 'id'}.issubset(apps_cols) and {'company_id', 'title', 'id'}.issubset(jobs_cols):
            cursor.execute(
                """
                SELECT j.title, COUNT(*) as cnt
                FROM job_applications ja
                JOIN jobs j ON ja.job_id = j.id
                WHERE j.company_id = %s
                GROUP BY j.title
                ORDER BY cnt DESC
                LIMIT 6
                """,
                (company_id,)
            )
            rows = cursor.fetchall() or []
            for r in rows:
                top_roles.append({'title': r.get('title') or 'Role', 'count': r.get('cnt', 0) or 0})

        # Recent activity (applications)
        recent_activity = []
        if {'job_id', 'id'}.issubset(apps_cols) and {'company_id', 'title', 'id'}.issubset(jobs_cols):
            date_col = 'created_at' if 'created_at' in apps_cols else 'id'
            cursor.execute(
                f"""
                SELECT ja.id, ja.{date_col} as created_at, j.title
                FROM job_applications ja
                JOIN jobs j ON ja.job_id = j.id
                WHERE j.company_id = %s
                ORDER BY ja.{date_col} DESC
                LIMIT 5
                """,
                (company_id,)
            )
            rows = cursor.fetchall() or []
            for r in rows:
                recent_activity.append({
                    'title': r.get('title') or 'Application',
                    'sub': f"Application #{r.get('id')}",
                    'time': str(r.get('created_at') or '')
                })

        metrics = {
            'open_roles': open_roles,
            'applications': total_apps,
            'interviews': 0,
            'hires': 0
        }

        return jsonify({
            'metrics': metrics,
            'applications_trend': trend,
            'top_roles': top_roles,
            'funnel': funnel,
            'recent_activity': recent_activity
        }), 200
    except Exception as e:
        app.logger.exception("Failed to load analytics: %s", e)
        return jsonify({'error': 'Internal server error', 'detail': str(e)}), 500
    finally:
        try:
            cursor.close()
        except Exception:
            pass
        try:
            conn.close()
        except Exception:
            pass

@app.route('/api/job-seeker/analytics', methods=['GET'])
@token_required
def job_seeker_analytics(current_user_id):
    """
    Returns analytics for a job seeker:
    - metrics: applications, interviews (scheduled/in_progress), offers, hires
    - applications_trend: counts over last 14 days
    - top_roles: jobs applied to (by title)
    - recent_activity: last 5 application events
    """
    conn = get_db_connection()
    if not conn:
        return jsonify({'error': 'Database connection failed'}), 500
    cursor = conn.cursor(dictionary=True)
    try:
        profile = fetch_job_seeker_profile(conn, current_user_id)
        if not profile:
            return jsonify({'error': 'Job seeker profile not found'}), 404
        js_id = profile.get('id')

        app_cols = get_table_columns(conn, 'job_applications') or set()
        job_cols = get_table_columns(conn, 'jobs') or set()

        js_fk = pick_first_column(app_cols, ['job_seeker_id', 'seeker_id', 'user_id'])
        if not js_fk:
            return jsonify({'metrics': {}, 'applications_trend': [], 'top_roles': [], 'recent_activity': []}), 200

        # Basic counts
        total_apps = interviews_cnt = offers_cnt = hires_cnt = 0
        status_col = pick_first_column(app_cols, ['application_status', 'status'])
        if status_col:
            cursor.execute(
                f"""
                SELECT {status_col} as st, COUNT(*) as c
                FROM job_applications
                WHERE {js_fk} = %s
                GROUP BY {status_col}
                """,
                (js_id if js_fk == 'job_seeker_id' else current_user_id,)
            )
            for row in cursor.fetchall() or []:
                st = (row.get('st') or '').lower()
                c = row.get('c') or 0
                total_apps += c
                if 'interview' in st:
                    interviews_cnt += c
                if 'offer' in st:
                    offers_cnt += c
                if 'hire' in st:
                    hires_cnt += c

        # Trend last 14 days
        trend = []
        date_col = 'created_at' if 'created_at' in app_cols else None
        if date_col:
            cursor.execute(
                f"""
                SELECT DATE({date_col}) as d, COUNT(*) as c
                FROM job_applications
                WHERE {js_fk} = %s AND {date_col} >= DATE_SUB(CURDATE(), INTERVAL 14 DAY)
                GROUP BY DATE({date_col})
                ORDER BY d ASC
                """,
                (js_id if js_fk == 'job_seeker_id' else current_user_id,)
            )
            rows = cursor.fetchall() or []
            trend_map = {str(r['d']): r['c'] for r in rows if r.get('d')}
            import datetime as dt
            today = dt.date.today()
            for i in range(14):
                day = today - dt.timedelta(days=13 - i)
                trend.append(trend_map.get(str(day), 0))

        # Top roles applied
        top_roles = []
        if {'job_id', 'id'}.issubset(app_cols) and 'title' in job_cols:
            cursor.execute(
                f"""
                SELECT j.title, COUNT(*) as cnt
                FROM job_applications ja
                JOIN jobs j ON ja.job_id = j.id
                WHERE ja.{js_fk} = %s
                GROUP BY j.title
                ORDER BY cnt DESC
                LIMIT 6
                """,
                (js_id if js_fk == 'job_seeker_id' else current_user_id,)
            )
            for r in cursor.fetchall() or []:
                top_roles.append({'title': r.get('title') or 'Role', 'count': r.get('cnt', 0) or 0})

        # Recent activity
        recent_activity = []
        if {'job_id', 'id'}.issubset(app_cols):
            date_col_ra = date_col or 'id'
            cursor.execute(
                f"""
                SELECT ja.id, ja.{date_col_ra} as created_at, j.title, ja.{status_col} as st
                FROM job_applications ja
                LEFT JOIN jobs j ON ja.job_id = j.id
                WHERE ja.{js_fk} = %s
                ORDER BY ja.{date_col_ra} DESC
                LIMIT 5
                """,
                (js_id if js_fk == 'job_seeker_id' else current_user_id,)
            )
            for r in cursor.fetchall() or []:
                recent_activity.append({
                    'title': r.get('title') or 'Application',
                    'sub': (r.get('st') or '').title() or 'Status update',
                    'time': str(r.get('created_at') or '')
                })

        metrics = {
            'applications': total_apps,
            'interviews': interviews_cnt,
            'offers': offers_cnt,
            'hires': hires_cnt
        }

        return jsonify({
            'metrics': metrics,
            'applications_trend': trend,
            'top_roles': top_roles,
            'recent_activity': recent_activity
        }), 200
    except Exception as e:
        app.logger.exception("Failed to load job seeker analytics: %s", e)
        return jsonify({'error': 'Internal server error', 'detail': str(e)}), 500
    finally:
        try:
            cursor.close()
        except Exception:
            pass
        try:
            conn.close()
        except Exception:
            pass

# ============ COMPANY APPLICATIONS ============
@app.route('/api/company/applications', methods=['GET'])
@token_required
def company_applications(current_user_id):
    conn = get_db_connection()
    if not conn:
        return jsonify({'error': 'Database connection failed'}), 500
    cursor = conn.cursor(dictionary=True)
    try:
        # Allow explicit company_id override (for team accounts or fallback cases)
        company_override = request.args.get('company_id', type=int)

        cursor.execute("SELECT id FROM companies WHERE user_id = %s", (current_user_id,))
        company = cursor.fetchone()
        company_id = company_override or (company['id'] if company else None)

        job_cols = get_table_columns(conn, 'jobs') or set()
        ensure_application_snapshot_columns(conn)
        app_cols = get_table_columns(conn, 'job_applications') or set()
        js_cols = get_table_columns(conn, 'job_seekers') or set()
        cv_cols = get_table_columns(conn, 'cv_analysis') or set()

        if not app_cols or not job_cols:
            return jsonify({'applications': []})

        js_fk = 'job_seeker_id' if 'job_seeker_id' in app_cols else ('user_id' if 'user_id' in app_cols else None)
        status_col = 'application_status' if 'application_status' in app_cols else ('status' if 'status' in app_cols else None)
        match_col = 'match_score' if 'match_score' in app_cols else None
        applied_col = 'created_at' if 'created_at' in app_cols else None
        interview_score_col = 'interview_score' if 'interview_score' in app_cols else None
        schedule_col = pick_first_column(app_cols, ['schedule_date', 'interview_date', 'interview_at', 'interview_time'])
        meeting_col = pick_first_column(app_cols, ['meeting_url', 'join_url', 'virtual_meeting_url', 'meeting_link'])
        resume_col = 'resume_url' if 'resume_url' in app_cols else None
        notes_col = 'notes' if 'notes' in app_cols else None
        ai_col = 'ai_analysis' if 'ai_analysis' in app_cols else None
        applied_full_name_col = 'applied_full_name' if 'applied_full_name' in app_cols else None
        applied_email_col = 'applied_email' if 'applied_email' in app_cols else None
        applied_phone_col = 'applied_phone' if 'applied_phone' in app_cols else None
        applied_job_title_col = 'applied_job_title' if 'applied_job_title' in app_cols else None
        applied_job_location_col = 'applied_job_location' if 'applied_job_location' in app_cols else None
        applied_predicted_role_col = 'applied_predicted_role' if 'applied_predicted_role' in app_cols else None
        applied_resume_col = 'applied_resume_url' if 'applied_resume_url' in app_cols else None

        select_app_cols = ['ja.id as app_id', 'ja.job_id']
        if js_fk:
            select_app_cols.append(f"ja.{js_fk} as js_id")
        if status_col:
            select_app_cols.append(f"ja.{status_col} as app_status")
        if match_col:
            select_app_cols.append(f"ja.{match_col} as applied_match_score")
        if applied_col:
            select_app_cols.append(f"ja.{applied_col} as applied_at")
        if interview_score_col:
            select_app_cols.append(f"ja.{interview_score_col} as interview_score")
        if schedule_col:
            select_app_cols.append(f"ja.{schedule_col} as scheduled_at")
        if meeting_col:
            select_app_cols.append(f"ja.{meeting_col} as meeting_url")
        if resume_col:
            select_app_cols.append(f"ja.{resume_col} as resume_url")
        if notes_col:
            select_app_cols.append(f"ja.{notes_col} as notes")
        if ai_col:
            select_app_cols.append(f"ja.{ai_col} as ai_analysis")
        if applied_full_name_col:
            select_app_cols.append(f"ja.{applied_full_name_col} as applied_full_name")
        if applied_email_col:
            select_app_cols.append(f"ja.{applied_email_col} as applied_email")
        if applied_phone_col:
            select_app_cols.append(f"ja.{applied_phone_col} as applied_phone")
        if applied_job_title_col:
            select_app_cols.append(f"ja.{applied_job_title_col} as applied_job_title")
        if applied_job_location_col:
            select_app_cols.append(f"ja.{applied_job_location_col} as applied_job_location")
        if applied_predicted_role_col:
            select_app_cols.append(f"ja.{applied_predicted_role_col} as applied_predicted_role")
        if applied_resume_col:
            select_app_cols.append(f"ja.{applied_resume_col} as applied_resume_url")

        select_job_cols = []
        for col in ['title', 'department', 'location']:
            if col in job_cols:
                select_job_cols.append(f"j.{col}")

        # Fetch applications, optionally scoped to a specific company_id
        base_select = f"""
            SELECT {', '.join(select_app_cols + select_job_cols)}
            FROM job_applications ja
            JOIN jobs j ON ja.job_id = j.id
        """
        params = []
        if company_id:
            sql = base_select + " WHERE j.company_id = %s ORDER BY ja.id DESC"
            params.append(company_id)
        else:
            sql = base_select + " ORDER BY ja.id DESC"

        cursor.execute(sql, tuple(params) if params else ())
        rows = cursor.fetchall() or []

        # Load latest interview records for these applications (if table exists)
        interviews_map = {}
        app_ids = [r.get('app_id') for r in rows if r.get('app_id')]
        interview_cols = get_table_columns(conn, 'interviews') or set()
        if app_ids and interview_cols and 'application_id' in interview_cols:
            placeholders = ','.join(['%s'] * len(app_ids))
            try:
                cursor.execute(
                    f"""
                    SELECT i.*
                    FROM interviews i
                    JOIN (
                        SELECT application_id, MAX(id) AS latest_id
                        FROM interviews
                        WHERE application_id IN ({placeholders})
                        GROUP BY application_id
                    ) li ON i.id = li.latest_id
                    """,
                    tuple(app_ids)
                )
                for iv in cursor.fetchall() or []:
                    interviews_map[iv.get('application_id')] = iv
            except Exception:
                app.logger.exception("Failed to fetch interviews for company applications")

        int_sched_col = pick_first_column(interview_cols, ['scheduled_date', 'interview_at', 'interview_time'])
        int_meeting_col = pick_first_column(interview_cols, ['meeting_url', 'join_url', 'virtual_meeting_url', 'meeting_link'])
        int_status_col = 'status' if 'status' in interview_cols else None
        int_feedback_col = 'feedback' if 'feedback' in interview_cols else None
        int_notes_col = 'notes' if 'notes' in interview_cols else None
        int_rating_col = 'rating' if 'rating' in interview_cols else None

        applications = []
        for r in rows:
            js_id_val = r.get('js_id')
            seeker = {}
            skills_list = []
            seeker_pk = js_id_val
            resume_candidate = None
            if js_id_val and js_cols:
                # choose lookup column based on how applications stores the seeker reference
                lookup_col = None
                if js_fk in ('job_seeker_id', 'seeker_id', 'candidate_id') and js_fk in js_cols:
                    lookup_col = js_fk
                elif 'user_id' in js_cols:
                    lookup_col = 'user_id'
                elif 'id' in js_cols:
                    lookup_col = 'id'
                if lookup_col:
                    cursor.execute(
                        f"SELECT * FROM job_seekers WHERE {lookup_col} = %s LIMIT 1",
                        (js_id_val,)
                    )
                    seeker = serialize_job_seeker_profile(cursor.fetchone() or {})
                    seeker_pk = seeker.get('id') or seeker.get('job_seeker_id') or js_id_val
                # Always refresh name/email from users to reflect the actual account
                try:
                    cursor.execute("SELECT name, email FROM users WHERE id = %s", (seeker.get('user_id') or js_id_val,))
                    urow = cursor.fetchone() or {}
                    # Prefer job_seeker.full_name if present; otherwise use user.name/email
                    seeker['full_name'] = seeker.get('full_name') or urow.get('name') or urow.get('email')
                    seeker['email'] = seeker.get('email') or urow.get('email')
                except Exception:
                    pass
                # skills
                skill_cols = get_table_columns(conn, 'job_seeker_skills') or set()
                if skill_cols:
                    fk_col = pick_first_column(skill_cols, ['job_seeker_id', 'seeker_id', 'user_id', 'candidate_id'])
                    name_col = pick_first_column(skill_cols, ['skill_name', 'name', 'skill'])
                    prof_col = pick_first_column(skill_cols, ['proficiency_level', 'level'])
                    if fk_col and name_col:
                        # pick a fk value that matches the skills table column
                        if fk_col == js_fk:
                            fk_val = js_id_val
                        elif fk_col == 'user_id':
                            fk_val = seeker.get('user_id') or js_id_val
                        else:
                            fk_val = seeker_pk
                        try:
                            cursor.execute(
                                f"SELECT {name_col} as skill_name{(', ' + prof_col + ' as proficiency_level') if prof_col else ''} FROM job_seeker_skills WHERE {fk_col} = %s",
                                (fk_val,)
                            )
                            skills_list = cursor.fetchall() or []
                        except Exception:
                            skills_list = []

            predicted_role = None
            predicted_salary_val = None
            predicted_exp_val = None
            cv_match = None
            cvrow = None
            if cv_cols and js_id_val:
                cursor.execute(
                    """
                    SELECT predicted_job_role, match_score, skills_detected, cv_file_url, ai_prediction, predicted_salary, predicted_experience_years
                    FROM cv_analysis
                    WHERE job_seeker_id = %s
                    ORDER BY analysis_date DESC, id DESC
                    LIMIT 1
                    """,
                    (seeker_pk,)
                )
                cvrow = cursor.fetchone()
                # Fallback: some rows may store user_id instead of seeker_pk
                if not cvrow and seeker.get('user_id'):
                    cursor.execute(
                        """
                        SELECT predicted_job_role, match_score, skills_detected, cv_file_url, ai_prediction, predicted_salary, predicted_experience_years
                        FROM cv_analysis
                        WHERE job_seeker_id = %s
                        ORDER BY analysis_date DESC, id DESC
                        LIMIT 1
                        """,
                        (seeker.get('user_id'),)
                    )
                    cvrow = cursor.fetchone()

            # Prefer AI analysis stored on the application itself, if present
            app_ai = None
            if ai_col and r.get('ai_analysis'):
                try:
                    app_ai = r.get('ai_analysis')
                    if isinstance(app_ai, str):
                        app_ai = json.loads(app_ai)
                    if isinstance(app_ai, dict):
                        if app_ai.get('predicted_job_role') or app_ai.get('job_role'):
                            predicted_role = app_ai.get('predicted_job_role') or app_ai.get('job_role')
                        if app_ai.get('match_score') is not None:
                            cv_match = app_ai.get('match_score')
                        if app_ai.get('predicted_salary') is not None:
                            predicted_salary_val = app_ai.get('predicted_salary')
                        if app_ai.get('predicted_experience_years') is not None:
                            predicted_exp_val = app_ai.get('predicted_experience_years')
                        if app_ai.get('skills_detected'):
                            skills_list = [{'skill_name': s} if isinstance(s, str) else s for s in (app_ai.get('skills_detected') or [])]
                        if app_ai.get('cv_file_url'):
                            resume_candidate = app_ai.get('cv_file_url')
                except Exception:
                    app_ai = None

            # If predicted role still missing, try notes snapshot (we store predicted role there on apply)
            if not predicted_role and notes_col and r.get('notes'):
                predicted_role = r.get('notes')

            # Fallback to latest CV analysis if app snapshot missing details
            if cvrow:
                if not predicted_role:
                    predicted_role = cvrow.get('predicted_job_role')
                if cv_match is None:
                    cv_match = cvrow.get('match_score')
                if predicted_salary_val is None:
                    predicted_salary_val = cvrow.get('predicted_salary')
                if predicted_exp_val is None:
                    predicted_exp_val = cvrow.get('predicted_experience_years')
                if not skills_list:
                    raw_skills = cvrow.get('skills_detected')
                    if isinstance(raw_skills, str):
                        try:
                            raw_skills = json.loads(raw_skills)
                        except Exception:
                            raw_skills = []
                    if isinstance(raw_skills, (list, tuple)):
                        skills_list = [{'skill_name': s} if isinstance(s, str) else s for s in raw_skills]
                if not resume_candidate and cvrow.get('cv_file_url'):
                    resume_candidate = cvrow.get('cv_file_url')

            # prefer non-zero/non-null match from application, then cv, then seeker
            app_match_val = r.get('applied_match_score')
            match_val = None
            for candidate in [app_match_val, cv_match, seeker.get('match_score')]:
                try:
                    if candidate is None:
                        continue
                    if isinstance(candidate, str):
                        candidate = float(candidate) if candidate else None
                    if candidate is None:
                        continue
                    if candidate != 0:
                        match_val = candidate
                        break
                    if match_val is None:
                        match_val = candidate
                except Exception:
                    continue

            # pick a resume url preferring seeker.resume_url, then cv file
            resume_candidate = seeker.get('resume_url')
            if not resume_candidate and cvrow and cvrow.get('cv_file_url'):
                resume_candidate = cvrow.get('cv_file_url')
            # If job applications row itself has a resume_url column, prefer that when present
            if resume_col and r.get('resume_url'):
                resume_candidate = r.get('resume_url')
            # If file does not exist, try to locate the latest CV file for this seeker/user
            def find_latest_cv(prefixes):
                try:
                    latest = None
                    for entry in os.scandir(UPLOAD_FOLDER):
                        if not entry.is_file():
                            continue
                        for pfx in prefixes:
                            if pfx and entry.name.startswith(pfx):
                                if latest is None or entry.stat().st_mtime > latest.stat().st_mtime:
                                    latest = entry
                    return latest.name if latest else None
                except Exception:
                    return None

            safe_resume = os.path.basename(resume_candidate) if resume_candidate else None
            if not safe_resume or not os.path.isfile(os.path.join(UPLOAD_FOLDER, safe_resume)):
                fallback_name = find_latest_cv([
                    f"js_{seeker_pk}_",
                    f"js_{seeker.get('user_id')}_"
                ])
                if fallback_name:
                    resume_candidate = fallback_name
            resume_url_full = build_cv_url(resume_candidate) if resume_candidate else None

            iv = interviews_map.get(r.get('app_id')) or {}
            iv_sched = iv.get(int_sched_col) if int_sched_col else None
            iv_meeting = iv.get(int_meeting_col) if int_meeting_col else None
            iv_status = iv.get(int_status_col) if int_status_col else None
            iv_feedback = iv.get(int_feedback_col) if int_feedback_col else None
            iv_notes = iv.get(int_notes_col) if int_notes_col else None
            iv_rating = iv.get(int_rating_col) if int_rating_col else None

            applications.append({
                'id': r.get('app_id'),
                'job_id': r.get('job_id'),
                'job_title': r.get('title') or r.get('department'),
                'job_location': r.get('location'),
                'status': r.get('app_status'),
                'match_score': match_val,
                'interview_score': r.get('interview_score'),
                'applied_at': r.get('applied_at'),
                'scheduled_at': r.get('scheduled_at'),
                'meeting_url': r.get('meeting_url'),
                'interview': {
                    'scheduled_at': iv_sched,
                    'status': iv_status,
                    'meeting_url': iv_meeting,
                    'feedback': iv_feedback,
                    'notes': iv_notes,
                    'rating': iv_rating,
                },
                'applied_full_name': r.get('applied_full_name'),
                'applied_email': r.get('applied_email'),
                'applied_phone': r.get('applied_phone'),
                'applied_job_title': r.get('applied_job_title'),
                'applied_job_location': r.get('applied_job_location'),
                'applied_predicted_role': r.get('applied_predicted_role'),
                'applied_resume_url': r.get('applied_resume_url'),
                'seeker': {
                    'id': js_id_val,
                    'full_name': seeker.get('full_name'),
                    'current_title': seeker.get('current_title'),
                    'location': seeker.get('location'),
                    'experience_level': seeker.get('experience_level'),
                    'predicted_role': seeker.get('predicted_job_role') or predicted_role,
                    'predicted_salary': cvrow.get('predicted_salary') if cvrow else seeker.get('predicted_salary'),
                    'predicted_experience_years': cvrow.get('predicted_experience_years') if cvrow else seeker.get('predicted_experience_years'),
                    'ai_prediction': cvrow.get('ai_prediction') if cvrow else None,
                    'email': seeker.get('email'),
                    'phone': seeker.get('phone'),
                    'resume_url': resume_url_full or seeker.get('resume_url'),
                    'skills': skills_list or seeker.get('skills') or [],
                }
            })

        return jsonify({'applications': applications}), 200
    except Exception as e:
        app.logger.exception("Failed to load company applications: %s", e)
        return jsonify({'error': 'Internal server error', 'detail': str(e)}), 500
    finally:
        try:
            cursor.close()
        except Exception:
            pass
        try:
            conn.close()
        except Exception:
            pass

@app.route('/api/company/applications/<int:app_id>/status', methods=['PUT'])
@token_required
def update_application_status(current_user_id, app_id):
    conn = get_db_connection()
    if not conn:
        return jsonify({'error': 'Database connection failed'}), 500
    cursor = conn.cursor(dictionary=True)
    try:
        payload = request.get_json(silent=True) or {}
        new_status = payload.get('status')
        interview_score = payload.get('interview_score')
        schedule_date = payload.get('schedule_date') or payload.get('interview_date')
        meeting_url_payload = payload.get('meeting_url')
        notes_val = payload.get('notes')
        if not new_status:
            return jsonify({'error': 'status is required'}), 400

        allowed_statuses = {
            'applied', 'under_review', 'shortlisted', 'interview',
            'technical_test', 'final_round', 'offer', 'rejected', 'accepted', 'hired'
        }

        def normalize_app_status(raw_status):
            if raw_status is None:
                return None
            key = str(raw_status).strip().lower().replace(' ', '_')
            if key in allowed_statuses:
                return key
            synonyms = {
                'accept': 'accepted',
                'accepted': 'accepted',
                'interview_scheduled': 'interview',
                'schedule': 'interview',
                'scheduled': 'interview',
                'invite': 'interview',
                'decline': 'rejected',
                'declined': 'rejected',
                'reject': 'rejected',
                'offer_sent': 'offer',
                'offerletter': 'offer',
                'offer_letter': 'offer',
                'hire': 'hired',
                'selected': 'hired',
                'final': 'final_round',
                'final_stage': 'final_round',
                'shortlist': 'shortlisted',
                'shortlisting': 'shortlisted',
                'review': 'under_review',
            }
            for needle, target in synonyms.items():
                if needle in key:
                    return target
            return None

        normalized_status = normalize_app_status(new_status)
        if not normalized_status:
            return jsonify({
                'error': 'Invalid status value',
                'allowed_statuses': sorted(list(allowed_statuses))
            }), 400

        cursor.execute("SELECT id FROM companies WHERE user_id = %s", (current_user_id,))
        company = cursor.fetchone()
        if not company:
            return jsonify({'error': 'Company profile not found'}), 403
        company_id = company['id']

        app_cols = get_table_columns(conn, 'job_applications') or set()
        status_col = 'application_status' if 'application_status' in app_cols else ('status' if 'status' in app_cols else None)
        interview_col = 'interview_score' if 'interview_score' in app_cols else None
        notes_col = 'notes' if 'notes' in app_cols else None
        status_updated_col = 'status_updated_at' if 'status_updated_at' in app_cols else None
        schedule_col = pick_first_column(app_cols, ['schedule_date', 'interview_date', 'interview_at', 'interview_time'])
        applied_col = 'applied_at' if 'applied_at' in app_cols else None
        meeting_col = pick_first_column(app_cols, ['meeting_url', 'join_url', 'virtual_meeting_url', 'meeting_link'])

        if not status_col:
            return jsonify({'error': 'job_applications table missing status column'}), 500

        cursor.execute(
            f"""
            SELECT ja.id
            FROM job_applications ja
            JOIN jobs j ON ja.job_id = j.id
            WHERE ja.id = %s AND j.company_id = %s
            """,
            (app_id, company_id)
        )
        belongs = cursor.fetchone()
        if not belongs:
            app.logger.warning("Company %s attempted to update app %s but job/company mismatch; attempting direct update for visibility", company_id, app_id)

        set_parts = [f"{status_col} = %s"]
        vals = [normalized_status]
        if interview_col and interview_score is not None:
            set_parts.append(f"{interview_col} = %s")
            vals.append(interview_score)
        if notes_col and notes_val is not None:
            set_parts.append(f"{notes_col} = %s")
            vals.append(notes_val)
        if schedule_date:
            try:
                if isinstance(schedule_date, str):
                    schedule_date = datetime.datetime.fromisoformat(schedule_date.replace('Z', '+00:00'))
            except Exception:
                pass
            # If a schedule date is provided, store it in schedule column (if exists)
            if schedule_col:
                set_parts.append(f"{schedule_col} = %s")
                vals.append(schedule_date)
            # Also mirror the scheduled date into applied_at as requested
            if applied_col:
                set_parts.append(f"{applied_col} = %s")
                vals.append(schedule_date)
        if meeting_col and meeting_url_payload:
            set_parts.append(f"{meeting_col} = %s")
            vals.append(meeting_url_payload)
        if status_updated_col:
            set_parts.append(f"{status_updated_col} = %s")
            vals.append(datetime.datetime.utcnow())
        vals.append(app_id)
        cursor.execute(
            f"UPDATE job_applications SET {', '.join(set_parts)} WHERE id = %s",
            tuple(vals)
        )
        if cursor.rowcount == 0 and not belongs:
            # As a fallback, try updating with a looser check
            app.logger.warning("Fallback update for application %s without company join", app_id)
            cursor.execute(
                f"UPDATE job_applications SET {', '.join(set_parts)} WHERE id = %s",
                tuple(vals)
        )
        conn.commit()
        if cursor.rowcount == 0:
            return jsonify({'error': 'Application not found or not updated'}), 404

        # If an interviews table exists, upsert a schedule/meeting record
        interview_cols = get_table_columns(conn, 'interviews') or set()
        if interview_cols and 'application_id' in interview_cols:
            try:
                int_sched_col = pick_first_column(interview_cols, ['scheduled_date', 'interview_at', 'interview_time'])
                int_meeting_col = pick_first_column(interview_cols, ['meeting_url', 'join_url', 'virtual_meeting_url', 'meeting_link'])
                int_status_col = 'status' if 'status' in interview_cols else None
                int_notes_col = 'notes' if 'notes' in interview_cols else None
                int_type_col = 'interview_type' if 'interview_type' in interview_cols else None

                interview_status = None
                new_status_l = (normalized_status or "").lower()
                if 'complete' in new_status_l:
                    interview_status = 'completed'
                elif 'reject' in new_status_l:
                    interview_status = 'cancelled'
                elif 'accept' in new_status_l or 'interview' in new_status_l or schedule_date:
                    interview_status = 'scheduled'

                if interview_status or schedule_date or meeting_url_payload or notes_val:
                    cursor.execute(
                        """
                        SELECT id FROM interviews
                        WHERE application_id = %s
                        ORDER BY updated_at DESC, id DESC
                        LIMIT 1
                        """,
                        (app_id,)
                    )
                    existing_int = cursor.fetchone()
                    if existing_int:
                        set_parts_int = []
                        vals_int = []
                        if int_status_col and interview_status:
                            set_parts_int.append(f"{int_status_col} = %s")
                            vals_int.append(interview_status)
                        if int_sched_col and schedule_date:
                            set_parts_int.append(f"{int_sched_col} = %s")
                            vals_int.append(schedule_date)
                        if int_meeting_col and meeting_url_payload:
                            set_parts_int.append(f"{int_meeting_col} = %s")
                            vals_int.append(meeting_url_payload)
                        if int_notes_col and notes_val is not None:
                            set_parts_int.append(f"{int_notes_col} = %s")
                            vals_int.append(notes_val)
                        if set_parts_int:
                            vals_int.append(existing_int['id'])
                            cursor.execute(
                                f"UPDATE interviews SET {', '.join(set_parts_int)} WHERE id = %s",
                                tuple(vals_int)
                            )
                    else:
                        cols_int = ['application_id']
                        vals_int = [app_id]
                        placeholders_int = ['%s']
                        if int_type_col:
                            cols_int.append(int_type_col)
                            vals_int.append('video_call')
                            placeholders_int.append('%s')
                        if int_sched_col:
                            cols_int.append(int_sched_col)
                            vals_int.append(schedule_date or datetime.datetime.utcnow())
                            placeholders_int.append('%s')
                        if int_meeting_col and meeting_url_payload:
                            cols_int.append(int_meeting_col)
                            vals_int.append(meeting_url_payload)
                            placeholders_int.append('%s')
                        if int_status_col and interview_status:
                            cols_int.append(int_status_col)
                            vals_int.append(interview_status)
                            placeholders_int.append('%s')
                        if int_notes_col and notes_val is not None:
                            cols_int.append(int_notes_col)
                            vals_int.append(notes_val)
                            placeholders_int.append('%s')
                        cursor.execute(
                            f"INSERT INTO interviews ({', '.join(cols_int)}) VALUES ({', '.join(placeholders_int)})",
                            tuple(vals_int)
                        )
                    conn.commit()
            except Exception:
                conn.rollback()
                app.logger.exception("Failed to upsert interview for application %s", app_id)
                # Do not fail the main request for interview insert issues

        return jsonify({'message': 'Status updated'}), 200
    except Exception as e:
        if conn:
            conn.rollback()
        app.logger.exception("Failed to update application status: %s", e)
        return jsonify({'error': 'Internal server error', 'detail': str(e)}), 500
    finally:
        try:
            cursor.close()
        except Exception:
            pass
        try:
            conn.close()
        except Exception:
            pass
@app.route('/api/test', methods=['GET'])
def test_api(): 
    conn = get_db_connection()
    status = "Database Connected" if conn else "Database Failed"
    if conn: conn.close()
    return jsonify({'message': 'API Online', 'db_status': status})

@app.route('/api/dashboard/stats', methods=['GET'])
def dashboard_stats():
    """Return public aggregate stats for homepage counters."""
    conn = get_db_connection()
    if not conn:
        return jsonify({'error': 'Database connection failed'}), 500
    cursor = conn.cursor()

    def safe_count(table_name, where=None, params=None):
        try:
            sql = f"SELECT COUNT(*) FROM {table_name}"
            if where:
                sql += f" WHERE {where}"
            cursor.execute(sql, params or ())
            row = cursor.fetchone()
            return int(row[0]) if row else 0
        except Exception as e:
            current_app.logger.exception("Failed to count %s: %s", table_name, e)
            return 0

    try:
        stats = {
            'total_jobs': safe_count('jobs'),
            'total_companies': safe_count('companies'),
            'total_job_seekers': safe_count('job_seekers'),
            # match_accuracy intentionally omitted per request
        }

        return jsonify({'stats': stats}), 200
    finally:
        try:
            cursor.close()
        except Exception:
            pass
        try:
            conn.close()
        except Exception:
            pass

if __name__ == '__main__':
    print(" JobGenix AI Backend Running on: http://localhost:8000")
    print(" Frontend served from: /frontend folder")
    print(" API Endpoints available at: http://localhost:8000/api/*")
    app.run(debug=True, host='0.0.0.0', port=8000)
