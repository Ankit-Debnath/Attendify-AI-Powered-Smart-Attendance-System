from tests.csrf_wrapper import CSRFTestClient
import unittest
from app import app
from database.database import init_db
import os
import io

class DeletionTestCase(unittest.TestCase):
    def setUp(self):
        app.config['TESTING'] = True
        app.config['DATABASE'] = os.path.join(app.root_path, 'database', 'test_attendance_del.db')
        self.client = CSRFTestClient(app.test_client())
        init_db(app.config['DATABASE'])
        
        # Register users
        self.client.post('/register/teacher', data=dict(
            name='T1', email='t1@example.com', password='password', confirm_password='password',
            subject='S1', department='D1'
        ))
        self.client.post('/register/teacher', data=dict(
            name='T2', email='t2@example.com', password='password', confirm_password='password',
            subject='S2', department='D2'
        ))
        self.client.post('/register/student', data=dict(
            name='S1', email='s1@example.com', password='password', confirm_password='password',
            student_id='S100', course='C1', semester='1'
        ))
        self.client.post('/register/student', data=dict(
            name='S2', email='s2@example.com', password='password', confirm_password='password',
            student_id='S200', course='C2', semester='2'
        ))

    def tearDown(self):
        if os.path.exists(app.config['DATABASE']):
            os.remove(app.config['DATABASE'])
            
    def test_01_unauthenticated_cannot_delete(self):
        rv1 = self.client.post('/teacher/account/delete', follow_redirects=True)
        self.assertIn(b'Please log in to access this page', rv1.data)
        
        rv2 = self.client.post('/student/account/delete', follow_redirects=True)
        self.assertIn(b'Please log in to access this page', rv2.data)

    def test_02_student_can_delete_own_account_and_not_affect_others(self):
        # Add profile picture
        self.client.post('/login', data=dict(email='s1@example.com', password='password'))
        data = {
            'name': 'S1', 'course': 'C1', 'semester': '1',
            'profile_picture': (io.BytesIO(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"), 'test.jpg')
        }
        self.client.post('/student/profile/edit', data=data, content_type='multipart/form-data')
        
        # Delete account
        rv = self.client.post('/student/account/delete', follow_redirects=True)
        self.assertIn(b'Your account has been permanently deleted', rv.data)
        
        # Verify can't login
        rv_login = self.client.post('/login', data=dict(email='s1@example.com', password='password'), follow_redirects=True)
        self.assertIn(b'Invalid email or password', rv_login.data)
        
        # Verify other student still exists
        rv_other = self.client.post('/login', data=dict(email='s2@example.com', password='password'), follow_redirects=True)
        self.assertIn(b'Dashboard', rv_other.data)

    def test_03_teacher_can_delete_own_account_and_not_affect_others(self):
        self.client.post('/login', data=dict(email='t1@example.com', password='password'))
        
        rv = self.client.post('/teacher/account/delete', follow_redirects=True)
        self.assertIn(b'Your account has been permanently deleted', rv.data)
        
        rv_login = self.client.post('/login', data=dict(email='t1@example.com', password='password'), follow_redirects=True)
        self.assertIn(b'Invalid email or password', rv_login.data)
        
        rv_other = self.client.post('/login', data=dict(email='t2@example.com', password='password'), follow_redirects=True)
        self.assertIn(b'Total Classes', rv_other.data)

    def test_04_get_request_cannot_delete(self):
        self.client.post('/login', data=dict(email='t1@example.com', password='password'))
        rv = self.client.get('/teacher/account/delete', follow_redirects=True)
        self.assertEqual(rv.status_code, 405) # Method Not Allowed

if __name__ == '__main__':
    unittest.main(verbosity=2)
