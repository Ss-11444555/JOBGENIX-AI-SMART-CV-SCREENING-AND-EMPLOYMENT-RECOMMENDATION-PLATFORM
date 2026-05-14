import os
import sys
from flask import Flask, request, jsonify, session
from flask_cors import CORS
from flask_bcrypt import Bcrypt
import jwt
import datetime
from functools import wraps
import mysql.connector
from mysql.connector import Error
import json
from datetime import datetime, timedelta

# Ensure project root is on sys.path so NewAIPredict is importable when running from /py
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from NewAIPredict.predictor import predict_job_and_salary

app = Flask(__name__)
app.config['SECRET_KEY'] = 'm&8^VpM&!Hn44pvoaIWsJog$h#eRBZvS'
app.config['BCRYPT_LOG_ROUNDS'] = 12
CORS(app)
bcrypt = Bcrypt(app)

# Database configuration
db_config = {
    'host': 'localhost',
    'user': 'root',
    'password': '',
    'database': 'job_matching_system'
}

def get_db_connection():
    try:
        connection = mysql.connector.connect(**db_config)
        return connection
    except Error as e:
        print(f"Error connecting to MySQL: {e}")
        return None

# Authentication decorator
def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization')
        if not token:
            return jsonify({'error': 'Token is missing'}), 401
        
        try:
            # Remove 'Bearer ' prefix if present
            if token.startswith('Bearer '):
                token = token[7:]
            
            data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])
            current_user_id = data['user_id']
        except Exception as e:
            return jsonify({'error': 'Token is invalid', 'details': str(e)}), 401
        
        return f(current_user_id, *args, **kwargs)
    return decorated

# Utility functions
def generate_token(user_id):
    payload = {
        'user_id': user_id,
        'exp': datetime.utcnow() + timedelta(days=1)
    }
    return jwt.encode(payload, app.config['SECRET_KEY'], algorithm='HS256')


def extract_education_entries(text: str):
    """
    Lightweight education extractor to feed AI and cv_analysis.
    Looks for common degree/program keywords.
    """
    if not text:
        return []
    edu_keywords = [
        'bachelor', 'master', 'phd', 'associate', 'diploma', 'degree',
        'b.sc', 'b.eng', 'btech', 'm.sc', 'msc', 'mba', 'bs ', 'ms ', 'ba ', 'ma ',
        "bachelor's", "master's", 'computer science', 'information technology'
    ]
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    hits = []
    for ln in lines:
        ln_lc = ln.lower()
        if any(kw in ln_lc for kw in edu_keywords):
            hits.append(ln)
        if len(hits) >= 8:
            break
    return hits

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
        'hybrid': 'remote',  # map hybrid to remote
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
    if key in ENUM_MAPS[kind].values():
        return key
    return None

# Basic API root health check
@app.route('/api', methods=['GET'])
def api_root():
    conn = get_db_connection()
    status = "Database Connected" if conn else "Database Failed"
    if conn:
        conn.close()
    return jsonify({'message': 'API Online', 'db_status': status})

# ============ AUTHENTICATION ROUTES ============

