import sqlite3
import os

def get_db_connection(db_path):
    """Establish a connection to the SQLite database."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

def init_db(db_path):
    """Initialize the database with tables if they do not exist."""
    # Ensure the directory exists
    dir_name = os.path.dirname(db_path)
    if dir_name:
        os.makedirs(dir_name, exist_ok=True)

    conn = get_db_connection(db_path)
    # Basic Phase 1 table setup
    conn.execute('CREATE TABLE IF NOT EXISTS system_info (id INTEGER PRIMARY KEY, version TEXT)')
    conn.execute('INSERT OR IGNORE INTO system_info (id, version) VALUES (1, "Phase 1")')

    # Phase 2 Users table
    conn.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL,
            subject TEXT,
            department TEXT,
            student_id TEXT UNIQUE,
            course TEXT,
            semester TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Phase 3: Add profile picture column if it doesn't exist
    try:
        conn.execute('ALTER TABLE users ADD COLUMN profile_picture TEXT')
    except sqlite3.OperationalError:
        pass # Column likely already exists

    # Phase 5: Classes and Enrollments tables
    conn.execute('''
        CREATE TABLE IF NOT EXISTS classes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            teacher_id INTEGER NOT NULL,
            class_name TEXT NOT NULL,
            subject TEXT NOT NULL,
            course TEXT NOT NULL,
            semester TEXT NOT NULL,
            class_code TEXT UNIQUE NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (teacher_id) REFERENCES users (id)
        )
    ''')

    conn.execute('''
        CREATE TABLE IF NOT EXISTS enrollments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            class_id INTEGER NOT NULL,
            student_id INTEGER NOT NULL,
            joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (class_id) REFERENCES classes (id),
            FOREIGN KEY (student_id) REFERENCES users (id),
            UNIQUE(class_id, student_id)
        )
    ''')

    # Phase 6: Attendance tables
    conn.execute('''
        CREATE TABLE IF NOT EXISTS attendance_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            class_id INTEGER NOT NULL,
            session_code TEXT UNIQUE NOT NULL,
            started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            expires_at TIMESTAMP NOT NULL,
            status TEXT NOT NULL DEFAULT 'active',
            FOREIGN KEY (class_id) REFERENCES classes (id)
        )
    ''')

    conn.execute('''
        CREATE TABLE IF NOT EXISTS attendance_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL,
            student_id INTEGER NOT NULL,
            marked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            status TEXT NOT NULL DEFAULT 'present',
            FOREIGN KEY (session_id) REFERENCES attendance_sessions (id),
            FOREIGN KEY (student_id) REFERENCES users (id),
            UNIQUE(session_id, student_id)
        )
    ''')

    # Phase 11.4: Face Embeddings
    conn.execute('''
        CREATE TABLE IF NOT EXISTS face_embeddings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER NOT NULL,
            embedding BLOB NOT NULL,
            model_name TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (student_id) REFERENCES users(id) ON DELETE CASCADE,
            UNIQUE(student_id, model_name)
        )
    ''')

    # Feature: Student Face Enrollment / Reference Images
    conn.execute('''
        CREATE TABLE IF NOT EXISTS student_face_references (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER NOT NULL,
            image_path TEXT NOT NULL,
            embedding BLOB NOT NULL,
            quality_status TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (student_id) REFERENCES users(id) ON DELETE CASCADE
        )
    ''')

    # Phase 11.5.6: Audit columns for photo attendance
    try:
        conn.execute("ALTER TABLE attendance_records ADD COLUMN attendance_source TEXT DEFAULT 'manual'")
    except sqlite3.OperationalError:
        pass

    try:
        conn.execute("ALTER TABLE attendance_records ADD COLUMN similarity REAL")
    except sqlite3.OperationalError:
        pass

    try:
        conn.execute("ALTER TABLE attendance_records ADD COLUMN reason TEXT")
    except sqlite3.OperationalError:
        pass

    try:
        conn.execute("ALTER TABLE attendance_sessions ADD COLUMN current_token TEXT")
        conn.execute("ALTER TABLE attendance_sessions ADD COLUMN token_expires_at TIMESTAMP")
    except sqlite3.OperationalError:
        pass

    conn.commit()
    conn.close()

def add_user(db_path, user_data):
    conn = get_db_connection(db_path)
    try:
        conn.execute('''
            INSERT INTO users (name, email, password_hash, role, subject, department, student_id, course, semester)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            user_data.get('name'),
            user_data.get('email'),
            user_data.get('password_hash'),
            user_data.get('role'),
            user_data.get('subject'),
            user_data.get('department'),
            user_data.get('student_id'),
            user_data.get('course'),
            user_data.get('semester')
        ))
        conn.commit()
        return True
    except sqlite3.IntegrityError as e:
        return str(e)
    finally:
        conn.close()

def get_user_by_email(db_path, email):
    conn = get_db_connection(db_path)
    user = conn.execute('SELECT * FROM users WHERE email = ?', (email,)).fetchone()
    conn.close()
    return user

def get_user_by_student_id(db_path, student_id):
    conn = get_db_connection(db_path)
    user = conn.execute('SELECT * FROM users WHERE student_id = ?', (student_id,)).fetchone()
    conn.close()
    return user

def get_user_by_id(db_path, user_id):
    conn = get_db_connection(db_path)
    user = conn.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
    conn.close()
    return user

def update_teacher_profile(db_path, user_id, name, subject, department):
    conn = get_db_connection(db_path)
    try:
        conn.execute('''
            UPDATE users
            SET name = ?, subject = ?, department = ?
            WHERE id = ? AND role = 'teacher'
        ''', (name, subject, department, user_id))
        conn.commit()
        return True
    except sqlite3.Error as e:
        return str(e)
    finally:
        conn.close()

def update_profile_picture(db_path, user_id, filename):
    conn = get_db_connection(db_path)
    try:
        conn.execute('''
            UPDATE users
            SET profile_picture = ?
            WHERE id = ?
        ''', (filename, user_id))
        conn.commit()
        return True
    except sqlite3.Error as e:
        return str(e)
    finally:
        conn.close()

def create_class(db_path, teacher_id, class_name, subject, course, semester, class_code):
    conn = get_db_connection(db_path)
    try:
        conn.execute('''
            INSERT INTO classes (teacher_id, class_name, subject, course, semester, class_code)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (teacher_id, class_name, subject, course, semester, class_code))
        conn.commit()
        return True
    except sqlite3.IntegrityError as e:
        return str(e)
    finally:
        conn.close()

def get_teacher_classes(db_path, teacher_id):
    conn = get_db_connection(db_path)
    # Also get the count of enrolled students for each class
    classes = conn.execute('''
        SELECT c.*, (SELECT COUNT(*) FROM enrollments WHERE class_id = c.id) as enrolled_count
        FROM classes c
        WHERE c.teacher_id = ?
        ORDER BY c.created_at DESC
    ''', (teacher_id,)).fetchall()
    conn.close()
    return classes

def get_class_by_id(db_path, class_id):
    conn = get_db_connection(db_path)
    class_ = conn.execute('SELECT * FROM classes WHERE id = ?', (class_id,)).fetchone()
    conn.close()
    return class_

def get_class_by_code(db_path, class_code):
    conn = get_db_connection(db_path)
    class_ = conn.execute('SELECT * FROM classes WHERE class_code = ?', (class_code,)).fetchone()
    conn.close()
    return class_

def update_class(db_path, class_id, class_name, subject, course, semester):
    conn = get_db_connection(db_path)
    try:
        conn.execute('''
            UPDATE classes
            SET class_name = ?, subject = ?, course = ?, semester = ?
            WHERE id = ?
        ''', (class_name, subject, course, semester, class_id))
        conn.commit()
        return True
    except sqlite3.Error as e:
        return str(e)
    finally:
        conn.close()

def delete_class(db_path, class_id):
    conn = get_db_connection(db_path)
    try:
        # First delete enrollments for this class
        conn.execute('DELETE FROM enrollments WHERE class_id = ?', (class_id,))
        # Then delete the class itself
        conn.execute('DELETE FROM classes WHERE id = ?', (class_id,))
        conn.commit()
        return True
    except sqlite3.Error as e:
        return str(e)
    finally:
        conn.close()

def get_class_students(db_path, class_id):
    conn = get_db_connection(db_path)
    students = conn.execute('''
        SELECT u.id, u.name, u.student_id, u.course, u.semester, e.joined_at
        FROM users u
        JOIN enrollments e ON u.id = e.student_id
        WHERE e.class_id = ?
        ORDER BY e.joined_at ASC
    ''', (class_id,)).fetchall()
    conn.close()
    return students

def enroll_student(db_path, class_id, student_id):
    conn = get_db_connection(db_path)
    try:
        conn.execute('''
            INSERT INTO enrollments (class_id, student_id)
            VALUES (?, ?)
        ''', (class_id, student_id))
        conn.commit()
        return True
    except sqlite3.IntegrityError as e:
        return str(e)
    finally:
        conn.close()

def is_student_enrolled(db_path, class_id, student_id):
    conn = get_db_connection(db_path)
    enrollment = conn.execute('''
        SELECT * FROM enrollments
        WHERE class_id = ? AND student_id = ?
    ''', (class_id, student_id)).fetchone()
    conn.close()
    return enrollment is not None

def get_student_classes(db_path, student_id):
    conn = get_db_connection(db_path)
    classes = conn.execute('''
        SELECT c.*, u.name as teacher_name, e.joined_at
        FROM classes c
        JOIN enrollments e ON c.id = e.class_id
        JOIN users u ON c.teacher_id = u.id
        WHERE e.student_id = ?
        ORDER BY e.joined_at DESC
    ''', (student_id,)).fetchall()
    conn.close()
    return classes

def leave_class(db_path, class_id, student_id):
    conn = get_db_connection(db_path)
    try:
        conn.execute('''
            DELETE FROM enrollments
            WHERE class_id = ? AND student_id = ?
        ''', (class_id, student_id))
        conn.commit()
        return True
    except sqlite3.Error as e:
        return str(e)
    finally:
        conn.close()

def update_student_profile(db_path, user_id, name, course, semester):
    conn = get_db_connection(db_path)
    try:
        conn.execute('''
            UPDATE users
            SET name = ?, course = ?, semester = ?
            WHERE id = ? AND role = 'student'
        ''', (name, course, semester, user_id))
        conn.commit()
        return True
    except sqlite3.Error as e:
        return str(e)
    finally:
        conn.close()

def delete_user(db_path, user_id):
    conn = get_db_connection(db_path)
    try:
        conn.execute('DELETE FROM student_face_references WHERE student_id = ?', (user_id,))
        conn.execute('DELETE FROM face_embeddings WHERE student_id = ?', (user_id,))
        conn.execute('DELETE FROM users WHERE id = ?', (user_id,))
        conn.commit()
        return True
    except sqlite3.Error as e:
        return str(e)
    finally:
        conn.close()

def create_attendance_session(db_path, class_id, session_code, expires_at):
    conn = get_db_connection(db_path)
    try:
        conn.execute('''
            INSERT INTO attendance_sessions (class_id, session_code, expires_at, status)
            VALUES (?, ?, ?, 'active')
        ''', (class_id, session_code, expires_at))
        session_id = conn.execute('SELECT last_insert_rowid()').fetchone()[0]
        conn.commit()
        return session_id
    except sqlite3.Error as e:
        return str(e)
    finally:
        conn.close()

def get_attendance_session(db_path, session_id):
    conn = get_db_connection(db_path)
    session = conn.execute('SELECT * FROM attendance_sessions WHERE id = ?', (session_id,)).fetchone()
    conn.close()
    return session

def get_attendance_session_by_code(db_path, session_code):
    conn = get_db_connection(db_path)
    session = conn.execute('SELECT * FROM attendance_sessions WHERE session_code = ?', (session_code,)).fetchone()
    conn.close()
    return session

def get_active_session_for_class(db_path, class_id):
    conn = get_db_connection(db_path)
    session = conn.execute('''
        SELECT * FROM attendance_sessions
        WHERE class_id = ? AND status = 'active'
        ORDER BY started_at DESC LIMIT 1
    ''', (class_id,)).fetchone()
    conn.close()
    return session

def end_attendance_session(db_path, session_id):
    conn = get_db_connection(db_path)
    try:
        conn.execute('''
            UPDATE attendance_sessions
            SET status = 'ended'
            WHERE id = ?
        ''', (session_id,))
        conn.commit()
        return True
    except sqlite3.Error as e:
        return str(e)
    finally:
        conn.close()

def create_attendance_record(db_path, session_id, student_id):
    conn = get_db_connection(db_path)
    try:
        conn.execute('''
            INSERT INTO attendance_records (session_id, student_id)
            VALUES (?, ?)
        ''', (session_id, student_id))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    except sqlite3.Error as e:
        return str(e)
    finally:
        conn.close()

def has_attendance_record(db_path, session_id, student_id):
    conn = get_db_connection(db_path)
    record = conn.execute('''
        SELECT id FROM attendance_records
        WHERE session_id = ? AND student_id = ?
    ''', (session_id, student_id)).fetchone()
    conn.close()
    return record is not None

def get_session_attendance(db_path, session_id):
    conn = get_db_connection(db_path)
    records = conn.execute('''
        SELECT a.*, u.name, u.student_id, u.course, u.semester
        FROM attendance_records a
        JOIN users u ON a.student_id = u.id
        WHERE a.session_id = ?
        ORDER BY a.marked_at ASC
    ''', (session_id,)).fetchall()
    conn.close()
    return records

def count_session_attendance(db_path, session_id):
    conn = get_db_connection(db_path)
    count = conn.execute('''
        SELECT COUNT(*) FROM attendance_records WHERE session_id = ?
    ''', (session_id,)).fetchone()[0]
    conn.close()
    return count

def get_class_attendance_history(db_path, class_id):
    conn = get_db_connection(db_path)
    records = conn.execute('''
        SELECT a.marked_at, a.status, u.name, u.student_id, s.session_code, s.started_at
        FROM attendance_records a
        JOIN attendance_sessions s ON a.session_id = s.id
        JOIN users u ON a.student_id = u.id
        WHERE s.class_id = ?
        ORDER BY s.started_at DESC, u.name ASC
    ''', (class_id,)).fetchall()
    conn.close()
    return records

def get_student_attendance(db_path, student_id):
    conn = get_db_connection(db_path)
    records = conn.execute('''
        SELECT a.marked_at, a.status, c.class_name, c.subject, c.class_code, s.started_at
        FROM attendance_records a
        JOIN attendance_sessions s ON a.session_id = s.id
        JOIN classes c ON s.class_id = c.id
        WHERE a.student_id = ?
        ORDER BY a.marked_at DESC
    ''', (student_id,)).fetchall()
    conn.close()
    return records

def get_teacher_dashboard_stats(db_path, teacher_id):
    conn = get_db_connection(db_path)

    classes = conn.execute('SELECT id, class_name, subject FROM classes WHERE teacher_id = ?', (teacher_id,)).fetchall()

    total_classes = len(classes)
    total_students_set = set()
    total_sessions = 0
    total_records = 0
    total_opportunities = 0

    class_stats = []

    for c in classes:
        c_id = c['id']
        enrollments = conn.execute('SELECT student_id FROM enrollments WHERE class_id = ?', (c_id,)).fetchall()
        enrolled_count = len(enrollments)
        for e in enrollments:
            total_students_set.add(e['student_id'])

        sessions = conn.execute('SELECT id, date(started_at) as s_date FROM attendance_sessions WHERE class_id = ? AND status = "ended"', (c_id,)).fetchall()
        session_count = len(sessions)
        total_sessions += session_count

        c_opportunities = enrolled_count * session_count
        total_opportunities += c_opportunities

        c_records = conn.execute('''
            SELECT COUNT(*) FROM attendance_records ar
            JOIN attendance_sessions s ON ar.session_id = s.id
            WHERE s.class_id = ? AND s.status = 'ended'
        ''', (c_id,)).fetchone()[0]
        total_records += c_records

        c_percentage = (c_records / c_opportunities * 100) if c_opportunities > 0 else None

        class_stats.append({
            'class_name': c['class_name'],
            'subject': c['subject'],
            'enrolled': enrolled_count,
            'sessions': session_count,
            'records': c_records,
            'percentage': c_percentage
        })

    overall_percentage = (total_records / total_opportunities * 100) if total_opportunities > 0 else None

    trend_dict = {}
    sessions_all = conn.execute('''
        SELECT s.id, date(s.started_at) as s_date, s.class_id
        FROM attendance_sessions s
        WHERE s.status = 'ended' AND s.class_id IN (SELECT id FROM classes WHERE teacher_id = ?)
    ''', (teacher_id,)).fetchall()

    for s in sessions_all:
        s_date = s['s_date']
        if s_date not in trend_dict:
            trend_dict[s_date] = {'opp': 0, 'rec': 0}

        enc = conn.execute('SELECT COUNT(*) FROM enrollments WHERE class_id = ?', (s['class_id'],)).fetchone()[0]
        trend_dict[s_date]['opp'] += enc

        rec = conn.execute('SELECT COUNT(*) FROM attendance_records WHERE session_id = ?', (s['id'],)).fetchone()[0]
        trend_dict[s_date]['rec'] += rec

    trend_data = []
    for d in sorted(trend_dict.keys()):
        opp = trend_dict[d]['opp']
        rec = trend_dict[d]['rec']
        pct = (rec / opp * 100) if opp > 0 else 0
        trend_data.append({'date': d, 'percentage': round(pct, 2)})

    recent_sessions = conn.execute('''
        SELECT date(s.started_at) as s_date, c.class_name,
               (SELECT COUNT(*) FROM attendance_records WHERE session_id = s.id) as rec_count,
               (SELECT COUNT(*) FROM enrollments WHERE class_id = c.id) as enr_count
        FROM attendance_sessions s
        JOIN classes c ON s.class_id = c.id
        WHERE c.teacher_id = ? AND s.status = 'ended'
        ORDER BY s.started_at DESC LIMIT 5
    ''', (teacher_id,)).fetchall()

    # student stats
    student_stats = []
    students_in_classes = conn.execute('''
        SELECT DISTINCT u.id, u.name, u.student_id, c.class_name, c.id as c_id
        FROM users u
        JOIN enrollments e ON u.id = e.student_id
        JOIN classes c ON e.class_id = c.id
        WHERE c.teacher_id = ?
        ORDER BY c.class_name, u.name
    ''', (teacher_id,)).fetchall()

    for st in students_in_classes:
        s_count = conn.execute('''
            SELECT COUNT(*) FROM attendance_sessions
            WHERE class_id = ? AND status = 'ended'
        ''', (st['c_id'],)).fetchone()[0]

        a_count = conn.execute('''
            SELECT COUNT(*) FROM attendance_records ar
            JOIN attendance_sessions s ON ar.session_id = s.id
            WHERE s.class_id = ? AND s.status = 'ended' AND ar.student_id = ?
        ''', (st['c_id'], st['id'])).fetchone()[0]

        pct = (a_count / s_count * 100) if s_count > 0 else None

        student_stats.append({
            'name': st['name'],
            'student_id': st['student_id'],
            'class_name': st['class_name'],
            'sessions': s_count,
            'attended': a_count,
            'percentage': pct
        })

    conn.close()

    return {
        'total_classes': total_classes,
        'total_students': len(total_students_set),
        'total_sessions': total_sessions,
        'total_records': total_records,
        'overall_percentage': overall_percentage,
        'class_stats': class_stats,
        'student_stats': student_stats,
        'trend_data': trend_data,
        'recent_sessions': recent_sessions
    }

def get_student_dashboard_stats(db_path, student_id):
    conn = get_db_connection(db_path)

    enrollments = conn.execute('''
        SELECT c.id, c.class_name, c.subject
        FROM classes c
        JOIN enrollments e ON c.id = e.class_id
        WHERE e.student_id = ?
    ''', (student_id,)).fetchall()

    total_classes = len(enrollments)
    total_sessions = 0
    total_attended = 0
    class_stats = []

    for c in enrollments:
        c_id = c['id']
        s_count = conn.execute('''
            SELECT COUNT(*) FROM attendance_sessions
            WHERE class_id = ? AND status = 'ended'
        ''', (c_id,)).fetchone()[0]
        total_sessions += s_count

        a_count = conn.execute('''
            SELECT COUNT(*) FROM attendance_records ar
            JOIN attendance_sessions s ON ar.session_id = s.id
            WHERE s.class_id = ? AND s.status = 'ended' AND ar.student_id = ?
        ''', (c_id, student_id)).fetchone()[0]
        total_attended += a_count

        pct = (a_count / s_count * 100) if s_count > 0 else None
        class_stats.append({
            'class_name': c['class_name'],
            'sessions': s_count,
            'attended': a_count,
            'percentage': pct
        })

    overall_pct = (total_attended / total_sessions * 100) if total_sessions > 0 else None

    history = conn.execute('''
        SELECT date(s.started_at) as s_date, c.class_name, ar.status
        FROM attendance_records ar
        JOIN attendance_sessions s ON ar.session_id = s.id
        JOIN classes c ON s.class_id = c.id
        WHERE ar.student_id = ? AND s.status = 'ended'
        ORDER BY s.started_at DESC LIMIT 10
    ''', (student_id,)).fetchall()

    trend_dict = {}
    all_s = conn.execute('''
        SELECT s.id, date(s.started_at) as s_date
        FROM attendance_sessions s
        JOIN enrollments e ON s.class_id = e.class_id
        WHERE e.student_id = ? AND s.status = 'ended'
    ''', (student_id,)).fetchall()

    for s in all_s:
        d = s['s_date']
        if d not in trend_dict:
            trend_dict[d] = {'cond': 0, 'att': 0}
        trend_dict[d]['cond'] += 1

        att = conn.execute('SELECT id FROM attendance_records WHERE session_id = ? AND student_id = ?', (s['id'], student_id)).fetchone()
        if att:
            trend_dict[d]['att'] += 1

    trend_data = []
    for d in sorted(trend_dict.keys()):
        cond = trend_dict[d]['cond']
        att = trend_dict[d]['att']
        pct = (att / cond * 100) if cond > 0 else 0
        trend_data.append({'date': d, 'percentage': round(pct, 2)})

    conn.close()

    return {
        'total_classes': total_classes,
        'total_sessions': total_sessions,
        'total_attended': total_attended,
        'overall_percentage': overall_pct,
        'class_stats': class_stats,
        'history': history,
        'trend_data': trend_data
    }

def get_teacher_report(db_path, teacher_id, class_id, start_date=None, end_date=None):
    conn = get_db_connection(db_path)

    # Verify ownership
    c = conn.execute('SELECT * FROM classes WHERE id = ? AND teacher_id = ?', (class_id, teacher_id)).fetchone()
    if not c:
        conn.close()
        return None

    date_filter = ""
    params = [class_id]
    if start_date:
        date_filter += " AND date(s.started_at) >= ?"
        params.append(start_date)
    if end_date:
        date_filter += " AND date(s.started_at) <= ?"
        params.append(end_date)

    # Get students in class
    students = conn.execute('''
        SELECT u.id, u.student_id, u.name
        FROM users u
        JOIN enrollments e ON u.id = e.student_id
        WHERE e.class_id = ?
        ORDER BY u.name
    ''', (class_id,)).fetchall()

    # Get total sessions in date range
    sessions = conn.execute(f'''
        SELECT id, started_at, session_code
        FROM attendance_sessions s
        WHERE class_id = ? AND status = 'ended' {date_filter}
        ORDER BY started_at
    ''', params).fetchall()

    s_ids = [s['id'] for s in sessions]

    student_stats = []
    total_records_class = 0
    total_opps = len(students) * len(sessions)

    for st in students:
        if not s_ids:
            a_count = 0
        else:
            placeholders = ','.join(['?']*len(s_ids))
            a_count = conn.execute(f'''
                SELECT COUNT(*) FROM attendance_records
                WHERE student_id = ? AND session_id IN ({placeholders})
            ''', [st['id']] + s_ids).fetchone()[0]

        total_records_class += a_count
        pct = (a_count / len(sessions) * 100) if sessions else None

        student_stats.append({
            'student_id': st['student_id'],
            'name': st['name'],
            'sessions': len(sessions),
            'present': a_count,
            'percentage': pct
        })

    session_stats = []
    for s in sessions:
        present = conn.execute('SELECT COUNT(*) FROM attendance_records WHERE session_id = ?', (s['id'],)).fetchone()[0]
        pct = (present / len(students) * 100) if students else None
        session_stats.append({
            'date': s['started_at'],
            'session_code': s['session_code'],
            'present': present,
            'total': len(students),
            'percentage': pct
        })

    overall_pct = (total_records_class / total_opps * 100) if total_opps > 0 else None

    conn.close()
    return {
        'class_info': c,
        'summary': {
            'students': len(students),
            'sessions': len(sessions),
            'total_records': total_records_class,
            'overall_percentage': overall_pct
        },
        'student_stats': student_stats,
        'session_stats': session_stats
    }

def get_student_report(db_path, student_id, class_id=None, start_date=None, end_date=None):
    conn = get_db_connection(db_path)

    # Base query for history
    query = '''
        SELECT date(s.started_at) as s_date, s.started_at, c.class_name, s.session_code, ar.status, s.id as session_id
        FROM attendance_sessions s
        JOIN classes c ON s.class_id = c.id
        JOIN enrollments e ON c.id = e.class_id
        LEFT JOIN attendance_records ar ON ar.session_id = s.id AND ar.student_id = e.student_id
        WHERE e.student_id = ? AND s.status = 'ended'
    '''
    params = [student_id]

    if class_id:
        query += " AND c.id = ?"
        params.append(class_id)
    if start_date:
        query += " AND date(s.started_at) >= ?"
        params.append(start_date)
    if end_date:
        query += " AND date(s.started_at) <= ?"
        params.append(end_date)

    query += " ORDER BY s.started_at DESC"

    history_raw = conn.execute(query, params).fetchall()

    history = []
    total_sessions = len(history_raw)
    total_present = 0

    for h in history_raw:
        st = h['status'] if h['status'] else 'absent'
        if st == 'present':
            total_present += 1
        history.append({
            'date': h['s_date'],
            'class_name': h['class_name'],
            'session': h['session_code'],
            'status': st
        })

    overall_pct = (total_present / total_sessions * 100) if total_sessions > 0 else None

    conn.close()
    return {
        'summary': {
            'sessions': total_sessions,
            'present': total_present,
            'overall_percentage': overall_pct
        },
        'history': history
    }

def upsert_face_embedding(db_path, student_id, embedding_bytes, model_name):
    conn = get_db_connection(db_path)
    try:
        conn.execute('''
            INSERT INTO face_embeddings (student_id, embedding, model_name, created_at, updated_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ON CONFLICT(student_id, model_name) DO UPDATE SET
                embedding = excluded.embedding,
                updated_at = CURRENT_TIMESTAMP
        ''', (student_id, embedding_bytes, model_name))
        conn.commit()
        return True
    except sqlite3.Error as e:
        return str(e)
    finally:
        conn.close()

def add_student_face_reference(db_path, student_id, image_path, embedding_bytes, quality_status):
    conn = get_db_connection(db_path)
    try:
        conn.execute('''
            INSERT INTO student_face_references (student_id, image_path, embedding, quality_status, created_at, updated_at)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        ''', (student_id, image_path, embedding_bytes, quality_status))
        conn.commit()
        return True
    except sqlite3.Error as e:
        return str(e)
    finally:
        conn.close()

def get_student_face_references(db_path, student_id):
    conn = get_db_connection(db_path)
    try:
        cursor = conn.execute('''
            SELECT id, image_path, quality_status, created_at
            FROM student_face_references
            WHERE student_id = ?
            ORDER BY created_at DESC
        ''', (student_id,))
        return [dict(row) for row in cursor.fetchall()]
    except Exception as e:
        return []
    finally:
        conn.close()

def get_student_face_reference_by_id(db_path, ref_id):
    conn = get_db_connection(db_path)
    try:
        row = conn.execute('SELECT * FROM student_face_references WHERE id = ?', (ref_id,)).fetchone()
        return dict(row) if row else None
    except Exception:
        return None
    finally:
        conn.close()

def delete_student_face_reference(db_path, ref_id):
    conn = get_db_connection(db_path)
    try:
        conn.execute('DELETE FROM student_face_references WHERE id = ?', (ref_id,))
        conn.commit()
        return True
    except sqlite3.Error as e:
        return str(e)
    finally:
        conn.close()


def get_all_face_embeddings(db_path, model_name='sface_2021dec'):
    conn = get_db_connection(db_path)
    try:
        # Get from face_embeddings (legacy profile pictures)
        cursor1 = conn.execute('''
            SELECT fe.student_id as user_id, u.student_id as school_id, u.name, fe.embedding
            FROM face_embeddings fe
            JOIN users u ON fe.student_id = u.id
            WHERE fe.model_name = ?
        ''', (model_name,))
        rows = cursor1.fetchall()

        # Get from new student_face_references
        cursor2 = conn.execute('''
            SELECT sfr.student_id as user_id, u.student_id as school_id, u.name, sfr.embedding
            FROM student_face_references sfr
            JOIN users u ON sfr.student_id = u.id
        ''')
        rows.extend(cursor2.fetchall())

        result = []
        for r in rows:
            result.append({
                'user_id': r['user_id'],
                'student_id': r['school_id'],
                'student_name': r['name'],
                'embedding': r['embedding']
            })
        return result
    except Exception as e:
        return []
    finally:
        conn.close()

def mark_photo_attendance(db_path, session_id, eligible_students):
    conn = get_db_connection(db_path)
    result = {
        'marked_count': 0,
        'already_present_count': 0,
        'error': None
    }

    try:
        conn.execute('BEGIN TRANSACTION')
        for student in eligible_students:
            sid = student['user_id']
            sim = student.get('similarity')
            # Check existing
            row = conn.execute('SELECT id FROM attendance_records WHERE session_id = ? AND student_id = ?', (session_id, sid)).fetchone()
            if row:
                result['already_present_count'] += 1
            else:
                conn.execute('''
                    INSERT INTO attendance_records (session_id, student_id, attendance_source, similarity)
                    VALUES (?, ?, 'classroom_photo', ?)
                ''', (session_id, sid, sim))
                result['marked_count'] += 1
        conn.commit()
        return result
    except Exception as e:
        conn.rollback()
        result['error'] = str(e)
        return result
    finally:
        conn.close()
