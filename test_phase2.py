from tests.csrf_wrapper import CSRFTestClient
import unittest
from app import app
from database.database import init_db
import os

class Phase2TestCase(unittest.TestCase):
    def setUp(self):
        app.config['TESTING'] = True
        app.config['DATABASE'] = os.path.join(app.root_path, 'database', 'test_attendance.db')
        self.client = CSRFTestClient(app.test_client())
        init_db(app.config['DATABASE'])

    def tearDown(self):
        if os.path.exists(app.config['DATABASE']):
            os.remove(app.config['DATABASE'])

    def test_01_teacher_registration_valid(self):
        rv = self.client.post('/register/teacher', data=dict(
            name='Teacher John', email='john@example.com', password='password', confirm_password='password',
            subject='Math', department='Science'
        ), follow_redirects=True)
        self.assertIn(b'Teacher registered successfully', rv.data)

    def test_02_student_registration_valid(self):
        rv = self.client.post('/register/student', data=dict(
            name='Student Alice', email='alice@example.com', password='password', confirm_password='password',
            student_id='S100', course='BTech', semester='1'
        ), follow_redirects=True)
        self.assertIn(b'Student registered successfully', rv.data)

    def test_03_duplicate_email(self):
        self.client.post('/register/teacher', data=dict(
            name='T1', email='dup@example.com', password='password', confirm_password='password',
            subject='A', department='B'
        ))
        rv = self.client.post('/register/student', data=dict(
            name='S1', email='dup@example.com', password='password', confirm_password='password',
            student_id='S200', course='C', semester='1'
        ), follow_redirects=True)
        self.assertIn(b'Email already registered', rv.data)

    def test_04_duplicate_student_id(self):
        self.client.post('/register/student', data=dict(
            name='S1', email='s1@example.com', password='password', confirm_password='password',
            student_id='DUP123', course='C', semester='1'
        ))
        rv = self.client.post('/register/student', data=dict(
            name='S2', email='s2@example.com', password='password', confirm_password='password',
            student_id='DUP123', course='C', semester='1'
        ), follow_redirects=True)
        self.assertIn(b'Student ID already registered', rv.data)

    def test_05_password_mismatch(self):
        rv = self.client.post('/register/teacher', data=dict(
            name='T', email='t@example.com', password='password1', confirm_password='password2',
            subject='S', department='D'
        ), follow_redirects=True)
        self.assertIn(b'Passwords do not match', rv.data)

    def test_06_teacher_login_correct(self):
        self.client.post('/register/teacher', data=dict(
            name='T', email='t@example.com', password='password', confirm_password='password',
            subject='S', department='D'
        ))
        rv = self.client.post('/login', data=dict(email='t@example.com', password='password'), follow_redirects=True)
        self.assertIn(b'Total Classes', rv.data)

    def test_07_student_login_correct(self):
        self.client.post('/register/student', data=dict(
            name='S', email='s@example.com', password='password', confirm_password='password',
            student_id='123', course='BSc', semester='1'
        ))
        rv = self.client.post('/login', data=dict(email='s@example.com', password='password'), follow_redirects=True)
        self.assertIn(b'Dashboard', rv.data)

    def test_08_incorrect_password(self):
        self.client.post('/register/student', data=dict(
            name='S', email='s@example.com', password='password', confirm_password='password',
            student_id='S999', course='C', semester='1'
        ))
        rv = self.client.post('/login', data=dict(email='s@example.com', password='wrongpassword'), follow_redirects=True)
        self.assertIn(b'Invalid email or password', rv.data)

    def test_09_logout(self):
        self.client.post('/register/student', data=dict(
            name='S', email='s@example.com', password='password', confirm_password='password',
            student_id='S999', course='C', semester='1'
        ))
        self.client.post('/login', data=dict(email='s@example.com', password='password'))
        rv = self.client.get('/logout', follow_redirects=True)
        self.assertIn(b'You have been logged out', rv.data)
        
        # Verify can't access dashboard
        rv2 = self.client.get('/student/dashboard', follow_redirects=True)
        self.assertIn(b'Please log in to access this page', rv2.data)

    def test_10_unauthenticated_teacher_dashboard(self):
        rv = self.client.get('/teacher/dashboard', follow_redirects=True)
        self.assertIn(b'Please log in to access this page', rv.data)

    def test_11_unauthenticated_student_dashboard(self):
        rv = self.client.get('/student/dashboard', follow_redirects=True)
        self.assertIn(b'Please log in to access this page', rv.data)

    def test_12_student_accessing_teacher_dashboard(self):
        self.client.post('/register/student', data=dict(
            name='S', email='s@example.com', password='password', confirm_password='password',
            student_id='S999', course='C', semester='1'
        ))
        self.client.post('/login', data=dict(email='s@example.com', password='password'))
        rv = self.client.get('/teacher/dashboard', follow_redirects=True)
        self.assertIn(b'Unauthorized access', rv.data)
        self.assertIn(b'Dashboard', rv.data) # Should redirect to student dashboard

    def test_13_teacher_accessing_student_dashboard(self):
        self.client.post('/register/teacher', data=dict(
            name='T', email='t@example.com', password='password', confirm_password='password',
            subject='S', department='D'
        ))
        self.client.post('/login', data=dict(email='t@example.com', password='password'))
        rv = self.client.get('/student/dashboard', follow_redirects=True)
        self.assertIn(b'Unauthorized access', rv.data)
        self.assertIn(b'Total Classes', rv.data) # Should redirect to teacher dashboard

if __name__ == '__main__':
    unittest.main(verbosity=2)
