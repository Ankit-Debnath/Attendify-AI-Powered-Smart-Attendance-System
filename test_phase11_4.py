import unittest
import os
import io
import numpy as np
import sqlite3
from app import app
from database.database import init_db, get_db_connection
from tests.csrf_wrapper import CSRFTestClient

class Phase11_4_TestCase(unittest.TestCase):
    def setUp(self):
        app.config['TESTING'] = True
        app.config['DATABASE'] = os.path.join(app.root_path, 'database', 'test_attendance_p11_4.db')
        self.client = CSRFTestClient(app.test_client())
        init_db(app.config['DATABASE'])
        
        # Register user
        self.client.post('/register/student', data=dict(
            name='S1', email='s1@example.com', password='password', confirm_password='password',
            student_id='S100', course='C1', semester='1'
        ))
        self.client.post('/register/teacher', data=dict(
            name='T1', email='t1@example.com', password='password', confirm_password='password',
            subject='S1', department='D1'
        ))
        
    def tearDown(self):
        if os.path.exists(app.config['DATABASE']):
            try:
                os.remove(app.config['DATABASE'])
            except:
                pass
                
    def login(self, email, password):
        return self.client.post('/login', data=dict(email=email, password=password), follow_redirects=True)
        
    def get_image_bytes(self, path):
        with open(path, 'rb') as f:
            return f.read()

    def test_A_valid_single_face(self):
        self.login('s1@example.com', 'password')
        img_bytes = self.get_image_bytes('tests/temp/lena.jpg')
        data = {'name': 'S1', 'course': 'C1', 'semester': '1', 'profile_picture': (io.BytesIO(img_bytes), 'lena.jpg')}
        rv = self.client.post('/student/profile/edit', data=data, content_type='multipart/form-data', follow_redirects=True)
        self.assertIn(b'Profile updated successfully', rv.data)
        
        conn = get_db_connection(app.config['DATABASE'])
        emb_row = conn.execute('SELECT embedding, model_name FROM face_embeddings WHERE student_id = 1').fetchone()
        conn.close()
        self.assertIsNotNone(emb_row)
        self.assertEqual(emb_row['model_name'], 'sface_2021dec')
        
        emb = np.frombuffer(emb_row['embedding'], dtype=np.float32)
        self.assertEqual(emb.shape, (128,))
        self.assertTrue(np.isfinite(emb).all())
        
    def test_B_reenrollment(self):
        self.login('s1@example.com', 'password')
        img_bytes = self.get_image_bytes('tests/temp/lena.jpg')
        data = {'name': 'S1', 'course': 'C1', 'semester': '1', 'profile_picture': (io.BytesIO(img_bytes), 'lena1.jpg')}
        self.client.post('/student/profile/edit', data=data, content_type='multipart/form-data')
        
        # Second upload
        data2 = {'name': 'S1', 'course': 'C1', 'semester': '1', 'profile_picture': (io.BytesIO(img_bytes), 'lena2.jpg')}
        self.client.post('/student/profile/edit', data=data2, content_type='multipart/form-data')
        
        conn = get_db_connection(app.config['DATABASE'])
        count = conn.execute('SELECT COUNT(*) FROM face_embeddings WHERE student_id = 1').fetchone()[0]
        conn.close()
        self.assertEqual(count, 1)
        
    def test_C_no_face(self):
        self.login('s1@example.com', 'password')
        img_bytes = self.get_image_bytes('tests/temp/zero_face.jpg')
        data = {'name': 'S1', 'course': 'C1', 'semester': '1', 'profile_picture': (io.BytesIO(img_bytes), 'zero.jpg')}
        rv = self.client.post('/student/profile/edit', data=data, content_type='multipart/form-data', follow_redirects=True)
        self.assertIn(b'No face detected', rv.data)
        
        conn = get_db_connection(app.config['DATABASE'])
        count = conn.execute('SELECT COUNT(*) FROM face_embeddings WHERE student_id = 1').fetchone()[0]
        conn.close()
        self.assertEqual(count, 0)
        
    def test_D_multiple_faces(self):
        self.login('s1@example.com', 'password')
        img_bytes = self.get_image_bytes('tests/temp/multi_face.jpg')
        data = {'name': 'S1', 'course': 'C1', 'semester': '1', 'profile_picture': (io.BytesIO(img_bytes), 'multi.jpg')}
        rv = self.client.post('/student/profile/edit', data=data, content_type='multipart/form-data', follow_redirects=True)
        self.assertIn(b'Multiple faces detected', rv.data)
        
        conn = get_db_connection(app.config['DATABASE'])
        count = conn.execute('SELECT COUNT(*) FROM face_embeddings WHERE student_id = 1').fetchone()[0]
        conn.close()
        self.assertEqual(count, 0)
        
    def test_E_unauthorized_access(self):
        # Not logged in
        img_bytes = self.get_image_bytes('tests/temp/lena.jpg')
        data = {'name': 'S1', 'course': 'C1', 'semester': '1', 'profile_picture': (io.BytesIO(img_bytes), 'lena.jpg')}
        rv = self.client.post('/student/profile/edit', data=data, content_type='multipart/form-data', follow_redirects=True)
        self.assertIn(b'Please log in', rv.data)
        
    def test_F_role_isolation(self):
        # Teacher logged in
        self.login('t1@example.com', 'password')
        img_bytes = self.get_image_bytes('tests/temp/lena.jpg')
        data = {'name': 'S1', 'course': 'C1', 'semester': '1', 'profile_picture': (io.BytesIO(img_bytes), 'lena.jpg')}
        rv = self.client.post('/student/profile/edit', data=data, content_type='multipart/form-data', follow_redirects=True)
        self.assertIn(b'Unauthorized access', rv.data)
        
    def test_G_csrf_protection(self):
        self.login('s1@example.com', 'password')
        img_bytes = self.get_image_bytes('tests/temp/lena.jpg')
        data = {'name': 'S1', 'course': 'C1', 'semester': '1', 'profile_picture': (io.BytesIO(img_bytes), 'lena.jpg')}
        
        # Raw test client to bypass CSRF wrapper
        rv = app.test_client().post('/student/profile/edit', data=data, content_type='multipart/form-data', follow_redirects=True)
        self.assertEqual(rv.status_code, 400)
        self.assertIn(b'Bad Request', rv.data)

if __name__ == '__main__':
    unittest.main(verbosity=2)
