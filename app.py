import os
import re
import uuid
from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from database.database import (init_db, add_user, get_user_by_email, get_user_by_id, 
                               get_user_by_student_id, update_teacher_profile, update_profile_picture, 
                               update_student_profile, delete_user, create_class, get_teacher_classes, 
                               get_class_by_id, get_class_by_code, update_class, delete_class, 
                               get_class_students, enroll_student, is_student_enrolled, 
                               get_student_classes, leave_class, create_attendance_session, 
                               get_attendance_session, get_attendance_session_by_code, 
                               get_active_session_for_class, end_attendance_session, 
                               create_attendance_record, has_attendance_record, 
                               get_session_attendance, count_session_attendance, 
                               get_class_attendance_history, get_student_attendance,
                               get_teacher_dashboard_stats, get_student_dashboard_stats,
                               get_db_connection, upsert_face_embedding, get_all_face_embeddings,
                               mark_photo_attendance)
from functools import wraps
import qrcode
import io
import base64
from datetime import datetime, timedelta
import secrets
from flask_wtf.csrf import CSRFProtect

from dotenv import load_dotenv
load_dotenv()

app = Flask(__name__)
csrf = CSRFProtect(app)

# Phase 11.6 Production Configuration
env_debug = os.environ.get('FLASK_DEBUG', '0').lower()
app.config['DEBUG'] = env_debug in ['1', 'true']

if not app.config['DEBUG']:
    secret = os.environ.get('FLASK_SECRET_KEY')
    if not secret:
        import sys
        if 'unittest' in sys.modules or 'pytest' in sys.modules:
            secret = 'test-secret-key-for-tests'
        else:
            raise ValueError("FLASK_SECRET_KEY environment variable is required in production mode.")
    app.config['SECRET_KEY'] = secret
    app.config['SESSION_COOKIE_SECURE'] = os.environ.get('SESSION_COOKIE_SECURE', 'True').lower() in ['1', 'true']
else:
    app.config['SECRET_KEY'] = os.environ.get('FLASK_SECRET_KEY', secrets.token_hex(32))
    app.config['SESSION_COOKIE_SECURE'] = False

app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

app.config['DATABASE'] = os.environ.get('DATABASE_PATH', os.path.join(app.root_path, 'database', 'attendance.db'))

# Ensure database directory exists
db_dir = os.path.dirname(app.config['DATABASE'])
if db_dir:
    os.makedirs(db_dir, exist_ok=True)

app.config['MODEL_DIRECTORY'] = os.environ.get('MODEL_DIRECTORY', os.path.join(app.root_path, 'models'))

# Upload Configuration
UPLOAD_FOLDER = os.environ.get('UPLOAD_FOLDER', os.path.join(app.root_path, 'static', 'uploads', 'profile_pics'))
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

try:
    max_len = int(os.environ.get('MAX_CONTENT_LENGTH', 10 * 1024 * 1024))
except ValueError:
    max_len = 10 * 1024 * 1024
app.config['MAX_CONTENT_LENGTH'] = max_len # 10MB upload limit default

app.config['CLASSROOM_UPLOAD_FOLDER'] = os.environ.get('CLASSROOM_UPLOAD_FOLDER', os.path.join(app.root_path, 'static', 'uploads', 'classroom'))
app.config['ANNOTATED_UPLOAD_FOLDER'] = os.environ.get('ANNOTATED_UPLOAD_FOLDER', os.path.join(app.root_path, 'static', 'uploads', 'classroom', 'annotated'))

