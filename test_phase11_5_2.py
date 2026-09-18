import unittest
import os
import io
import json
from app import app
from database.database import init_db, get_db_connection
from tests.csrf_wrapper import CSRFTestClient

def get_lena_bytes():
    with open('tests/temp/lena.jpg', 'rb') as f:
        return f.read()

class MockFaceRecognitionEngine:
    def __init__(self, db_path):
        pass
        
    def process_classroom_image(self, image_bytes):
        # We will dynamically set return value in tests
        pass

import app as app_module
app_module.FaceRecognitionEngine = MockFaceRecognitionEngine


import uuid
class Phase11_5_2_TestCase(unittest.TestCase):
    def setUp(self):
        app.config['TESTING'] = True
        self.db_path = os.path.join(app.root_path, 'database', f'test_attendance_p11_5_2_{uuid.uuid4().hex}.db')
        app.config['DATABASE'] = self.db_path
        
        self.client = CSRFTestClient(app.test_client())
        init_db(app.config['DATABASE'])
        
        conn = get_db_connection(app.config['DATABASE'])
        from werkzeug.security import generate_password_hash
        hashed_pw = generate_password_hash("password")
        conn.execute('INSERT INTO users (name, email, password_hash, role) VALUES (?, ?, ?, ?)', ("Teacher", "teacher@example.com", hashed_pw, "teacher"))
        conn.execute('INSERT INTO users (name, email, password_hash, role) VALUES (?, ?, ?, ?)', ("Teacher2", "teacher2@example.com", hashed_pw, "teacher"))
        conn.execute('INSERT INTO users (name, email, password_hash, role, student_id) VALUES (?, ?, ?, ?, ?)', ("Student A", "student1@example.com", hashed_pw, "student", "S100"))
        conn.execute('INSERT INTO users (name, email, password_hash, role, student_id) VALUES (?, ?, ?, ?, ?)', ("Student B", "student2@example.com", hashed_pw, "student", "S200"))
        
        conn.execute('INSERT INTO classes (class_name, subject, course, semester, class_code, teacher_id) VALUES (?, ?, ?, ?, ?, ?)', ("Class A", "Sub A", "C1", "1", "CODEA", 1))
        conn.execute('INSERT INTO enrollments (class_id, student_id) VALUES (?, ?)', (1, 3)) # Student A (id=3) is enrolled in Class A
        
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
        return self.client.post('/login', data=dict(email='student1@example.com', password='password'), follow_redirects=True)
        
    def login_teacher2(self):
        return self.client.post('/login', data=dict(email='teacher2@example.com', password='password'), follow_redirects=True)

    def set_mock_response(self, response):
        app_module.FaceRecognitionEngine.process_classroom_image = lambda self, bytes: response

    def test_01_access_photo_recognition_endpoint(self):
        self.login_teacher()
        self.set_mock_response({"success": True, "total_detected_faces": 0, "recognized_faces": 0, "unknown_faces": 0, "results": []})
        data = {'file': (io.BytesIO(get_lena_bytes()), 'test.jpg')}
        rv = self.client.post('/teacher/classes/1/attendance/1/recognize', data=data, content_type='multipart/form-data')
        self.assertEqual(rv.status_code, 200)
        json_data = json.loads(rv.data)
        self.assertTrue(json_data['success'])

    def test_02_unauthenticated_user_rejected(self):
        rv = self.client.post('/teacher/classes/1/attendance/1/recognize')
        self.assertEqual(rv.status_code, 302)

    def test_03_student_role_rejected(self):
        self.login_student()
        rv = self.client.post('/teacher/classes/1/attendance/1/recognize')
        self.assertEqual(rv.status_code, 302)
        
    def test_04_missing_csrf_token(self):
        client = app.test_client()
        rv = client.post('/teacher/classes/1/attendance/1/recognize', data={})
        self.assertEqual(rv.status_code, 400)

    def test_05_invalid_image_rejected(self):
        self.login_teacher()
        data = {'file': (io.BytesIO(b"not an image"), 'test.txt')}
        rv = self.client.post('/teacher/classes/1/attendance/1/recognize', data=data, content_type='multipart/form-data')
        self.assertEqual(rv.status_code, 400)
        json_data = json.loads(rv.data)
        self.assertFalse(json_data['success'])
        self.assertIn("Invalid or corrupted image format", json_data['error'])

    def test_07_invalid_class_id_rejected(self):
        self.login_teacher()
        data = {'file': (io.BytesIO(get_lena_bytes()), 'test.jpg')}
        rv = self.client.post('/teacher/classes/99/attendance/1/recognize', data=data, content_type='multipart/form-data')
        self.assertEqual(rv.status_code, 403)
        
    def test_08_invalid_session_id_rejected(self):
        self.login_teacher()
        data = {'file': (io.BytesIO(get_lena_bytes()), 'test.jpg')}
        rv = self.client.post('/teacher/classes/1/attendance/99/recognize', data=data, content_type='multipart/form-data')
        self.assertEqual(rv.status_code, 400)
        
    def test_09_session_class_mismatch(self):
        # Insert a session for another class
        conn = get_db_connection(app.config['DATABASE'])
        conn.execute('INSERT INTO classes (class_name, subject, course, semester, class_code, teacher_id) VALUES (?, ?, ?, ?, ?, ?)', ("C", "S", "C", "1", "CODEC", 1))
        conn.execute('INSERT INTO attendance_sessions (class_id, session_code, expires_at, status) VALUES (?, ?, datetime("now", "+1 hour"), "active")', (2, "SESS_B"))
        conn.commit()
        conn.close()
        
        self.login_teacher()
        data = {'file': (io.BytesIO(get_lena_bytes()), 'test.jpg')}
        # class 1 calling session 2 (which belongs to class 2)
        rv = self.client.post('/teacher/classes/1/attendance/2/recognize', data=data, content_type='multipart/form-data')
        self.assertEqual(rv.status_code, 400)
        
    def test_10_unauthorized_teacher(self):
        self.login_teacher2()
        data = {'file': (io.BytesIO(get_lena_bytes()), 'test.jpg')}
        rv = self.client.post('/teacher/classes/1/attendance/1/recognize', data=data, content_type='multipart/form-data')
        self.assertEqual(rv.status_code, 403)
        
    def test_11_12_13_14_recognition_result_correct(self):
        self.login_teacher()
        # Mock a result with recognized enrolled, recognized unenrolled, and unknown
        mock_result = {
            "success": True, "total_detected_faces": 3, "recognized_faces": 2, "unknown_faces": 1,
            "results": [
                {"user_id": 3, "student_id": "S100", "recognized": True}, # Student A (enrolled)
                {"user_id": 4, "student_id": "S200", "recognized": True}, # Student B (not enrolled)
                {"user_id": None, "student_id": None, "recognized": False} # Unknown
            ]
        }
        self.set_mock_response(mock_result)
        
        data = {'file': (io.BytesIO(get_lena_bytes()), 'test.jpg')}
        rv = self.client.post('/teacher/classes/1/attendance/1/recognize', data=data, content_type='multipart/form-data')
        
        self.assertEqual(rv.status_code, 200)
        json_data = json.loads(rv.data)
        
        self.assertTrue(json_data['success'])
        self.assertEqual(json_data['total_detected_faces'], 3)
        
        res = json_data['results']
        
        # Enrolled
        self.assertTrue(res[0]['recognized'])
        self.assertTrue(res[0]['enrolled_in_class'])
        
        # Unenrolled
        self.assertTrue(res[1]['recognized'])
        self.assertFalse(res[1]['enrolled_in_class'])
        
        # Unknown
        self.assertFalse(res[2]['recognized'])
        self.assertFalse(res[2]['enrolled_in_class'])

    def test_15_no_face_image_returns_valid_empty_result(self):
        self.login_teacher()
        self.set_mock_response({"success": True, "total_detected_faces": 0, "recognized_faces": 0, "unknown_faces": 0, "results": []})
        data = {'file': (io.BytesIO(get_lena_bytes()), 'test.jpg')}
        rv = self.client.post('/teacher/classes/1/attendance/1/recognize', data=data, content_type='multipart/form-data')
        json_data = json.loads(rv.data)
        self.assertEqual(json_data['total_detected_faces'], 0)
        self.assertEqual(len(json_data['results']), 0)
        
    def test_16_existing_attendance_records_not_changed(self):
        self.login_teacher()
        self.set_mock_response({"success": True, "total_detected_faces": 1, "recognized_faces": 1, "unknown_faces": 0, "results": [{"user_id": 3, "student_id": "S100", "recognized": True}]})
        data = {'file': (io.BytesIO(get_lena_bytes()), 'test.jpg')}
        self.client.post('/teacher/classes/1/attendance/1/recognize', data=data, content_type='multipart/form-data')
        
        # Verify no attendance was marked
        conn = get_db_connection(app.config['DATABASE'])
        records = conn.execute('SELECT count(*) as count FROM attendance_records').fetchone()
        self.assertEqual(records['count'], 0)
        conn.close()

if __name__ == '__main__':
    unittest.main(verbosity=2)

