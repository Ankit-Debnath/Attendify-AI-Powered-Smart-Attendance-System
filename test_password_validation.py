import unittest
import os
from app import app
from database.database import init_db
from tests.csrf_wrapper import CSRFTestClient

class PasswordValidationTestCase(unittest.TestCase):
    def setUp(self):
        app.config['TESTING'] = True
        app.config['DATABASE'] = os.path.join(app.root_path, 'database', 'test_password.db')
        self.client = CSRFTestClient(app.test_client())
        init_db(app.config['DATABASE'])

    def tearDown(self):
        if os.path.exists(app.config['DATABASE']):
            os.remove(app.config['DATABASE'])

    def test_01_teacher_short_password_rejected(self):
        rv = self.client.post('/register/teacher', data=dict(
            name='T1', email='t1@example.com',
            password='short', confirm_password='short',
            subject='Math', department='Science'
        ))
        self.assertIn(b'Password must be at least 8 characters long', rv.data)
        
    def test_02_teacher_empty_whitespace_password_rejected(self):
        rv = self.client.post('/register/teacher', data=dict(
            name='T1', email='t1@example.com',
            password='        ', confirm_password='        ',
            subject='Math', department='Science'
        ))
        self.assertIn(b'Password must be at least 8 characters long', rv.data)

    def test_03_teacher_valid_password_accepted(self):
        rv = self.client.post('/register/teacher', data=dict(
            name='T1', email='t1@example.com',
            password='validpassword123', confirm_password='validpassword123',
            subject='Math', department='Science'
        ), follow_redirects=True)
        self.assertIn(b'Teacher registered successfully', rv.data)
        
        # Verify it's actually hashed
        from database.database import get_user_by_email
        user = get_user_by_email(app.config['DATABASE'], 't1@example.com')
        self.assertNotEqual(user['password_hash'], 'validpassword123')
        self.assertTrue(user['password_hash'].startswith('scrypt:') or user['password_hash'].startswith('pbkdf2:'))

    def test_04_student_short_password_rejected(self):
        rv = self.client.post('/register/student', data=dict(
            name='S1', email='s1@example.com',
            password='short', confirm_password='short',
            student_id='S100', course='CS', semester='1'
        ))
        self.assertIn(b'Password must be at least 8 characters long', rv.data)

    def test_05_student_valid_password_accepted(self):
        rv = self.client.post('/register/student', data=dict(
            name='S1', email='s1@example.com',
            password='validpassword123', confirm_password='validpassword123',
            student_id='S100', course='CS', semester='1'
        ), follow_redirects=True)
        self.assertIn(b'Student registered successfully', rv.data)

if __name__ == '__main__':
    unittest.main()
