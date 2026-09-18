import unittest
import os
import io
import re
from app import app
from database.database import init_db, get_db_connection
from tests.csrf_wrapper import CSRFTestClient

def get_lena_bytes():
    with open("tests/temp/lena.jpg", "rb") as f:
        return f.read()

class Phase4TestCase(unittest.TestCase):
    def setUp(self):
        app.config['TESTING'] = True
        app.config['DATABASE'] = os.path.join(app.root_path, 'database', 'test_attendance_p4.db')
        
        self.client = CSRFTestClient(app.test_client())
        init_db(app.config['DATABASE'])
        
        # Register a teacher and a student
        self.client.post('/register/teacher', data=dict(
            name='T1', email='t1@example.com', password='password', confirm_password='password',
            subject='S1', department='D1'
        ))
        self.client.post('/register/student', data=dict(
            name='S1', email='s1@example.com', password='password', confirm_password='password',
            student_id='S100', course='C1', semester='1'
        ))

    def tearDown(self):
        if os.path.exists(app.config['DATABASE']):
            try:
                os.remove(app.config['DATABASE'])
            except:
                pass
                
    def login_teacher(self):
        return self.client.post('/login', data=dict(email='t1@example.com', password='password'), follow_redirects=True)
        
    def login_student(self):
        return self.client.post('/login', data=dict(email='s1@example.com', password='password'), follow_redirects=True)

    def test_01_student_profile_requires_login(self):
        rv = self.client.get('/student/profile', follow_redirects=True)
        self.assertIn(b'Please log in to access this page', rv.data)

    def test_02_teacher_cannot_access_student_profile(self):
        self.login_teacher()
        rv = self.client.get('/student/profile', follow_redirects=True)
        self.assertIn(b'Unauthorized access', rv.data)
        
    def test_03_student_can_access_own_profile(self):
        self.login_student()
        rv = self.client.get('/student/profile')
        self.assertIn(b'S1', rv.data)
        self.assertIn(b'C1', rv.data)

    def test_04_to_07_student_edit_profile(self):
        self.login_student()
        rv = self.client.post('/student/profile/edit', data=dict(
            name='S1 Edited',
            course='C1 Edited',
            semester='2'
        ), follow_redirects=True)
        self.assertIn(b'Profile updated successfully', rv.data)
        
        conn = get_db_connection(app.config['DATABASE'])
        user = conn.execute('SELECT * FROM users WHERE email = ?', ('s1@example.com',)).fetchone()
        conn.close()
        self.assertEqual(user['name'], 'S1 Edited')
        self.assertEqual(user['course'], 'C1 Edited')
        self.assertEqual(user['semester'], '2')

    def test_08_edit_profile_requires_login(self):
        rv = self.client.post('/student/profile/edit', data=dict(name='A', course='B', semester='1'), follow_redirects=True)
        self.assertIn(b'Please log in to access this page', rv.data)

    def test_09_teacher_cannot_edit_student_profile(self):
        self.login_teacher()
        rv = self.client.post('/student/profile/edit', data=dict(name='A', course='B', semester='1'), follow_redirects=True)
        self.assertIn(b'Unauthorized access', rv.data)

    def test_10_student_edit_profile_missing_fields(self):
        self.login_student()
        rv = self.client.post('/student/profile/edit', data=dict(
            name='',
            course='',
            semester=''
        ), follow_redirects=True)
        
        self.assertIn(b'Name, Course, and Semester are required.', rv.data)

    def test_11_upload_valid_image(self):
        self.login_student()
        data = {
            'name': 'S1', 'course': 'C1', 'semester': '1',
            'profile_picture': (io.BytesIO(get_lena_bytes()), 'test.jpg')
        }
        rv = self.client.post('/student/profile/edit', data=data, content_type='multipart/form-data', follow_redirects=True)
        self.assertIn(b'Profile updated successfully', rv.data)
        
    def test_12_upload_invalid_image(self):
        self.login_student()
        data = {
            'name': 'S1', 'course': 'C1', 'semester': '1',
            'profile_picture': (io.BytesIO(b"fake script"), 'test.txt')
        }
        rv = self.client.post('/student/profile/edit', data=data, content_type='multipart/form-data', follow_redirects=True)
        self.assertIn(b'Invalid image format', rv.data)

    def test_13_upload_oversized_image(self):
        self.login_student()
        # 3MB data
        large_data = b"0" * (3 * 1024 * 1024)
        data = {
            'name': 'S1', 'course': 'C1', 'semester': '1',
            'profile_picture': (io.BytesIO(large_data), 'test.jpg')
        }
        rv = self.client.post('/student/profile/edit', data=data, content_type='multipart/form-data', follow_redirects=True)
        self.assertEqual(rv.status_code, 413)

    def test_14_remove_profile_image(self):
        self.login_student()
        # First upload
        data = {
            'name': 'S1', 'course': 'C1', 'semester': '1',
            'profile_picture': (io.BytesIO(get_lena_bytes()), 'test1.jpg')
        }
        self.client.post('/student/profile/edit', data=data, content_type='multipart/form-data', follow_redirects=True)
        
        # Now remove
        rv = self.client.post('/student/profile/picture/remove', follow_redirects=True)
        self.assertIn(b'Profile picture removed', rv.data)
        
    def test_15_student_dashboard_requires_login(self):
        rv = self.client.get('/student/dashboard', follow_redirects=True)
        self.assertIn(b'Please log in to access this page', rv.data)

if __name__ == '__main__':
    unittest.main(verbosity=2)
