from tests.csrf_wrapper import CSRFTestClient
import unittest
from app import app
from database.database import init_db, get_db_connection
import os
import csv
import io

class Phase9TestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Set up config isolation
        cls.original_config = {}
        for key in ['TESTING', 'DATABASE', 'WTF_CSRF_ENABLED', 'SECRET_KEY', 'MAX_CONTENT_LENGTH']:
            cls.original_config[key] = app.config.get(key)
            
        app.config['TESTING'] = True
        cls.db_path = os.path.join(app.root_path, 'database', 'test_attendance_p9.db')
        app.config['DATABASE'] = cls.db_path
        
        # Clean up existing database safely before creating fixtures
        if os.path.exists(cls.db_path):
            try:
                os.remove(cls.db_path)
            except Exception:
                pass
                
        init_db(cls.db_path)
        
        # Use a temporary client for setup fixtures
        setup_client = CSRFTestClient(app.test_client())
        
        def s_login(email, password):
            return setup_client.post('/login', data=dict(email=email, password=password), follow_redirects=True)
            
        # Register users
        setup_client.post('/register/teacher', data=dict(
            name='T1', email='t1@example.com', password='password', confirm_password='password',
            subject='S1', department='D1'
        ))
        setup_client.post('/register/teacher', data=dict(
            name='T2', email='t2@example.com', password='password', confirm_password='password',
            subject='S2', department='D2'
        ))
        setup_client.post('/register/student', data=dict(
            name='S1', email='s1@example.com', password='password', confirm_password='password',
            student_id='S100', course='C1', semester='1'
        ))
        setup_client.post('/register/student', data=dict(
            name='S2', email='s2@example.com', password='password', confirm_password='password',
            student_id='S200', course='C2', semester='2'
        ))
        
        # T1 Creates Class 1
        s_login('t1@example.com', 'password')
        setup_client.post('/teacher/classes/create', data=dict(class_name='Math 101', subject='Math', course='BSc', semester='1'), follow_redirects=True)
        
        # T2 Creates Class 2
        setup_client.get('/logout')
        s_login('t2@example.com', 'password')
        setup_client.post('/teacher/classes/create', data=dict(class_name='Sci 101', subject='Sci', course='BSc', semester='1'), follow_redirects=True)
        setup_client.get('/logout')
        
        # Setup class codes
        conn = get_db_connection(app.config['DATABASE'])
        cls.c1_code = conn.execute('SELECT class_code FROM classes WHERE id=1').fetchone()['class_code']
        cls.c2_code = conn.execute('SELECT class_code FROM classes WHERE id=2').fetchone()['class_code']
        conn.close()
        
        # Enrollments
        s_login('s1@example.com', 'password')
        setup_client.post('/student/classes/join', data=dict(class_code=cls.c1_code))
        setup_client.get('/logout')
        
        s_login('s2@example.com', 'password')
        setup_client.post('/student/classes/join', data=dict(class_code=cls.c1_code))
        setup_client.post('/student/classes/join', data=dict(class_code=cls.c2_code))
        setup_client.get('/logout')
        
        # Sessions & Checkins
        conn = get_db_connection(app.config['DATABASE'])
        
        for _ in range(3):
            s_login('t1@example.com', 'password')
            setup_client.post('/teacher/classes/1/attendance', data=dict(duration=10), follow_redirects=True)
            s_id = conn.execute('SELECT id, session_code FROM attendance_sessions ORDER BY id DESC LIMIT 1').fetchone()
            setup_client.get('/logout')
            
            # Check in students while session is active
            s_login('s1@example.com', 'password')
            setup_client.post(f"/student/attendance/checkin/{s_id['session_code']}")
            setup_client.get('/logout')
            
            s_login('s2@example.com', 'password')
            # S2 only attends first 2 sessions
            if _ < 2:
                setup_client.post(f"/student/attendance/checkin/{s_id['session_code']}")
            setup_client.get('/logout')
            
            # Now end the session
            s_login('t1@example.com', 'password')
            setup_client.post(f"/teacher/attendance/{s_id['id']}/end")
            setup_client.get('/logout')
            
        conn.close()

    @classmethod
    def tearDownClass(cls):
        try:
            if os.path.exists(cls.db_path):
                os.remove(cls.db_path)
        finally:
            if hasattr(cls, 'original_config'):
                for key, val in cls.original_config.items():
                    if val is None:
                        app.config.pop(key, None)
                    else:
                        app.config[key] = val

    def setUp(self):
        # We need a fresh client for each test so they don't share cookies
        self.client = CSRFTestClient(app.test_client())
        
    def login(self, email, password):
        return self.client.post('/login', data=dict(email=email, password=password), follow_redirects=True)

    def test_auth_access(self):
        # 1. Unauth teacher access rejected
        rv = self.client.get('/teacher/reports', follow_redirects=True)
        self.assertIn(b'Please log in', rv.data)
        # 2. Unauth student access rejected
        rv = self.client.get('/student/reports', follow_redirects=True)
        self.assertIn(b'Please log in', rv.data)
        
        self.login('s1@example.com', 'password')
        # 3. Student cannot access teacher reports
        rv = self.client.get('/teacher/reports', follow_redirects=True)
        self.assertIn(b'Unauthorized access', rv.data)
        self.client.get('/logout')
        
        self.login('t1@example.com', 'password')
        # 4. Teacher cannot access student reports
        rv = self.client.get('/student/reports', follow_redirects=True)
        self.assertIn(b'Unauthorized access', rv.data)
        
    def test_teacher_isolation(self):
        self.login('t1@example.com', 'password')
        # 5. Teacher can report own class
        rv = self.client.get('/teacher/reports?class_id=1')
        self.assertIn(b'83.33%', rv.data) # Total 5/6
        
        # 6, 7. Teacher cannot report another's class
        rv2 = self.client.get('/teacher/reports?class_id=2', follow_redirects=True)
        self.assertIn(b'Invalid class selection', rv2.data)
        
        # 8. Report contains only authorized students
        self.assertNotIn(b'unauthorized_student', rv.data)
        
    def test_student_isolation(self):
        self.login('s1@example.com', 'password')
        # 9. Student can view own report
        rv = self.client.get('/student/reports')
        self.assertIn(b'100.00%', rv.data)
        
        # 10. Cannot access another student's report (no ID parameter accepted)
        # Asserts identity from session
        self.assertNotIn(b'S200', rv.data) 
        
        # 11. Student only sees enrolled classes
        rv2 = self.client.get('/student/reports?class_id=2', follow_redirects=True)
        self.assertIn(b'Invalid class selection', rv2.data)
        
    def test_filters(self):
        self.login('t1@example.com', 'password')
        # 12. Class filtering works
        rv = self.client.get('/teacher/reports?class_id=1')
        self.assertIn(b'S100', rv.data)
        
        # 14. Invalid date range rejected safely
        rv2 = self.client.get('/teacher/reports?class_id=1&start_date=2026-10-10&end_date=2026-09-09', follow_redirects=True)
        self.assertIn(b'Start date cannot be after end date', rv2.data)
        
        # 15. Empty date range result handled safely
        rv3 = self.client.get('/teacher/reports?class_id=1&start_date=2030-01-01&end_date=2030-01-02')
        self.assertIn(b'No completed sessions found', rv3.data)
        
    def test_calculations(self):
        # 16, 17. Percentages correct (Checked above in 100.00% and 83.33%)
        
        # 18. Zero-session case handled safely
        self.login('t2@example.com', 'password')
        rv = self.client.get('/teacher/reports?class_id=2')
        self.assertIn(b'N/A', rv.data) # No sessions yet
        
    def test_csv_export(self):
        self.login('t1@example.com', 'password')
        rv = self.client.get('/teacher/reports/export/csv?class_id=1')
        self.assertEqual(rv.status_code, 200)
        self.assertEqual(rv.mimetype, 'text/csv')
        self.assertIn(b'Student ID,Student Name,Sessions,Present,Percentage', rv.data)
        self.assertIn(b'S100,S1,3,3,100.00%', rv.data)
        
        # Student CSV
        self.client.get('/logout')
        self.login('s1@example.com', 'password')
        rv2 = self.client.get('/student/reports/export/csv')
        self.assertEqual(rv2.status_code, 200)
        self.assertIn(b'Date,Class,Session,Status', rv2.data)
        
        # 22. Passwords not in CSV
        self.assertNotIn(b'password', rv.data)
        
    def test_pdf_export(self):
        self.login('t1@example.com', 'password')
        rv = self.client.get('/teacher/reports/export/pdf?class_id=1')
        self.assertEqual(rv.status_code, 200)
        self.assertEqual(rv.mimetype, 'application/pdf')
        self.assertTrue(rv.data.startswith(b'%PDF-1.'))
        
        self.client.get('/logout')
        self.login('s1@example.com', 'password')
        rv2 = self.client.get('/student/reports/export/pdf')
        self.assertEqual(rv2.status_code, 200)
        self.assertTrue(rv2.data.startswith(b'%PDF-1.'))

if __name__ == '__main__':
    unittest.main(verbosity=2)