from utils.cv_engine import extract_single_face_embedding
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def is_valid_image_file(file):
    if not file or not file.filename:
        return False
    if not allowed_file(file.filename):
        return False
        
    try:
        from PIL import Image
        img = Image.open(file)
        img.verify()
        if img.format.lower() not in ['jpeg', 'jpg', 'png', 'webp', 'mpo']:
            return False
        return True
    except Exception:
        return False
    finally:
        file.seek(0)

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash("Please log in to access this page.", "error")
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def role_required(role):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user_id' not in session:
                flash("Please log in to access this page.", "error")
                return redirect(url_for('login'))
            if session.get('role') != role:
                flash("Unauthorized access.", "error")
                # Redirect to appropriate dashboard
                if session.get('role') == 'teacher':
                    return redirect(url_for('teacher_dashboard'))
                elif session.get('role') == 'student':
                    return redirect(url_for('student_dashboard'))
                return redirect(url_for('login'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def is_valid_email(email):
    # Basic email format validation
    pattern = r'^[\w\.-]+@[\w\.-]+\.\w+$'
    return re.match(pattern, email) is not None

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/initdb')
def initialize_database():
    """Simple route to initialize the database."""
    init_db(app.config['DATABASE'])
    return "Database initialized successfully!"

@app.route('/register/teacher', methods=['GET', 'POST'])
def register_teacher():
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        subject = request.form.get('subject')
        department = request.form.get('department')
        
        if not all([name, email, password, confirm_password, subject, department]):
            flash("All fields are required.", "error")
            return render_template('auth/register_teacher.html')
            
        if not is_valid_email(email):
            flash("Invalid email format.", "error")
            return render_template('auth/register_teacher.html')
            
        if not password or len(password.strip()) < 8:
            flash("Password must be at least 8 characters long and cannot be whitespace only.", "error")
            return render_template('auth/register_teacher.html')
            
        if password != confirm_password:
            flash("Passwords do not match.", "error")
            return render_template('auth/register_teacher.html')
            
        existing_user = get_user_by_email(app.config['DATABASE'], email)
        if existing_user:
            flash("Email already registered.", "error")
            return render_template('auth/register_teacher.html')
            
        user_data = {
            'name': name,
            'email': email,
            'password_hash': generate_password_hash(password),
            'role': 'teacher',
            'subject': subject,
            'department': department,
            'student_id': None,
            'course': None,
            'semester': None
        }
        
        result = add_user(app.config['DATABASE'], user_data)
        if result is True:
            flash("Teacher registered successfully. Please login.", "success")
            return redirect(url_for('login'))
        else:
            flash(f"Registration failed: Database error.", "error")
            
    return render_template('auth/register_teacher.html')

@app.route('/register/student', methods=['GET', 'POST'])
def register_student():
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        student_id = request.form.get('student_id')
        course = request.form.get('course')
        semester = request.form.get('semester')
        
        if not all([name, email, password, confirm_password, student_id, course, semester]):
            flash("All fields are required.", "error")
            return render_template('auth/register_student.html')
            
        if not is_valid_email(email):
            flash("Invalid email format.", "error")
            return render_template('auth/register_student.html')
            
        if not password or len(password.strip()) < 8:
            flash("Password must be at least 8 characters long and cannot be whitespace only.", "error")
            return render_template('auth/register_student.html')
            
        if password != confirm_password:
            flash("Passwords do not match.", "error")
            return render_template('auth/register_student.html')
            
        existing_email = get_user_by_email(app.config['DATABASE'], email)
        if existing_email:
            flash("Email already registered.", "error")
            return render_template('auth/register_student.html')
            
        existing_student_id = get_user_by_student_id(app.config['DATABASE'], student_id)
        if existing_student_id:
            flash("Student ID already registered.", "error")
            return render_template('auth/register_student.html')
            
        user_data = {
            'name': name,
            'email': email,
            'password_hash': generate_password_hash(password),
            'role': 'student',
            'subject': None,
            'department': None,
            'student_id': student_id,
            'course': course,
            'semester': semester
        }
        
        result = add_user(app.config['DATABASE'], user_data)
        if result is True:
            flash("Student registered successfully. Please login.", "success")
            return redirect(url_for('login'))
        else:
            flash(f"Registration failed: Database error.", "error")
            
    return render_template('auth/register_student.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        if not all([email, password]):
            flash("Email and password are required.", "error")
            return render_template('auth/login.html')
            
        user = get_user_by_email(app.config['DATABASE'], email)
        
        if user and check_password_hash(user['password_hash'], password):
            session['user_id'] = user['id']
            session['role'] = user['role']
            session['name'] = user['name']
            
            if user['role'] == 'teacher':
                return redirect(url_for('teacher_dashboard'))
            else:
                return redirect(url_for('student_dashboard'))
        else:
            flash("Invalid email or password.", "error")
            
    return render_template('auth/login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for('index'))

@app.route('/teacher/dashboard')
@role_required('teacher')
def teacher_dashboard():
    user = get_user_by_id(app.config['DATABASE'], session['user_id'])
    stats = get_teacher_dashboard_stats(app.config['DATABASE'], session['user_id'])
    return render_template('teacher/dashboard.html', user=user, stats=stats)

@app.route('/teacher/profile', methods=['GET'])
@role_required('teacher')
def teacher_profile():
    user = get_user_by_id(app.config['DATABASE'], session['user_id'])
    return render_template('teacher/profile.html', user=user)

@app.route('/teacher/profile/edit', methods=['GET', 'POST'])
@role_required('teacher')
def teacher_profile_edit():
    user = get_user_by_id(app.config['DATABASE'], session['user_id'])
    
    if request.method == 'POST':
        if request.content_length and request.content_length > 2 * 1024 * 1024:
            from werkzeug.exceptions import RequestEntityTooLarge
            raise RequestEntityTooLarge()
        name = request.form.get('name')
        subject = request.form.get('subject')
        department = request.form.get('department')
        
        if not all([name, subject, department]):
            flash("Name, Subject, and Department are required.", "error")
            return redirect(url_for('teacher_profile_edit'))
            
        if update_teacher_profile(app.config['DATABASE'], session['user_id'], name, subject, department) is True:
            session['name'] = name # Update session name
            
            # Handle profile picture upload
            if 'profile_picture' in request.files:
                file = request.files['profile_picture']
                if file.filename != '':
                    if file and is_valid_image_file(file):
                        ext = file.filename.rsplit('.', 1)[1].lower()
                        filename = secure_filename(f"{uuid.uuid4().hex}.{ext}")
                        
                        # Delete old picture if exists
                        if user['profile_picture']:
                            old_path = os.path.join(app.config['UPLOAD_FOLDER'], user['profile_picture'])
                            if os.path.exists(old_path):
                                os.remove(old_path)
                                
                        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                        update_profile_picture(app.config['DATABASE'], session['user_id'], filename)
                    else:
                        flash("Invalid image format. Use JPG, PNG, or WEBP.", "error")
                        return redirect(url_for('teacher_profile_edit'))

            flash("Profile updated successfully.", "success")
            return redirect(url_for('teacher_profile'))
        else:
            flash("Failed to update profile.", "error")
            
    return render_template('teacher/profile_edit.html', user=user)

@app.route('/teacher/profile/picture/remove', methods=['POST'])
@role_required('teacher')
def teacher_remove_picture():
    user = get_user_by_id(app.config['DATABASE'], session['user_id'])
    if user['profile_picture']:
        old_path = os.path.join(app.config['UPLOAD_FOLDER'], user['profile_picture'])
        if os.path.exists(old_path):
            os.remove(old_path)
        update_profile_picture(app.config['DATABASE'], session['user_id'], None)
        flash("Profile picture removed.", "success")
    return redirect(url_for('teacher_profile'))

@app.route('/student/dashboard')
@role_required('student')
def student_dashboard():
    user = get_user_by_id(app.config['DATABASE'], session['user_id'])
    stats = get_student_dashboard_stats(app.config['DATABASE'], session['user_id'])
    return render_template('student/dashboard.html', user=user, stats=stats)

@app.route('/student/profile', methods=['GET'])
@role_required('student')
def student_profile():
    user = get_user_by_id(app.config['DATABASE'], session['user_id'])
    return render_template('student/profile.html', user=user)

@app.route('/student/profile/edit', methods=['GET', 'POST'])
@role_required('student')
def student_profile_edit():
    user = get_user_by_id(app.config['DATABASE'], session['user_id'])
    
    if request.method == 'POST':
        if request.content_length and request.content_length > 2 * 1024 * 1024:
            from werkzeug.exceptions import RequestEntityTooLarge
            raise RequestEntityTooLarge()
        name = request.form.get('name')
        course = request.form.get('course')
        semester = request.form.get('semester')
        
        if not all([name, course, semester]):
            flash("Name, Course, and Semester are required.", "error")
            return redirect(url_for('student_profile_edit'))
            
        if update_student_profile(app.config['DATABASE'], session['user_id'], name, course, semester) is True:
            session['name'] = name # Update session name
            
            # Handle profile picture upload
            if 'profile_picture' in request.files:
                file = request.files['profile_picture']
                if file.filename != '':
                    if file and is_valid_image_file(file):
                        # Phase 11.4: Extract face embedding
                        file_bytes = file.read()
                        cv_result = extract_single_face_embedding(file_bytes)
                        
                        if not cv_result['success']:
                            flash(cv_result['error'], "error")
                            return redirect(url_for('student_profile_edit'))
                        
                        ext = file.filename.rsplit('.', 1)[1].lower()
                        filename = secure_filename(f"{uuid.uuid4().hex}.{ext}")
                        
                        # Save embedding
                        upsert_res = upsert_face_embedding(app.config['DATABASE'], session['user_id'], cv_result['embedding'], cv_result['model_name'])
                        if upsert_res is not True:
                            flash("Database error during face enrollment.", "error")
                            return redirect(url_for('student_profile_edit'))
                            
                        # Delete old picture if exists
                        if user['profile_picture']:
                            old_path = os.path.join(app.config['UPLOAD_FOLDER'], user['profile_picture'])
                            if os.path.exists(old_path):
                                try:
                                    os.remove(old_path)
                                except:
                                    pass
                                
                        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                        with open(file_path, 'wb') as f:
                            f.write(file_bytes)
                        update_profile_picture(app.config['DATABASE'], session['user_id'], filename)
                    else:
                        flash("Invalid image format. Use JPG, PNG, or WEBP.", "error")
                        return redirect(url_for('student_profile_edit'))

            flash("Profile updated successfully.", "success")
            return redirect(url_for('student_profile'))
        else:
            flash("Failed to update profile.", "error")
            
    return render_template('student/profile_edit.html', user=user)

@app.route('/student/profile/picture/remove', methods=['POST'])
@role_required('student')
def student_remove_picture():
    user = get_user_by_id(app.config['DATABASE'], session['user_id'])
    if user['profile_picture']:
        old_path = os.path.join(app.config['UPLOAD_FOLDER'], user['profile_picture'])
        if os.path.exists(old_path):
            os.remove(old_path)
        update_profile_picture(app.config['DATABASE'], session['user_id'], None)
        flash("Profile picture removed.", "success")
    return redirect(url_for('student_profile'))

@app.route('/teacher/account/delete', methods=['POST'])
@role_required('teacher')
def teacher_delete_account():
    user = get_user_by_id(app.config['DATABASE'], session['user_id'])
    if user['profile_picture']:
        old_path = os.path.join(app.config['UPLOAD_FOLDER'], user['profile_picture'])
        if os.path.exists(old_path):
            os.remove(old_path)
            
    delete_user(app.config['DATABASE'], session['user_id'])
    session.clear()
    flash("Your account has been permanently deleted.", "success")
    return redirect(url_for('index'))

@app.route('/student/account/delete', methods=['POST'])
@role_required('student')
def student_delete_account():
    user = get_user_by_id(app.config['DATABASE'], session['user_id'])
    if user['profile_picture']:
        old_path = os.path.join(app.config['UPLOAD_FOLDER'], user['profile_picture'])
        if os.path.exists(old_path):
            os.remove(old_path)
            
    delete_user(app.config['DATABASE'], session['user_id'])
    session.clear()
    flash("Your account has been permanently deleted.", "success")
    return redirect(url_for('index'))

@app.route('/teacher/classes')
@role_required('teacher')
def teacher_classes():
    classes = get_teacher_classes(app.config['DATABASE'], session['user_id'])
    return render_template('teacher/classes.html', classes=classes)

@app.route('/teacher/classes/create', methods=['GET', 'POST'])
@role_required('teacher')
def teacher_class_create():
    if request.method == 'POST':
        class_name = request.form.get('class_name')
        subject = request.form.get('subject')
        course = request.form.get('course')
        semester = request.form.get('semester')
        
        if not all([class_name, subject, course, semester]):
            flash("All fields are required.", "error")
            return redirect(url_for('teacher_class_create'))
            
        class_code = uuid.uuid4().hex[:8].upper()
        result = create_class(app.config['DATABASE'], session['user_id'], class_name, subject, course, semester, class_code)
        
        if result is True:
            flash(f"Class created successfully! Class Code: {class_code}", "success")
            return redirect(url_for('teacher_classes'))
        else:
            flash("Failed to create class.", "error")
            
    return render_template('teacher/class_create.html')

@app.route('/teacher/classes/<int:class_id>')
@role_required('teacher')
def teacher_class_detail(class_id):
    class_ = get_class_by_id(app.config['DATABASE'], class_id)
    if not class_ or class_['teacher_id'] != session['user_id']:
        flash("Class not found or unauthorized.", "error")
        return redirect(url_for('teacher_classes'))
        
    students = get_class_students(app.config['DATABASE'], class_id)
    return render_template('teacher/class_detail.html', class_=class_, students=students)

@app.route('/teacher/classes/<int:class_id>/edit', methods=['GET', 'POST'])
@role_required('teacher')
def teacher_class_edit(class_id):
    class_ = get_class_by_id(app.config['DATABASE'], class_id)
    if not class_ or class_['teacher_id'] != session['user_id']:
        flash("Class not found or unauthorized.", "error")
        return redirect(url_for('teacher_classes'))
        
    if request.method == 'POST':
        class_name = request.form.get('class_name')
        subject = request.form.get('subject')
        course = request.form.get('course')
        semester = request.form.get('semester')
        
        if not all([class_name, subject, course, semester]):
            flash("All fields are required.", "error")
            return redirect(url_for('teacher_class_edit', class_id=class_id))
            
        if update_class(app.config['DATABASE'], class_id, class_name, subject, course, semester) is True:
            flash("Class updated successfully.", "success")
            return redirect(url_for('teacher_classes'))
        else:
            flash("Failed to update class.", "error")
            
    return render_template('teacher/class_edit.html', class_=class_)

@app.route('/teacher/classes/<int:class_id>/delete', methods=['POST'])
@role_required('teacher')
def teacher_class_delete(class_id):
    class_ = get_class_by_id(app.config['DATABASE'], class_id)
    if not class_ or class_['teacher_id'] != session['user_id']:
        flash("Class not found or unauthorized.", "error")
        return redirect(url_for('teacher_classes'))
        
    if delete_class(app.config['DATABASE'], class_id) is True:
        flash("Class deleted successfully.", "success")
    else:
        flash("Failed to delete class.", "error")
    return redirect(url_for('teacher_classes'))

@app.route('/student/classes')
@role_required('student')
def student_classes():
    classes = get_student_classes(app.config['DATABASE'], session['user_id'])
    return render_template('student/classes.html', classes=classes)

@app.route('/student/classes/join', methods=['GET', 'POST'])
@role_required('student')
def student_class_join():
    if request.method == 'POST':
        class_code = request.form.get('class_code')
        if not class_code:
            flash("Class code is required.", "error")
            return redirect(url_for('student_class_join'))
            
        class_ = get_class_by_code(app.config['DATABASE'], class_code)
        if not class_:
            flash("Invalid class code.", "error")
            return redirect(url_for('student_class_join'))
            
        if is_student_enrolled(app.config['DATABASE'], class_['id'], session['user_id']):
            flash("You are already enrolled in this class.", "error")
            return redirect(url_for('student_classes'))
            
        if enroll_student(app.config['DATABASE'], class_['id'], session['user_id']) is True:
            flash("Successfully joined the class!", "success")
            return redirect(url_for('student_classes'))
        else:
            flash("Failed to join class.", "error")
            
    return render_template('student/join_class.html')

@app.route('/student/classes/<int:class_id>/leave', methods=['POST'])
@role_required('student')
def student_class_leave(class_id):
    if not is_student_enrolled(app.config['DATABASE'], class_id, session['user_id']):
        flash("You are not enrolled in this class.", "error")
        return redirect(url_for('student_classes'))
        
    if leave_class(app.config['DATABASE'], class_id, session['user_id']) is True:
        flash("Successfully left the class.", "success")
    else:
        flash("Failed to leave class.", "error")
        
    return redirect(url_for('student_classes'))

@app.route('/teacher/classes/<int:class_id>/attendance', methods=['GET', 'POST'])
@role_required('teacher')
def teacher_attendance_start(class_id):
    class_ = get_class_by_id(app.config['DATABASE'], class_id)
    if not class_ or class_['teacher_id'] != session['user_id']:
        flash("Class not found or unauthorized.", "error")
        return redirect(url_for('teacher_classes'))
        
    active_session = get_active_session_for_class(app.config['DATABASE'], class_id)
    if active_session:
        # Check if actually expired
        expires_at = datetime.strptime(active_session['expires_at'], '%Y-%m-%d %H:%M:%S')
        if datetime.utcnow() > expires_at:
            end_attendance_session(app.config['DATABASE'], active_session['id'])
            active_session = None
        else:
            return redirect(url_for('teacher_attendance_session', session_id=active_session['id']))
            
    if request.method == 'POST':
        duration = int(request.form.get('duration', 10))
        # Cryptographically secure code
        session_code = secrets.token_urlsafe(8)
        expires_at = (datetime.utcnow() + timedelta(minutes=duration)).strftime('%Y-%m-%d %H:%M:%S')
        
        session_id = create_attendance_session(app.config['DATABASE'], class_id, session_code, expires_at)
        if isinstance(session_id, int):
            flash("Attendance session started.", "success")
            return redirect(url_for('teacher_attendance_session', session_id=session_id))
        else:
            flash("Error starting session.", "error")
            
    return render_template('teacher/attendance_start.html', class_=class_)

@app.route('/teacher/attendance/<int:session_id>')
@role_required('teacher')
def teacher_attendance_session(session_id):
    att_session = get_attendance_session(app.config['DATABASE'], session_id)
    if not att_session:
        flash("Session not found.", "error")
        return redirect(url_for('teacher_classes'))
        
    class_ = get_class_by_id(app.config['DATABASE'], att_session['class_id'])
    if not class_ or class_['teacher_id'] != session['user_id']:
        flash("Unauthorized.", "error")
        return redirect(url_for('teacher_classes'))
        
    # Check expiration
    expires_at = datetime.strptime(att_session['expires_at'], '%Y-%m-%d %H:%M:%S')
    if att_session['status'] == 'active' and datetime.utcnow() > expires_at:
        end_attendance_session(app.config['DATABASE'], session_id)
        att_session = get_attendance_session(app.config['DATABASE'], session_id) # Reload
        
    # Generate QR Code
    checkin_url = url_for('student_checkin', session_code=att_session['session_code'], _external=True)
    qr = qrcode.make(checkin_url)
    buf = io.BytesIO()
    qr.save(buf, format='PNG')
    qr_b64 = base64.b64encode(buf.getvalue()).decode('utf-8')
    
    records = get_session_attendance(app.config['DATABASE'], session_id)
    count = count_session_attendance(app.config['DATABASE'], session_id)
    
    return render_template('teacher/attendance_session.html', 
                           class_=class_, 
                           att_session=att_session, 
                           qr_b64=qr_b64, 
                           records=records, 
                           count=count)

@app.route('/teacher/attendance/<int:session_id>/end', methods=['POST'])
@role_required('teacher')
def teacher_attendance_end(session_id):
    att_session = get_attendance_session(app.config['DATABASE'], session_id)
    if not att_session:
        return redirect(url_for('teacher_classes'))
    class_ = get_class_by_id(app.config['DATABASE'], att_session['class_id'])
    if not class_ or class_['teacher_id'] != session['user_id']:
        flash("Unauthorized.", "error")
        return redirect(url_for('teacher_classes'))
        
    end_attendance_session(app.config['DATABASE'], session_id)
    flash("Attendance session ended.", "success")
    return redirect(url_for('teacher_attendance_session', session_id=session_id))

@app.route('/teacher/classes/<int:class_id>/attendance/history')
@role_required('teacher')
def teacher_class_attendance_history(class_id):
    class_ = get_class_by_id(app.config['DATABASE'], class_id)
    if not class_ or class_['teacher_id'] != session['user_id']:
        flash("Unauthorized.", "error")
        return redirect(url_for('teacher_classes'))
        
    records = get_class_attendance_history(app.config['DATABASE'], class_id)
    return render_template('teacher/attendance_history.html', class_=class_, records=records)

@app.route('/student/attendance/checkin/<session_code>', methods=['GET', 'POST'])
@role_required('student')
def student_checkin(session_code):
    att_session = get_attendance_session_by_code(app.config['DATABASE'], session_code)
    if not att_session:
        flash("Invalid or expired session code.", "error")
        return redirect(url_for('student_classes'))
        
    class_ = get_class_by_id(app.config['DATABASE'], att_session['class_id'])
    
    # Validation checks
    if not is_student_enrolled(app.config['DATABASE'], class_['id'], session['user_id']):
        flash("You are not enrolled in this class.", "error")
        return redirect(url_for('student_classes'))
        
    if att_session['status'] != 'active':
        flash("This attendance session has ended.", "error")
        return redirect(url_for('student_classes'))
        
    expires_at = datetime.strptime(att_session['expires_at'], '%Y-%m-%d %H:%M:%S')
    if datetime.utcnow() > expires_at:
        end_attendance_session(app.config['DATABASE'], att_session['id'])
        flash("This attendance session has expired.", "error")
        return redirect(url_for('student_classes'))
        
    if has_attendance_record(app.config['DATABASE'], att_session['id'], session['user_id']):
        flash("You have already checked in for this session.", "error")
        return redirect(url_for('student_classes'))
        
    if request.method == 'POST':
        if create_attendance_record(app.config['DATABASE'], att_session['id'], session['user_id']) is True:
            flash("Attendance marked successfully!", "success")
            return redirect(url_for('student_attendance'))
        else:
            flash("Failed to mark attendance. You may have already checked in.", "error")
            
    return render_template('student/attendance_checkin.html', class_=class_, att_session=att_session)

@app.route('/student/attendance')
@role_required('student')
def student_attendance():
    records = get_student_attendance(app.config['DATABASE'], session['user_id'])
    return render_template('student/attendance.html', records=records)


from utils.report_generator import generate_csv, generate_pdf
from database.database import get_teacher_report, get_student_report
from flask import Response

@app.route('/teacher/reports', methods=['GET'])
@login_required
def teacher_reports():
    if session.get('role') != 'teacher':
        flash("Unauthorized access.", "error")
        return redirect(url_for('student_dashboard'))
        
    db_path = app.config['DATABASE']
    conn = get_db_connection(db_path)
    classes = conn.execute('SELECT * FROM classes WHERE teacher_id = ?', (session['user_id'],)).fetchall()
    conn.close()
    
    class_id = request.args.get('class_id')
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    
    if start_date and end_date and start_date > end_date:
        flash("Start date cannot be after end date.", "error")
        return redirect(url_for('teacher_reports'))
        
    report = None
    if class_id:
        report = get_teacher_report(db_path, session['user_id'], class_id, start_date, end_date)
        if not report:
            flash("Invalid class selection.", "error")
            return redirect(url_for('teacher_reports'))
            
    return render_template('teacher/reports.html', classes=classes, report=report, class_id=int(class_id) if class_id else None, start_date=start_date, end_date=end_date)

@app.route('/teacher/reports/export/csv', methods=['GET'])
@login_required
def teacher_export_csv():
    if session.get('role') != 'teacher':
        return "Unauthorized", 403
        
    class_id = request.args.get('class_id')
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    
    if not class_id:
        return "Class required", 400
        
    report = get_teacher_report(app.config['DATABASE'], session['user_id'], class_id, start_date, end_date)
    if not report:
        return "Invalid class", 400
        
    headers = ['Student ID', 'Student Name', 'Sessions', 'Present', 'Percentage']
    rows = []
    for s in report['student_stats']:
        pct = f"{s['percentage']:.2f}%" if s['percentage'] is not None else "N/A"
        rows.append([s['student_id'], s['name'], s['sessions'], s['present'], pct])
        
    csv_data = generate_csv(headers, rows)
    
    filename = f"attendance_{report['class_info']['class_name']}"
    if start_date and end_date:
        filename += f"_{start_date}_to_{end_date}"
    filename += ".csv"
    
    return Response(csv_data, mimetype="text/csv", headers={"Content-Disposition": f"attachment;filename={filename}"})

@app.route('/teacher/reports/export/pdf', methods=['GET'])
@login_required
def teacher_export_pdf():
    if session.get('role') != 'teacher':
        return "Unauthorized", 403
        
    class_id = request.args.get('class_id')
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    
    if not class_id:
        return "Class required", 400
        
    report = get_teacher_report(app.config['DATABASE'], session['user_id'], class_id, start_date, end_date)
    if not report:
        return "Invalid class", 400
        
    title = f"Attendance Report: {report['class_info']['class_name']}"
    
    pct = f"{report['summary']['overall_percentage']:.2f}%" if report['summary']['overall_percentage'] is not None else "N/A"
    summary = [
        f"Subject: {report['class_info']['subject']} | Course: {report['class_info']['course']} | Sem: {report['class_info']['semester']}",
        f"Total Students: {report['summary']['students']}",
        f"Sessions Conducted: {report['summary']['sessions']}",
        f"Overall Attendance: {pct}"
    ]
    if start_date and end_date:
        summary.append(f"Date Range: {start_date} to {end_date}")
        
    headers = ['Student ID', 'Student Name', 'Sessions', 'Present', 'Percentage']
    rows = []
    for s in report['student_stats']:
        pct_str = f"{s['percentage']:.2f}%" if s['percentage'] is not None else "N/A"
        rows.append([s['student_id'], s['name'], str(s['sessions']), str(s['present']), pct_str])
        
    pdf_data = generate_pdf(title, summary, headers, rows)
    
    filename = f"attendance_{report['class_info']['class_name']}.pdf"
    
    return Response(pdf_data, mimetype="application/pdf", headers={"Content-Disposition": f"attachment;filename={filename}"})

from utils.report_generator import generate_csv, generate_pdf
from database.database import get_teacher_report, get_student_report
from flask import Response

@app.route('/student/reports', methods=['GET'])
@login_required
def student_reports():
    if session.get('role') != 'student':
        flash("Unauthorized access.", "error")
        return redirect(url_for('teacher_dashboard'))
        
    db_path = app.config['DATABASE']
    conn = get_db_connection(db_path)
    classes = conn.execute('''
        SELECT c.* FROM classes c 
        JOIN enrollments e ON c.id = e.class_id 
        WHERE e.student_id = ?
    ''', (session['user_id'],)).fetchall()
    conn.close()
    
    class_id = request.args.get('class_id')
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    
    if start_date and end_date and start_date > end_date:
        flash("Start date cannot be after end date.", "error")
        return redirect(url_for('student_reports'))
        
    if class_id:
        enrolled = False
        for c in classes:
            if c['id'] == int(class_id):
                enrolled = True
                break
        if not enrolled:
            flash("Invalid class selection.", "error")
            return redirect(url_for('student_reports'))
            
    report = get_student_report(db_path, session['user_id'], class_id, start_date, end_date)
    return render_template('student/reports.html', classes=classes, report=report, class_id=int(class_id) if class_id else None, start_date=start_date, end_date=end_date)

@app.route('/student/reports/export/csv', methods=['GET'])
@login_required
def student_export_csv():
    if session.get('role') != 'student':
        return "Unauthorized", 403
        
    class_id = request.args.get('class_id')
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    
    if class_id:
        conn = get_db_connection(app.config['DATABASE'])
        e = conn.execute('SELECT * FROM enrollments WHERE student_id = ? AND class_id = ?', (session['user_id'], class_id)).fetchone()
        conn.close()
        if not e:
            return "Invalid class", 400
            
    report = get_student_report(app.config['DATABASE'], session['user_id'], class_id, start_date, end_date)
    
    headers = ['Date', 'Class', 'Session', 'Status']
    rows = []
    for h in report['history']:
        rows.append([h['date'], h['class_name'], h['session'], h['status']])
        
    csv_data = generate_csv(headers, rows)
    
    filename = "my_attendance_report.csv"
    
    return Response(csv_data, mimetype="text/csv", headers={"Content-Disposition": f"attachment;filename={filename}"})

@app.route('/student/reports/export/pdf', methods=['GET'])
@login_required
def student_export_pdf():
    if session.get('role') != 'student':
        return "Unauthorized", 403
        
    class_id = request.args.get('class_id')
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    
    if class_id:
        conn = get_db_connection(app.config['DATABASE'])
        e = conn.execute('SELECT * FROM enrollments WHERE student_id = ? AND class_id = ?', (session['user_id'], class_id)).fetchone()
        conn.close()
        if not e:
            return "Invalid class", 400
            
    report = get_student_report(app.config['DATABASE'], session['user_id'], class_id, start_date, end_date)
    
    title = "My Attendance Report"
    
    pct = f"{report['summary']['overall_percentage']:.2f}%" if report['summary']['overall_percentage'] is not None else "N/A"
    summary = [
        f"Total Sessions: {report['summary']['sessions']}",
        f"Present: {report['summary']['present']}",
        f"Overall Attendance: {pct}"
    ]
    if start_date and end_date:
        summary.append(f"Date Range: {start_date} to {end_date}")
        
    headers = ['Date', 'Class', 'Session', 'Status']
    rows = []
    for h in report['history']:
        rows.append([h['date'], h['class_name'], h['session'], h['status']])
        
    pdf_data = generate_pdf(title, summary, headers, rows)
    
    filename = "my_attendance_report.pdf"
    return Response(pdf_data, mimetype="application/pdf", headers={"Content-Disposition": f"attachment;filename={filename}"})

import logging
from logging.handlers import RotatingFileHandler

# Configure logging
if not app.debug:
    # Ensure logs directory exists
    log_dir = os.environ.get('LOG_DIRECTORY', os.path.join(app.root_path, 'logs'))
    os.makedirs(log_dir, exist_ok=True)
    
    file_handler = RotatingFileHandler(os.path.join(log_dir, 'attendify.log'), maxBytes=10240, backupCount=10)
    file_handler.setFormatter(logging.Formatter(
        '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
    ))
    file_handler.setLevel(logging.INFO)
    app.logger.addHandler(file_handler)
    app.logger.setLevel(logging.INFO)
    app.logger.info('Attendify startup')

@app.route('/health', methods=['GET'])
def health_check():
    try:
        conn = get_db_connection(app.config['DATABASE'])
        conn.execute('SELECT 1').fetchone()
        conn.close()
        return jsonify({"status": "healthy", "database": "connected"}), 200
    except Exception as e:
        app.logger.error(f"Health check failed: {e}")
        return jsonify({"status": "unhealthy", "error": "Database connection failed"}), 503

@app.errorhandler(400)
def bad_request(e):
    return render_template('error.html', code=400, message="Bad Request: Invalid input or missing parameters."), 400

@app.errorhandler(401)
def unauthorized(e):
    return render_template('error.html', code=401, message="Unauthorized: Please log in."), 401

@app.errorhandler(403)
def forbidden(e):
    return render_template('error.html', code=403, message="Forbidden: You do not have permission to access this resource."), 403

@app.errorhandler(404)
def not_found(e):
    return render_template('error.html', code=404, message="Not Found: The requested resource does not exist."), 404

@app.errorhandler(413)
def payload_too_large(e):
    return render_template('error.html', code=413, message="Payload Too Large: The uploaded file exceeds the maximum allowed size."), 413

@app.errorhandler(500)
def internal_error(e):
    return render_template('error.html', code=500, message="Internal Server Error: Something went wrong on our end."), 500

if __name__ == '__main__':
    host = os.environ.get('FLASK_HOST', '127.0.0.1')
    try:
        port = int(os.environ.get('FLASK_PORT', 5000))
    except ValueError:
        port = 5000
    app.run(host=host, port=port, debug=app.config.get('DEBUG', False))

from utils.face_recognition_engine import FaceRecognitionEngine

@app.route('/teacher/classes/<int:class_id>/attendance/<int:session_id>/recognize', methods=['POST'])
@login_required
@role_required('teacher')
def teacher_photo_recognize(class_id, session_id):
    class_ = get_class_by_id(app.config['DATABASE'], class_id)
    if not class_ or class_['teacher_id'] != session['user_id']:
        return jsonify({"success": False, "error": "Unauthorized class access"}), 403
        
    att_session = get_attendance_session(app.config['DATABASE'], session_id)
    if not att_session or att_session['class_id'] != class_id:
        return jsonify({"success": False, "error": "Invalid attendance session"}), 400
        
    if att_session['status'] != 'active':
        return jsonify({"success": False, "error": "Session is not active"}), 400
        
    if 'file' not in request.files:
        return jsonify({"success": False, "error": "No file part"}), 400
        
    file = request.files['file']
    if file.filename == '':
        return jsonify({"success": False, "error": "No selected file"}), 400
        
    if not is_valid_image_file(file):
        return jsonify({"success": False, "error": "Invalid or corrupted image format"}), 400
        
    try:
        file_bytes = file.read()
        engine = FaceRecognitionEngine(app.config['DATABASE'])
        rec_result = engine.process_classroom_image(file_bytes)
    except Exception as e:
        return jsonify({"success": False, "error": "Recognition engine failure"}), 500
        
    if not rec_result.get('success'):
        return jsonify({"success": False, "error": rec_result.get('error', 'Unknown CV error')}), 400
        
    import itsdangerous
    signer = itsdangerous.URLSafeTimedSerializer(app.config['SECRET_KEY'])
    
    eligible_students = []
    seen_users = set()
    
    results = rec_result.get('results', [])
    for face in results:
        face['enrolled_in_class'] = False
        face['already_present'] = False
        face['duplicate_in_photo'] = False
        
        if face.get('recognized') and face.get('user_id'):
            uid = face['user_id']
            is_enrolled = is_student_enrolled(app.config['DATABASE'], class_id, uid)
            if is_enrolled:
                face['enrolled_in_class'] = True
                
                has_att = has_attendance_record(app.config['DATABASE'], session_id, uid)
                if has_att:
                    face['already_present'] = True
                    
                if uid in seen_users:
                    face['duplicate_in_photo'] = True
                else:
                    seen_users.add(uid)
                    if not has_att:
                        eligible_students.append({
                            'user_id': uid,
                            'similarity': face.get('similarity', 0.0)
                        })
                    
    token_payload = {
        'teacher_id': session['user_id'],
        'class_id': class_id,
        'session_id': session_id,
        'eligible_students': eligible_students
    }
    save_token = signer.dumps(token_payload)
                
    response_data = {
        "success": True,
        "class_id": class_id,
        "session_id": session_id,
        "total_detected_faces": rec_result.get('total_detected_faces', 0),
        "recognized_faces": rec_result.get('recognized_faces', 0),
        "unknown_faces": rec_result.get('unknown_faces', 0),
        "results": results,
        "save_token": save_token
    }
    
    return jsonify(response_data), 200


@app.route('/teacher/classes/<int:class_id>/attendance/<int:session_id>/photo', methods=['GET'])
@login_required
@role_required('teacher')
def teacher_photo_attendance(class_id, session_id):
    class_ = get_class_by_id(app.config['DATABASE'], class_id)
    if not class_ or class_['teacher_id'] != session['user_id']:
        flash("Class not found or unauthorized.", "error")
        return redirect(url_for('teacher_classes'))
        
    att_session = get_attendance_session(app.config['DATABASE'], session_id)
    if not att_session or att_session['class_id'] != class_id:
        flash("Invalid session.", "error")
        return redirect(url_for('teacher_classes'))
        
    if att_session['status'] != 'active':
        flash("Session is no longer active.", "error")
        return redirect(url_for('teacher_attendance_session', session_id=session_id))
        
    return render_template('teacher/photo_attendance.html', class_=class_, att_session=att_session)

@app.route('/teacher/classes/<int:class_id>/attendance/<int:session_id>/save', methods=['POST'])
@login_required
@role_required('teacher')
def teacher_photo_save(class_id, session_id):
    class_ = get_class_by_id(app.config['DATABASE'], class_id)
    if not class_ or class_['teacher_id'] != session['user_id']:
        return jsonify({"success": False, "error": "Unauthorized class access"}), 403
        
    att_session = get_attendance_session(app.config['DATABASE'], session_id)
    if not att_session or att_session['class_id'] != class_id:
        return jsonify({"success": False, "error": "Invalid attendance session"}), 400
        
    if att_session['status'] != 'active':
        return jsonify({"success": False, "error": "Session is not active"}), 400
        
    data = request.get_json()
    if not data or 'save_token' not in data:
        return jsonify({"success": False, "error": "Missing save token"}), 400
        
    import itsdangerous
    signer = itsdangerous.URLSafeTimedSerializer(app.config['SECRET_KEY'])
    try:
        token_data = signer.loads(data['save_token'], max_age=900) # 15 minutes expiration
    except itsdangerous.SignatureExpired:
        return jsonify({"success": False, "error": "Save token has expired. Please re-upload the photo."}), 400
    except itsdangerous.BadSignature:
        return jsonify({"success": False, "error": "Invalid or tampered save token"}), 400
        
    if token_data.get('session_id') != session_id:
        return jsonify({"success": False, "error": "Token does not match session"}), 400
    
    if token_data.get('class_id') != class_id:
        return jsonify({"success": False, "error": "Token does not match class"}), 400
        
    if token_data.get('teacher_id') != session['user_id']:
        return jsonify({"success": False, "error": "Token does not match teacher"}), 400
        
    eligible_students = token_data.get('eligible_students', [])
    
    result = mark_photo_attendance(app.config['DATABASE'], session_id, eligible_students)
    
    if result.get('error'):
        return jsonify({"success": False, "error": result['error']}), 500
        
    return jsonify({
        "success": True,
        "marked_count": result['marked_count'],
        "already_present_count": result['already_present_count']
    }), 200

