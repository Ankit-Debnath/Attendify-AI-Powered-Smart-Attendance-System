import unittest
import os
from app import app
from database.database import init_db, get_db_connection
from tests.csrf_wrapper import CSRFTestClient
from werkzeug.security import generate_password_hash
import uuid

class Phase11_5_3_TestCase(unittest.TestCase):
    def setUp(self):
        app.config['TESTING'] = True
        self.db_path = os.path.join(app.root_path, 'database', f'test_attendance_p11_5_3_{uuid.uuid4().hex}.db')
        app.config['DATABASE'] = self.db_path
        
        self.client = CSRFTestClient(app.test_client())
        init_db(app.config['DATABASE'])
        
        conn = get_db_connection(app.config['DATABASE'])
        hashed_pw = generate_password_hash("password")
        
        # Teacher and student
        conn.execute('INSERT INTO users (name, email, password_hash, role) VALUES (?, ?, ?, ?)', ("Teacher", "teacher@example.com", hashed_pw, "teacher"))
        conn.execute('INSERT INTO users (name, email, password_hash, role, student_id) VALUES (?, ?, ?, ?, ?)', ("Student", "student@example.com", hashed_pw, "student", "S100"))
        
        # Class and enrollment
        conn.execute('INSERT INTO classes (class_name, subject, course, semester, class_code, teacher_id) VALUES (?, ?, ?, ?, ?, ?)', ("Class A", "Sub A", "C1", "1", "CODEA", 1))
        conn.execute('INSERT INTO enrollments (class_id, student_id) VALUES (?, ?)', (1, 2))
        
        # Attendance Session
        conn.execute('INSERT INTO attendance_sessions (class_id, session_code, expires_at, status) VALUES (?, ?, datetime("now", "+1 hour"), "active")', (1, "SESS_A"))
        
        conn.commit()
        conn.close()
        
    def tearDown(self):
        if os.path.exists(app.config['DATABASE']):
            try:
                os.remove(app.config['DATABASE'])
            except:
                pass

    def login_teacher(self):
        return self.client.post('/login', data=dict(email='teacher@example.com', password='password'), follow_redirects=True)

    def login_student(self):
        return self.client.post('/login', data=dict(email='student@example.com', password='password'), follow_redirects=True)

    def test_01_teacher_can_access_photo_attendance_page(self):
        self.login_teacher()
        rv = self.client.get('/teacher/classes/1/attendance/1/photo')
        self.assertEqual(rv.status_code, 200)
        self.assertIn(b"Classroom Photo Attendance", rv.data)
        self.assertIn(b"Upload a clear photograph", rv.data)

    def test_02_student_cannot_access_it(self):
        self.login_student()
        rv = self.client.get('/teacher/classes/1/attendance/1/photo')
        self.assertEqual(rv.status_code, 302) # Redirect due to role_required

    def test_03_unauthenticated_user_cannot_access(self):
        rv = self.client.get('/teacher/classes/1/attendance/1/photo')
        self.assertEqual(rv.status_code, 302) # Redirect to login

    def test_04_upload_page_contains_correct_form(self):
        self.login_teacher()
        rv = self.client.get('/teacher/classes/1/attendance/1/photo')
        self.assertIn(b'id="photo-attendance-form"', rv.data)
        self.assertIn(b'type="file"', rv.data)
        self.assertIn(b'accept=".jpg, .jpeg, .png, .webp"', rv.data)
        self.assertIn(b'csrf_token', rv.data)

    def test_05_csrf_protection_remains_active(self):
        self.login_teacher()
        # Direct POST to the backend API should be rejected without CSRF if testing without wrapper
        client_no_csrf = app.test_client()
        # Note: We need a cookie to be authenticated for the POST, let's login on normal client
        client_no_csrf.post('/login', data=dict(email='teacher@example.com', password='password'))
        
        rv = client_no_csrf.post('/teacher/classes/1/attendance/1/recognize', data={})
        self.assertEqual(rv.status_code, 400) # Bad Request due to missing CSRF token

    def test_12_existing_attendance_page_remains_functional(self):
        self.login_teacher()
        rv = self.client.get('/teacher/attendance/1')
        self.assertEqual(rv.status_code, 200)
        # Should have the new button
        self.assertIn(b"Classroom Photo Attendance", rv.data)
        self.assertIn(b"End Session Now", rv.data)

    def test_13_existing_normal_attendance_workflow_unchanged(self):
        # A student should be able to check in manually
        self.login_student()
        rv = self.client.post('/student/attendance/checkin/SESS_A', data=dict(session_code='SESS_A'))
        self.assertEqual(rv.status_code, 302)
        
        # Verify attendance record was created
        conn = get_db_connection(app.config['DATABASE'])
        records = conn.execute('SELECT * FROM attendance_records WHERE session_id = 1').fetchall()
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]['student_id'], 2)
        conn.close()

if __name__ == '__main__':
    unittest.main(verbosity=2)