@app.route('/api/auth/job-seeker/register', methods=['POST'])
def job_seeker_register():
    try:
        data = request.get_json()

        # Validate required fields
        required_fields = ['email', 'password', 'fullName', 'location', 'experienceLevel']
        for field in required_fields:
            if not data.get(field):
                return jsonify({'error': f'{field} is required'}), 400

        connection = get_db_connection()
        if not connection:
            return jsonify({'error': 'Database connection failed'}), 500

        cursor = connection.cursor(dictionary=True)

        # Check if user already exists
        cursor.execute("SELECT id FROM users WHERE email = %s", (data['email'],))
        if cursor.fetchone():
            cursor.close()
            connection.close()
            return jsonify({'error': 'User already exists with this email'}), 400

        # Hash password
        hashed_password = bcrypt.generate_password_hash(data['password']).decode('utf-8')

        # Start transaction
        connection.start_transaction()

        # Create user
        cursor.execute(
            "INSERT INTO users (email, password_hash, user_type) VALUES (%s, %s, 'job_seeker')",
            (data['email'], hashed_password)
        )
        user_id = cursor.lastrowid

        # Extract OCR text if provided directly; otherwise leave empty
        extracted_text = data.get('ocrText', '') or ''
        education_entries = extract_education_entries(extracted_text) if extracted_text else []

        # AI prediction (runs even if OCR text is empty, but will return None)
        ai_prediction = None
        try:
            ai_prediction = predict_job_and_salary(
                extracted_text,
                experience_level=data.get('experienceLevel'),
                education_entries=education_entries
            )
            if isinstance(ai_prediction, dict) and education_entries:
                ai_prediction.setdefault('education_detected', education_entries)
        except Exception as ai_err:
            print(f"AI prediction failed: {ai_err}")

        predicted_role = ai_prediction.get('job_role') if ai_prediction else None
        predicted_salary = ai_prediction.get('salary') if ai_prediction else None
        predicted_exp_years = ai_prediction.get('experience_years') if ai_prediction else None

        # Create job seeker profile
        cursor.execute(
            """INSERT INTO job_seekers 
            (user_id, full_name, phone, location, current_title, experience_level, bio) 
            VALUES (%s, %s, %s, %s, %s, %s, %s)""",
            (user_id, data['fullName'], data.get('phone'), data['location'], 
             data.get('currentTitle') or predicted_role, data['experienceLevel'], data.get('bio', ''))
        )
        job_seeker_id = cursor.lastrowid

        # Add skills if provided
        skills = data.get('skills', [])
        for skill in skills:
            cursor.execute(
                "INSERT INTO job_seeker_skills (job_seeker_id, skill_name) VALUES (%s, %s)",
                (job_seeker_id, skill)
            )

        # Save analysis into cv_analysis if table exists
        try:
            cursor.execute("SHOW TABLES LIKE 'cv_analysis'")
            if cursor.fetchone():
                ca_fields = ["job_seeker_id"]
                ca_values = [job_seeker_id]
                if extracted_text:
                    ca_fields.append("analysis_data")
                    ca_values.append(extracted_text[:64000])
                if predicted_role is not None:
                    ca_fields.append("predicted_job_role")
                    ca_values.append(predicted_role)
                if predicted_salary is not None:
                    ca_fields.append("predicted_salary")
                    ca_values.append(predicted_salary)
                if predicted_exp_years is not None:
                    ca_fields.append("predicted_experience_years")
                    ca_values.append(predicted_exp_years)
                if education_entries:
                    ca_fields.append("education_detected")
                    ca_values.append(json.dumps(education_entries))
                if ai_prediction is not None:
                    ca_fields.append("ai_prediction")
                    ca_values.append(json.dumps(ai_prediction))
                ca_fields.append("analysis_date")
                ca_values.append(datetime.utcnow())
                ca_fields.append("created_at")
                ca_values.append(datetime.utcnow())

                placeholders = ", ".join(["%s"] * len(ca_fields))
                cursor.execute(
                    f"INSERT INTO cv_analysis ({', '.join(ca_fields)}) VALUES ({placeholders})",
                    tuple(ca_values)
                )
        except Exception as ca_err:
            print(f"cv_analysis insert skipped/failed: {ca_err}")

        # Commit transaction
        connection.commit()

        # Generate token
        token = generate_token(user_id)

        cursor.close()
        connection.close()

        response_payload = {
            'token': token,
            'user': {
                'id': user_id,
                'email': data['email'],
                'user_type': 'job_seeker',
                'profile': {
                    'id': job_seeker_id,
                    'full_name': data['fullName'],
                    'experience_level': data['experienceLevel']
                }
            }
        }
        if ai_prediction:
            response_payload['ai_prediction'] = ai_prediction

        return jsonify(response_payload), 201

    except Exception as e:
        if connection:
            connection.rollback()
            connection.close()
        return jsonify({'error': 'Registration failed', 'details': str(e)}), 500

