import unittest
from app import app
from database.database import init_db, get_db_connection, get_user_by_email
from tests.csrf_wrapper import CSRFTestClient
import os
import datetime
import io
import json
from unittest.mock import patch

class DynamicQRTestCase(unittest.TestCase):
    def setUp(self):
        app.config['TESTING'] = True
        app.config['DATABASE'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'test_temp.db')
        self.client = CSRFTestClient(app.test_client())
        init_db(app.config['DATABASE'])

        conn = get_db_connection(app.config['DATABASE'])
        conn.execute('DELETE FROM users')
        conn.execute('DELETE FROM classes')
        conn.execute('DELETE FROM attendance_sessions')
        conn.execute('DELETE FROM enrollments')
        conn.execute('DELETE FROM student_face_references')

        conn.execute("""
            INSERT INTO users (name, email, password_hash, role, student_id)
            VALUES ('Teacher', 't@test.com', 'scrypt:32768:8:1$u7xK/x12$...', 'teacher', NULL)
        """)
        self.teacher_id = conn.execute('SELECT id FROM users WHERE email="t@test.com"').fetchone()[0]

        conn.execute("""
            INSERT INTO classes (class_name, subject, course, semester, class_code, teacher_id)
            VALUES ('Class1', 'Sub1', 'Course1', 1, 'Code1', ?)
        """, (self.teacher_id,))
        self.class_id = conn.execute('SELECT last_insert_rowid()').fetchone()[0]

        exp = datetime.datetime.utcnow() + datetime.timedelta(hours=1)
        conn.execute("""
            INSERT INTO attendance_sessions (class_id, session_code, expires_at, status)
            VALUES (?, '1234', ?, 'active')
        """, (self.class_id, exp.strftime('%Y-%m-%d %H:%M:%S')))
        self.session_id = conn.execute('SELECT last_insert_rowid()').fetchone()[0]

        conn.execute("""
            INSERT INTO users (name, email, password_hash, role, student_id)
            VALUES ('Student', 's@test.com', 'scrypt:32768:8:1$u7xK/x12$...', 'student', 'S123')
        """)
        self.student_user_id = conn.execute('SELECT id FROM users WHERE email="s@test.com"').fetchone()[0]

        conn.execute("""
            INSERT INTO enrollments (student_id, class_id)
            VALUES (?, ?)
        """, (self.student_user_id, self.class_id))

        # INSERT face reference
        conn.execute("""
            INSERT INTO student_face_references (student_id, image_path, embedding)
            VALUES (?, 'dummy', '[]')
        """, (self.student_user_id,))

        conn.commit()
        conn.close()

    def login(self, email):
        with self.client.session_transaction() as sess:
            user = get_user_by_email(app.config['DATABASE'], email)
            sess['user_id'] = user['id']
            sess['role'] = user['role']

    def test_live_status_generates_token(self):
        self.login('t@test.com')
        res = self.client.get(f'/api/teacher/attendance/{self.session_id}/live_status')
        self.assertEqual(res.status_code, 200)

        conn = get_db_connection(app.config['DATABASE'])
        token = conn.execute('SELECT current_token FROM attendance_sessions WHERE id = ?', (self.session_id,)).fetchone()[0]
        conn.close()

        self.assertIsNotNone(token)
        return token

    def test_scan_token(self):
        token = self.test_live_status_generates_token()
        self.login('s@test.com')
        res = self.client.get(f'/student/attendance/scan/{token}', follow_redirects=True)
        self.assertEqual(res.status_code, 200)

    @patch('utils.cv_engine.process_student_attendance')
    def test_submit_face(self, mock_process):
        mock_process.return_value = {'success': True, 'status': 'present', 'message': 'Verified', 'reason': 'Face matched'}
        token = self.test_live_status_generates_token()
        self.login('s@test.com')
        self.client.get(f'/student/attendance/scan/{token}')

        data = {
            'face_image': (io.BytesIO(b'dummy_image_data'), 'face.jpg')
        }
        res = self.client.post('/student/attendance/verify', data=data, content_type='multipart/form-data', follow_redirects=True)
        self.assertEqual(res.status_code, 200)

    @patch('utils.cv_engine.process_student_attendance')
    def test_submit_face_needs_confirmation(self, mock_process):
        mock_process.return_value = {'success': True, 'status': 'needs_confirmation', 'message': 'Low confidence', 'reason': 'Low confidence'}
        token = self.test_live_status_generates_token()
        self.login('s@test.com')
        self.client.get(f'/student/attendance/scan/{token}')

        data = {
            'face_image': (io.BytesIO(b'dummy_image_data'), 'face.jpg')
        }
        res = self.client.post('/student/attendance/verify', data=data, content_type='multipart/form-data', follow_redirects=True)
        self.assertEqual(res.status_code, 200)

if __name__ == "__main__":
    unittest.main()
