import unittest
import os
import json
import time
from unittest.mock import patch
from app import app
from database.database import init_db, get_db_connection
from werkzeug.security import generate_password_hash
import itsdangerous
import uuid

class Phase11_5_6_TestCase(unittest.TestCase):
    def setUp(self):
        app.config['TESTING'] = True
        app.config['WTF_CSRF_ENABLED'] = False
        self.db_path = os.path.join(app.root_path, 'database', f'test_attendance_p11_5_6_{uuid.uuid4().hex}.db')
        app.config['DATABASE'] = self.db_path
        self.client = app.test_client()
        init_db(self.db_path)
        
        conn = get_db_connection(self.db_path)
        hashed_pw = generate_password_hash("password")
        
        # Teachers
        conn.execute('INSERT INTO users (name, email, password_hash, role) VALUES (?, ?, ?, ?)', ("T1", "t1@ex.com", hashed_pw, "teacher"))
        conn.execute('INSERT INTO users (name, email, password_hash, role) VALUES (?, ?, ?, ?)', ("T2", "t2@ex.com", hashed_pw, "teacher"))
        
        # Students
        conn.execute('INSERT INTO users (name, email, password_hash, role, student_id) VALUES (?, ?, ?, ?, ?)', ("S1", "s1@ex.com", hashed_pw, "student", "S100"))
        conn.execute('INSERT INTO users (name, email, password_hash, role, student_id) VALUES (?, ?, ?, ?, ?)', ("S2", "s2@ex.com", hashed_pw, "student", "S200"))
        conn.execute('INSERT INTO users (name, email, password_hash, role, student_id) VALUES (?, ?, ?, ?, ?)', ("S3", "s3@ex.com", hashed_pw, "student", "S300"))
        
        # Classes
        conn.execute('INSERT INTO classes (class_name, subject, course, semester, class_code, teacher_id) VALUES (?, ?, ?, ?, ?, ?)', ("C1", "S1", "C1", "1", "C001", 1))
        conn.execute('INSERT INTO classes (class_name, subject, course, semester, class_code, teacher_id) VALUES (?, ?, ?, ?, ?, ?)', ("C2", "S2", "C2", "1", "C002", 2))
        
        # Enroll S1 and S2 in C1
        conn.execute('INSERT INTO enrollments (class_id, student_id) VALUES (?, ?)', (1, 3)) # S1
        conn.execute('INSERT INTO enrollments (class_id, student_id) VALUES (?, ?)', (1, 4)) # S2
        
        # Sessions
        conn.execute('INSERT INTO attendance_sessions (class_id, session_code, expires_at, status) VALUES (?, ?, datetime("now", "+1 hour"), ?)', (1, "SESS1", "active"))
        conn.execute('INSERT INTO attendance_sessions (class_id, session_code, expires_at, status) VALUES (?, ?, datetime("now", "+1 hour"), ?)', (1, "SESS2", "active"))
        conn.execute('INSERT INTO attendance_sessions (class_id, session_code, expires_at, status) VALUES (?, ?, datetime("now", "-1 hour"), ?)', (1, "SESS_ENDED", "ended"))
        
        # S2 is already present in SESS1
        conn.execute('INSERT INTO attendance_records (session_id, student_id) VALUES (?, ?)', (1, 4))
        
        conn.commit()
        conn.close()
        self.signer = itsdangerous.URLSafeTimedSerializer(app.config['SECRET_KEY'])

    def tearDown(self):
        if os.path.exists(self.db_path):
            try:
                os.remove(self.db_path)
            except:
                pass

    def login(self, email):
        self.client.post('/login', data={'email': email, 'password': 'password'})
        
    def generate_token(self, teacher_id, class_id, session_id, eligible_students, age_offset=0):
        payload = {
            'teacher_id': teacher_id,
            'class_id': class_id,
            'session_id': session_id,
            'eligible_students': eligible_students
        }
        # To simulate expired token, we have to mock time or create a token with an old timestamp
        # URLSafeTimedSerializer uses time.time() internally if we don't override. 
        # Actually it's easier to just mock time in the test.
        return self.signer.dumps(payload)

    # ------------------- A. Review Workflow (Mocked CV) -------------------
    @patch('app.FaceRecognitionEngine.process_classroom_image')
    @patch('app.is_valid_image_file', return_value=True)
    def test_review_workflow(self, mock_is_valid, mock_cv):
        mock_cv.return_value = {
            "success": True,
            "results": [
                {"recognized": True, "user_id": 3, "similarity": 0.85}, # S1 (Eligible)
                {"recognized": True, "user_id": 3, "similarity": 0.81}, # S1 (Duplicate)
                {"recognized": True, "user_id": 4, "similarity": 0.90}, # S2 (Already present)
                {"recognized": True, "user_id": 5, "similarity": 0.70}, # S3 (Unenrolled)
                {"recognized": False} # Unknown
            ]
        }
        self.login('t1@ex.com')
        import io
        rv = self.client.post('/teacher/classes/1/attendance/1/recognize', data={'file': (io.BytesIO(b'dummy'), 'test.jpg')}, content_type='multipart/form-data')
        
        if rv.status_code != 200:
            print(rv.data)
        
        data = json.loads(rv.data)
        
        res = data['results']
        self.assertTrue(res[0]['enrolled_in_class'])
        self.assertFalse(res[0]['already_present'])
        self.assertFalse(res[0]['duplicate_in_photo'])
        
        self.assertTrue(res[1]['enrolled_in_class'])
        self.assertFalse(res[1]['already_present'])
        self.assertTrue(res[1]['duplicate_in_photo'])
        
        self.assertTrue(res[2]['enrolled_in_class'])
        self.assertTrue(res[2]['already_present'])
        
        self.assertFalse(res[3]['enrolled_in_class'])
        
        # Token should only contain S1 (user_id=3)
        token = data['save_token']
        payload = self.signer.loads(token)
        eligible = payload['eligible_students']
        self.assertEqual(len(eligible), 1)
        self.assertEqual(eligible[0]['user_id'], 3)
        self.assertEqual(eligible[0]['similarity'], 0.85)

    # ------------------- B. Token Security -------------------
    def test_token_expired(self):
        self.login('t1@ex.com')
        # Create a token with an artificially old timestamp
        # The default payload generated by itsdangerous signs [payload, timestamp]
        # We can just mock time.time when we dump it.
        with patch('time.time', return_value=time.time() - 2000):
            token = self.signer.dumps({
                'teacher_id': 1, 'class_id': 1, 'session_id': 1, 'eligible_students': []
            })
            
        rv = self.client.post('/teacher/classes/1/attendance/1/save', json={'save_token': token})
        self.assertEqual(rv.status_code, 400)
        self.assertIn(b'expired', rv.data.lower())

    def test_token_wrong_class(self):
        self.login('t1@ex.com')
        token = self.generate_token(1, 999, 1, [{'user_id': 3}])
        rv = self.client.post('/teacher/classes/1/attendance/1/save', json={'save_token': token})
        self.assertEqual(rv.status_code, 400)
        self.assertIn(b'Token does not match class', rv.data)
        
    def test_token_wrong_session(self):
        self.login('t1@ex.com')
        token = self.generate_token(1, 1, 999, [{'user_id': 3}])
        rv = self.client.post('/teacher/classes/1/attendance/1/save', json={'save_token': token})
        self.assertEqual(rv.status_code, 400)
        self.assertIn(b'Token does not match session', rv.data)

    def test_token_wrong_teacher(self):
        self.login('t1@ex.com')
        token = self.generate_token(2, 1, 1, [{'user_id': 3}])
        rv = self.client.post('/teacher/classes/1/attendance/1/save', json={'save_token': token})
        self.assertEqual(rv.status_code, 400)
        self.assertIn(b'Token does not match teacher', rv.data)

    def test_token_tampered(self):
        self.login('t1@ex.com')
        rv = self.client.post('/teacher/classes/1/attendance/1/save', json={'save_token': "tampered.token.123"})
        self.assertEqual(rv.status_code, 400)

    # ------------------- C & E. Attendance & Audit -------------------
    def test_attendance_and_audit(self):
        self.login('t1@ex.com')
        token = self.generate_token(1, 1, 1, [{'user_id': 3, 'similarity': 0.88}])
        rv = self.client.post('/teacher/classes/1/attendance/1/save', json={'save_token': token})
        self.assertEqual(rv.status_code, 200)
        
        conn = get_db_connection(self.db_path)
        row = conn.execute('SELECT * FROM attendance_records WHERE session_id=1 AND student_id=3').fetchone()
        conn.close()
        
        self.assertIsNotNone(row)
        self.assertEqual(row['attendance_source'], 'classroom_photo')
        self.assertEqual(row['similarity'], 0.88)
        
        # Test replay
        rv2 = self.client.post('/teacher/classes/1/attendance/1/save', json={'save_token': token})
        data = json.loads(rv2.data)
        self.assertEqual(data['marked_count'], 0)
        self.assertEqual(data['already_present_count'], 1)

    # ------------------- D. Error Handling -------------------
    def test_inactive_session(self):
        self.login('t1@ex.com')
        rv = self.client.post('/teacher/classes/1/attendance/3/recognize', data={'file': (b'', '')})
        self.assertEqual(rv.status_code, 400)
        self.assertIn(b'Session is not active', rv.data)

if __name__ == '__main__':
    unittest.main()