@app.route('/api/auth/company/register', methods=['POST'])
def company_register():
    try:
        data = request.get_json()
        
        # Validate required fields
        required_fields = ['companyName', 'companyEmail', 'industry', 'companySize', 
                          'adminName', 'adminEmail', 'password']
        for field in required_fields:
            if not data.get(field):
                return jsonify({'error': f'{field} is required'}), 400
        
        connection = get_db_connection()
        if not connection:
            return jsonify({'error': 'Database connection failed'}), 500
            
        cursor = connection.cursor(dictionary=True)
        
        # Check if company email already exists
        cursor.execute("SELECT id FROM users WHERE email = %s", (data['companyEmail'],))
        if cursor.fetchone():
            cursor.close()
            connection.close()
            return jsonify({'error': 'Company already exists with this email'}), 400
        
        # Hash password
        hashed_password = bcrypt.generate_password_hash(data['password']).decode('utf-8')
        
        # Start transaction
        connection.start_transaction()
        
        # Create user for company
        cursor.execute(
            "INSERT INTO users (email, password_hash, user_type) VALUES (%s, %s, 'company')",
            (data['companyEmail'], hashed_password)
        )
        user_id = cursor.lastrowid
        
        # Create company profile
        cursor.execute(
            """INSERT INTO companies 
            (user_id, company_name, industry, company_size, website, description, 
             contact_email, phone, address) 
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (user_id, data['companyName'], data['industry'], data['companySize'],
             data.get('website'), data.get('companyDescription'), data['companyEmail'],
             data.get('adminPhone'), data.get('address', ''))
        )
        company_id = cursor.lastrowid
        
        # Create admin team member
        cursor.execute(
            """INSERT INTO company_team_members 
            (company_id, user_id, name, email, role, joined_at) 
            VALUES (%s, %s, %s, %s, 'admin', %s)""",
            (company_id, user_id, data['adminName'], data['adminEmail'], datetime.utcnow())
        )
        
        # Commit transaction
        connection.commit()
        
        # Generate token
        token = generate_token(user_id)
        
        cursor.close()
        connection.close()
        
        return jsonify({
            'token': token,
            'user': {
                'id': user_id,
                'email': data['companyEmail'],
                'user_type': 'company',
                'company': {
                    'id': company_id,
                    'name': data['companyName'],
                    'industry': data['industry']
                }
            }
        }), 201
        
    except Exception as e:
        if connection:
            connection.rollback()
            connection.close()
        return jsonify({'error': 'Company registration failed', 'details': str(e)}), 500

@app.route('/api/auth/login', methods=['POST'])
def login():
    try:
        data = request.get_json()
        email = data.get('email')
        password = data.get('password')
        
        if not email or not password:
            return jsonify({'error': 'Email and password are required'}), 400
        
        connection = get_db_connection()
        if not connection:
            return jsonify({'error': 'Database connection failed'}), 500
            
        cursor = connection.cursor(dictionary=True)
        
        # Find user
        cursor.execute("SELECT * FROM users WHERE email = %s", (email,))
        user = cursor.fetchone()
        
        if not user or not bcrypt.check_password_hash(user['password_hash'], password):
            cursor.close()
            connection.close()
            return jsonify({'error': 'Invalid credentials'}), 401
        
        # Get user profile based on type
        if user['user_type'] == 'job_seeker':
            cursor.execute("SELECT * FROM job_seekers WHERE user_id = %s", (user['id'],))
            profile = cursor.fetchone()
        else:
            cursor.execute("""
                SELECT c.*, ct.role 
                FROM companies c 
                LEFT JOIN company_team_members ct ON c.user_id = ct.user_id 
                WHERE c.user_id = %s
            """, (user['id'],))
            profile = cursor.fetchone()
        
        # Generate token
        token = generate_token(user['id'])
        
        cursor.close()
        connection.close()
        
        response_data = {
            'token': token,
            'user': {
                'id': user['id'],
                'email': user['email'],
                'user_type': user['user_type']
            }
        }
        
        # Add profile data
        if user['user_type'] == 'job_seeker' and profile:
            response_data['user']['profile'] = profile
        elif user['user_type'] == 'company' and profile:
            response_data['user']['company'] = profile
        
        return jsonify(response_data), 200
        
    except Exception as e:
        if connection:
            connection.close()
        return jsonify({'error': 'Login failed', 'details': str(e)}), 500

# ============ COMPANY DASHBOARD ROUTES ============

@app.route('/api/company/dashboard', methods=['GET'])
@token_required
def company_dashboard(current_user_id):
    try:
        connection = get_db_connection()
        if not connection:
            return jsonify({'error': 'Database connection failed'}), 500
            
        cursor = connection.cursor(dictionary=True)
        
        # Get company ID
        cursor.execute("SELECT id FROM companies WHERE user_id = %s", (current_user_id,))
        company = cursor.fetchone()
        if not company:
            return jsonify({'error': 'Company not found'}), 404
        
        company_id = company['id']
        
        # Get company stats
        cursor.execute("""
            SELECT 
                COUNT(*) as total_jobs,
                SUM(application_count) as total_applications,
                SUM(view_count) as total_views
            FROM jobs 
            WHERE company_id = %s AND status = 'active'
        """, (company_id,))
        stats = cursor.fetchone()
        
        # Get recent jobs
        cursor.execute("""
            SELECT id, title, location, job_type, application_count, status
            FROM jobs 
            WHERE company_id = %s 
            ORDER BY created_at DESC 
            LIMIT 5
        """, (company_id,))
        recent_jobs = cursor.fetchall()
        
        # Get recent candidates
        cursor.execute("""
            SELECT 
                js.id, js.full_name, js.current_title, js.location,
                ja.application_status, ja.applied_at,
                j.title as job_title
            FROM job_applications ja
            JOIN job_seekers js ON ja.job_seeker_id = js.id
            JOIN jobs j ON ja.job_id = j.id
            WHERE j.company_id = %s
            ORDER BY ja.applied_at DESC 
            LIMIT 10
        """, (company_id,))
        recent_candidates = cursor.fetchall()
        
        cursor.close()
        connection.close()
        
        return jsonify({
            'metrics': {
                'total_jobs': stats['total_jobs'] or 0,
                'total_applications': stats['total_applications'] or 0,
                'total_views': stats['total_views'] or 0,
                'active_interviews': 0  # You can calculate this from interviews table
            },
            'recent_jobs': recent_jobs,
            'recent_candidates': recent_candidates
        }), 200
        
    except Exception as e:
        if connection:
            connection.close()
        return jsonify({'error': 'Failed to load dashboard', 'details': str(e)}), 500

# ============ JOB MANAGEMENT ROUTES ============

@app.route('/api/company/jobs', methods=['GET'])
@token_required
def get_company_jobs(current_user_id):
    try:
        # Get query parameters for filtering
        status = request.args.get('status')
        search = request.args.get('search')
        
        connection = get_db_connection()
        if not connection:
            return jsonify({'error': 'Database connection failed'}), 500
            
        cursor = connection.cursor(dictionary=True)
        
        # Get company ID
        cursor.execute("SELECT id FROM companies WHERE user_id = %s", (current_user_id,))
        company = cursor.fetchone()
        if not company:
            return jsonify({'error': 'Company not found'}), 404
        
        # Build query
        query = """
            SELECT 
                j.*,
                COUNT(ja.id) as application_count
            FROM jobs j
            LEFT JOIN job_applications ja ON j.id = ja.job_id
            WHERE j.company_id = %s
        """
        params = [company['id']]
        
        if status:
            query += " AND j.status = %s"
            params.append(status)
        
        if search:
            query += " AND j.title LIKE %s"
            params.append(f'%{search}%')
        
        query += " GROUP BY j.id ORDER BY j.created_at DESC"
        
        cursor.execute(query, params)
        jobs = cursor.fetchall()
        
        # Get skills for each job
        for job in jobs:
            cursor.execute(
                "SELECT skill_name, skill_type FROM job_skills WHERE job_id = %s",
                (job['id'],)
            )
            job['skills'] = cursor.fetchall()
        
        cursor.close()
        connection.close()
        
        return jsonify({'jobs': jobs}), 200
        
    except Exception as e:
        if connection:
            connection.close()
        return jsonify({'error': 'Failed to fetch jobs', 'details': str(e)}), 500

@app.route('/api/company/jobs', methods=['POST'])
@token_required
def create_job(current_user_id):
    try:
        data = request.get_json()
        
        # Validate required fields
        required_fields = ['title', 'description', 'location', 'jobType', 'experienceLevel']
        for field in required_fields:
            if not data.get(field):
                return jsonify({'error': f'{field} is required'}), 400
        
        connection = get_db_connection()
        if not connection:
            return jsonify({'error': 'Database connection failed'}), 500
            
        cursor = connection.cursor(dictionary=True)
        
        # Get company ID
        cursor.execute("SELECT id FROM companies WHERE user_id = %s", (current_user_id,))
        company = cursor.fetchone()
        if not company:
            return jsonify({'error': 'Company not found'}), 404
        
        # Start transaction
        connection.start_transaction()
        
        # Create job
        # Normalize enum fields to match DB schema
        job_type = normalize_enum(data.get('jobType') or data.get('type'), 'job_type')
        if not job_type:
            return jsonify({'error': 'Invalid or missing jobType'}), 400

        experience_level = normalize_enum(
            data.get('experienceLevel') or data.get('experience') or data.get('experience_level'),
            'experience_level'
        )
        if not experience_level:
            return jsonify({'error': 'Invalid or missing experienceLevel'}), 400

        education_level = normalize_enum(
            data.get('educationLevel') or data.get('education') or data.get('education_level'),
            'education_level'
        )

        cursor.execute("""
            INSERT INTO jobs 
            (company_id, title, description, requirements, job_type, location, 
             experience_level, education_level, department, salary_min, salary_max, salary_type,
             positions_available, application_deadline, status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'active')
        """, (
            company['id'], data['title'], data['description'], 
            data.get('requirements', ''), job_type, data['location'],
            experience_level, education_level, data.get('department'), data.get('salaryMin'),
            data.get('salaryMax'), data.get('salaryType', 'yearly'),
            data.get('positionsAvailable', 1), data.get('applicationDeadline')
        ))
        job_id = cursor.lastrowid
        
        # Add required skills
        required_skills = data.get('requiredSkills', [])
        for skill in required_skills:
            cursor.execute(
                "INSERT INTO job_skills (job_id, skill_name, skill_type) VALUES (%s, %s, 'required')",
                (job_id, skill)
            )
        
        # Add bonus skills
        bonus_skills = data.get('bonusSkills', [])
        for skill in bonus_skills:
            cursor.execute(
                "INSERT INTO job_skills (job_id, skill_name, skill_type) VALUES (%s, %s, 'bonus')",
                (job_id, skill)
            )
        
        # Commit transaction
        connection.commit()
        
        cursor.close()
        connection.close()
        
        return jsonify({'message': 'Job created successfully', 'job_id': job_id}), 201
        
    except Exception as e:
        if connection:
            connection.rollback()
            connection.close()
        return jsonify({'error': 'Failed to create job', 'details': str(e)}), 500

@app.route('/api/company/profile', methods=['GET'])
@token_required
def get_company_profile(current_user_id):
    conn = get_db_connection()
    if not conn:
        return jsonify({'error': 'Database connection failed'}), 500

    cursor = conn.cursor(dictionary=True)
    try:
        # Fetch the company's record
        cursor.execute("SELECT * FROM companies WHERE user_id = %s", (current_user_id,))
        company = cursor.fetchone()

        if not company:
            return jsonify({'error': 'Company profile not found'}), 404

        return jsonify({'company': company}), 200

    except Exception as e:
        return jsonify({'error': 'Failed to load company profile', 'detail': str(e)}), 500

    finally:
        cursor.close()
        conn.close()


@app.route('/api/company/profile', methods=['PUT'])
@token_required
def update_company_profile(current_user_id):
    """
    Updates the companies table for the logged-in company.
    No get_table_columns, no optional stuff.
    """
    conn = get_db_connection()
    if not conn:
        return jsonify({'error': 'Database connection failed'}), 500

    cursor = conn.cursor(dictionary=True)
    try:
        data = request.get_json(silent=True) or {}
        if not data:
            return jsonify({'error': 'Invalid or empty JSON'}), 400

        # Make sure company exists for this user
        cursor.execute(
            "SELECT id FROM companies WHERE user_id = %s",
            (current_user_id,)
        )
        company = cursor.fetchone()
        if not company:
            return jsonify({'error': 'Company profile not found'}), 404

        # Read fields from JSON (from your form)
        company_name  = data.get('company_name')  or data.get('companyName')
        industry      = data.get('industry')
        company_size  = data.get('company_size')  or data.get('companySize')
        website       = data.get('website')
        description   = data.get('description')
        contact_email = data.get('contact_email') or data.get('contactEmail')

        # Build UPDATE query
        sql = """
            UPDATE companies
            SET
                company_name  = %s,
                industry      = %s,
                company_size  = %s,
                website       = %s,
                description   = %s,
                contact_email = %s,
                updated_at    = %s
            WHERE user_id = %s
        """

        values = (
            company_name,
            industry,
            company_size,
            website,
            description,
            contact_email,
            datetime.datetime.utcnow(),
            current_user_id
        )

        cursor.execute(sql, values)
        conn.commit()

        # Return updated row
        cursor.execute(
            "SELECT * FROM companies WHERE user_id = %s",
            (current_user_id,)
        )
        updated = cursor.fetchone()

        return jsonify({
            'message': 'Company profile updated successfully',
            'company': updated
        }), 200

    except Exception as e:
        conn.rollback()
        return jsonify({'error': 'Profile update failed', 'detail': str(e)}), 500

    finally:
        cursor.close()
        conn.close()

# ============ CANDIDATE MANAGEMENT ROUTES ============

@app.route('/api/company/candidates', methods=['GET'])
@token_required
def get_company_candidates(current_user_id):
    try:
        # Get query parameters
        status = request.args.get('status')
        job_id = request.args.get('job')
        search = request.args.get('search')
        
        connection = get_db_connection()
        if not connection:
            return jsonify({'error': 'Database connection failed'}), 500
            
        cursor = connection.cursor(dictionary=True)
        
        # Get company ID
        cursor.execute("SELECT id FROM companies WHERE user_id = %s", (current_user_id,))
        company = cursor.fetchone()
        if not company:
            return jsonify({'error': 'Company not found'}), 404
        
        # Build query
        query = """
            SELECT 
                js.id, js.full_name, js.current_title, js.location, js.experience_level,
                ja.id as application_id, ja.application_status, ja.applied_at, ja.match_score,
                j.id as job_id, j.title as job_title,
                GROUP_CONCAT(DISTINCT jss.skill_name) as skills
            FROM job_applications ja
            JOIN job_seekers js ON ja.job_seeker_id = js.id
            JOIN jobs j ON ja.job_id = j.id
            LEFT JOIN job_seeker_skills jss ON js.id = jss.job_seeker_id
            WHERE j.company_id = %s
        """
        params = [company['id']]
        
        if status:
            query += " AND ja.application_status = %s"
            params.append(status)
        
        if job_id:
            query += " AND j.id = %s"
            params.append(job_id)
        
        if search:
            query += " AND (js.full_name LIKE %s OR js.current_title LIKE %s OR jss.skill_name LIKE %s)"
            params.extend([f'%{search}%', f'%{search}%', f'%{search}%'])
        
        query += " GROUP BY ja.id ORDER BY ja.applied_at DESC"
        
        cursor.execute(query, params)
        candidates = cursor.fetchall()
        
        # Process skills string to array
        for candidate in candidates:
            if candidate['skills']:
                candidate['skills'] = candidate['skills'].split(',')
            else:
                candidate['skills'] = []
        
        cursor.close()
        connection.close()
        
        return jsonify({'candidates': candidates}), 200
        
    except Exception as e:
        if connection:
            connection.close()
        return jsonify({'error': 'Failed to fetch candidates', 'details': str(e)}), 500

@app.route('/api/company/candidates/<int:candidate_id>/status', methods=['PUT'])
@token_required
def update_candidate_status(current_user_id, candidate_id):
    try:
        data = request.get_json()
        new_status = data.get('status')
        
        if not new_status:
            return jsonify({'error': 'Status is required'}), 400
        
        connection = get_db_connection()
        if not connection:
            return jsonify({'error': 'Database connection failed'}), 500
            
        cursor = connection.cursor(dictionary=True)
        
        # Verify company has access to this candidate
        cursor.execute("""
            SELECT ja.id 
            FROM job_applications ja
            JOIN jobs j ON ja.job_id = j.id
            JOIN companies c ON j.company_id = c.id
            WHERE ja.id = %s AND c.user_id = %s
        """, (candidate_id, current_user_id))
        
        application = cursor.fetchone()
        if not application:
            cursor.close()
            connection.close()
            return jsonify({'error': 'Application not found or access denied'}), 404
        
        # Update status
        cursor.execute("""
            UPDATE job_applications 
            SET application_status = %s, status_updated_at = %s
            WHERE id = %s
        """, (new_status, datetime.utcnow(), candidate_id))
        
        connection.commit()
        cursor.close()
        connection.close()
        
        return jsonify({'message': 'Candidate status updated successfully'}), 200
        
    except Exception as e:
        if connection:
            connection.rollback()
            connection.close()
        return jsonify({'error': 'Failed to update candidate status', 'details': str(e)}), 500


# ============ JOB SEEKER ROUTES ============

@app.route('/api/job-seeker/dashboard', methods=['GET'])
@token_required
def job_seeker_dashboard(current_user_id):
    try:
        connection = get_db_connection()
        if not connection:
            return jsonify({'error': 'Database connection failed'}), 500
            
        cursor = connection.cursor(dictionary=True)
        
        # Get job seeker profile
        cursor.execute("SELECT * FROM job_seekers WHERE user_id = %s", (current_user_id,))
        profile = cursor.fetchone()
        
        if not profile:
            return jsonify({'error': 'Job seeker profile not found'}), 404
        
        # Get application stats
        cursor.execute("""
            SELECT 
                COUNT(*) as total_applications,
                SUM(CASE WHEN application_status = 'applied' THEN 1 ELSE 0 END) as pending,
                SUM(CASE WHEN application_status = 'interview' THEN 1 ELSE 0 END) as interviews,
                SUM(CASE WHEN application_status = 'hired' THEN 1 ELSE 0 END) as hired
            FROM job_applications 
            WHERE job_seeker_id = %s
        """, (profile['id'],))
        stats = cursor.fetchone()
        
        # Get recent applications
        cursor.execute("""
            SELECT 
                ja.*, j.title, j.company_id, c.company_name
            FROM job_applications ja
            JOIN jobs j ON ja.job_id = j.id
            JOIN companies c ON j.company_id = c.id
            WHERE ja.job_seeker_id = %s
            ORDER BY ja.applied_at DESC 
            LIMIT 5
        """, (profile['id'],))
        recent_applications = cursor.fetchall()
        
        # Get job recommendations (simplified - in production, use AI matching)
        cursor.execute("""
            SELECT j.*, c.company_name,
                   (SELECT COUNT(*) FROM job_skills js WHERE js.job_id = j.id AND js.skill_type = 'required') as required_skills_count
            FROM jobs j
            JOIN companies c ON j.company_id = c.id
            WHERE j.status = 'active'
            ORDER BY j.created_at DESC 
            LIMIT 10
        """)
        recommended_jobs = cursor.fetchall()
        
        cursor.close()
        connection.close()
        
        return jsonify({
            'profile': profile,
            'metrics': {
                'total_applications': stats['total_applications'] or 0,
                'pending': stats['pending'] or 0,
                'interviews': stats['interviews'] or 0,
                'hired': stats['hired'] or 0
            },
            'recent_applications': recent_applications,
            'recommended_jobs': recommended_jobs
        }), 200
        
    except Exception as e:
        if connection:
            connection.close()
        return jsonify({'error': 'Failed to load dashboard', 'details': str(e)}), 500

@app.route('/api/job-seeker/jobs', methods=['GET'])
@token_required
def get_jobs_for_seeker(current_user_id):
    try:
        # Get query parameters
        search = request.args.get('search')
        job_type = request.args.get('jobType')
        location = request.args.get('location')
        
        connection = get_db_connection()
        if not connection:
            return jsonify({'error': 'Database connection failed'}), 500
            
        cursor = connection.cursor(dictionary=True)
        
        # Build query
        query = """
            SELECT 
                j.*, c.company_name, c.industry,
                (SELECT COUNT(*) FROM job_applications ja WHERE ja.job_id = j.id) as application_count
            FROM jobs j
            JOIN companies c ON j.company_id = c.id
            WHERE j.status = 'active'
        """
        params = []
        
        if search:
            query += " AND (j.title LIKE %s OR j.description LIKE %s OR c.company_name LIKE %s)"
            params.extend([f'%{search}%', f'%{search}%', f'%{search}%'])
        
        if job_type:
            query += " AND j.job_type = %s"
            params.append(job_type)
        
        if location:
            query += " AND j.location LIKE %s"
            params.append(f'%{location}%')
        
        query += " ORDER BY j.created_at DESC"
        
        cursor.execute(query, params)
        jobs = cursor.fetchall()
        
        # Get skills for each job
        for job in jobs:
            cursor.execute(
                "SELECT skill_name, skill_type FROM job_skills WHERE job_id = %s",
                (job['id'],)
            )
            job['skills'] = cursor.fetchall()
        
        cursor.close()
        connection.close()
        
        return jsonify({'jobs': jobs}), 200
        
    except Exception as e:
        if connection:
            connection.close()
        return jsonify({'error': 'Failed to fetch jobs', 'details': str(e)}), 500

@app.route('/api/job-seeker/jobs/<int:job_id>/apply', methods=['POST'])
@token_required
def apply_for_job(current_user_id, job_id):
    try:
        data = request.get_json()
        
        connection = get_db_connection()
        if not connection:
            return jsonify({'error': 'Database connection failed'}), 500
            
        cursor = connection.cursor(dictionary=True)
        
        # Get job seeker ID
        cursor.execute("SELECT id FROM job_seekers WHERE user_id = %s", (current_user_id,))
        job_seeker = cursor.fetchone()
        if not job_seeker:
            return jsonify({'error': 'Job seeker profile not found'}), 404
        
        # Check if already applied
        cursor.execute("""
            SELECT id FROM job_applications 
            WHERE job_id = %s AND job_seeker_id = %s
        """, (job_id, job_seeker['id']))
        
        if cursor.fetchone():
            cursor.close()
            connection.close()
            return jsonify({'error': 'Already applied to this job'}), 400
        
        # Create application
        cursor.execute("""
            INSERT INTO job_applications 
            (job_id, job_seeker_id, cover_letter, application_status)
            VALUES (%s, %s, %s, 'applied')
        """, (job_id, job_seeker['id'], data.get('coverLetter', '')))
        
        # Update job application count
        cursor.execute("""
            UPDATE jobs SET application_count = application_count + 1 
            WHERE id = %s
        """, (job_id,))
        
        connection.commit()
        cursor.close()
        connection.close()
        
        return jsonify({'message': 'Application submitted successfully'}), 201
        
    except Exception as e:
        if connection:
            connection.rollback()
            connection.close()
        return jsonify({'error': 'Failed to apply for job', 'details': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=False, port=5000)
