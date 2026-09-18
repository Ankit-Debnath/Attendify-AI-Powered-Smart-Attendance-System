from tests.csrf_wrapper import CSRFTestClient
import unittest
from app import app
from database.database import init_db
import os
import io

class Phase3TestCase(unittest.TestCase):
    def setUp(self):
        app.config['TESTING'] = True
        app.config['DATABASE'] = os.path.join(app.root_path, 'database', 'test_attendance_p3.db')
        self.client = CSRFTestClient(app.test_client())
        init_db(app.config['DATABASE'])
        
        # Register a teacher and a student for tests
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
            os.remove(app.config['DATABASE'])
            
    def login_teacher(self):
        return self.client.post('/login', data=dict(email='t1@example.com', password='password'), follow_redirects=True)
        
    def login_student(self):
        return self.client.post('/login', data=dict(email='s1@example.com', password='password'), follow_redirects=True)

    def test_01_teacher_dashboard(self):
        rv = self.login_teacher()
        self.assertIn(b'Total Classes', rv.data)
        self.assertIn(b'Total Students', rv.data)
        self.assertIn(b'Good morning, T1', rv.data)

    def test_02_student_cannot_access_teacher_profile(self):
        self.login_student()
        rv = self.client.get('/teacher/profile', follow_redirects=True)
        self.assertIn(b'Unauthorized access', rv.data)
        
    def test_03_teacher_view_profile(self):
        self.login_teacher()
        rv = self.client.get('/teacher/profile')
        self.assertIn(b'T1', rv.data)
        self.assertIn(b'S1', rv.data)

    def test_04_to_07_teacher_edit_profile(self):
        self.login_teacher()
        rv = self.client.post('/teacher/profile/edit', data=dict(
            name='T1 Edited',
            subject='S1 Edited',
            department='D1 Edited'
            # Note: email is not sent, it's disabled in form, test that it wasn't overwritten
        ), follow_redirects=True)
        
        self.assertIn(b'Profile updated successfully', rv.data)
        
        # Verify changes
        rv = self.client.get('/teacher/profile')
        self.assertIn(b'T1 Edited', rv.data)
        self.assertIn(b'S1 Edited', rv.data)
        self.assertIn(b'D1 Edited', rv.data)
        self.assertIn(b't1@example.com', rv.data) # Email remained intact

    def test_08_upload_valid_image(self):
        self.login_teacher()
        data = {
            'name': 'T1', 'subject': 'S1', 'department': 'D1',
            'profile_picture': (io.BytesIO(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"), 'test.jpg')
        }
        rv = self.client.post('/teacher/profile/edit', data=data, content_type='multipart/form-data', follow_redirects=True)
        self.assertIn(b'Profile updated successfully', rv.data)
        
    def test_09_upload_invalid_image(self):
        self.login_teacher()
        data = {
            'name': 'T1', 'subject': 'S1', 'department': 'D1',
            'profile_picture': (io.BytesIO(b"fake script"), 'test.txt')
        }
        rv = self.client.post('/teacher/profile/edit', data=data, content_type='multipart/form-data', follow_redirects=True)
        self.assertIn(b'Invalid image format', rv.data)

    def test_10_upload_oversized_image(self):
        self.login_teacher()
        # 3MB data
        large_data = b"0" * (3 * 1024 * 1024)
        data = {
            'name': 'T1', 'subject': 'S1', 'department': 'D1',
            'profile_picture': (io.BytesIO(large_data), 'test.jpg')
        }
        rv = self.client.post('/teacher/profile/edit', data=data, content_type='multipart/form-data', follow_redirects=True)
        # Flask intercepts this and throws 413 Request Entity Too Large
        self.assertEqual(rv.status_code, 413)

    def test_11_replace_profile_image(self):
        self.login_teacher()
        # First upload
        data = {
            'name': 'T1', 'subject': 'S1', 'department': 'D1',
            'profile_picture': (io.BytesIO(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"), 'test1.png')
        }
        self.client.post('/teacher/profile/edit', data=data, content_type='multipart/form-data', follow_redirects=True)
        
        # Second upload
        data2 = {
            'name': 'T1', 'subject': 'S1', 'department': 'D1',
            'profile_picture': (io.BytesIO(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"), 'test2.png')
        }
        rv = self.client.post('/teacher/profile/edit', data=data2, content_type='multipart/form-data', follow_redirects=True)
        self.assertIn(b'Profile updated successfully', rv.data)

    def test_12_remove_profile_image(self):
        self.login_teacher()
        # First upload
        data = {
            'name': 'T1', 'subject': 'S1', 'department': 'D1',
            'profile_picture': (io.BytesIO(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"), 'test1.png')
        }
        self.client.post('/teacher/profile/edit', data=data, content_type='multipart/form-data', follow_redirects=True)
        
        # Now remove
        rv = self.client.post('/teacher/profile/picture/remove', follow_redirects=True)
        self.assertIn(b'Profile picture removed', rv.data)

    def test_15_homepage_works(self):
        rv = self.client.get('/')
        self.assertEqual(rv.status_code, 200)
        self.assertIn(b'Attendify', rv.data)

if __name__ == '__main__':
    unittest.main(verbosity=2)
