from tests.csrf_wrapper import CSRFTestClient
import unittest
from app import app
from database.database import init_db, get_db_connection
import os
import time

class Phase6TestCase(unittest.TestCase):
    def setUp(self):
        app.config['TESTING'] = True
        app.config['DATABASE'] = os.path.join(app.root_path, 'database', 'test_attendance_p6.db')
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
        
        # T1 Creates Class 1
        self.login('t1@example.com', 'password')
        self.client.post('/teacher/classes/create', data=dict(
            class_name='Math 101', subject='Math', course='BSc', semester='1'
        ), follow_redirects=True)
        conn = get_db_connection(app.config['DATABASE'])
        self.class1_code = conn.execute('SELECT class_code FROM classes WHERE id=1').fetchone()['class_code']
        conn.close()
        self.client.get('/logout')
        
        # S1 joins Class 1
        self.login('s1@example.com', 'password')
        self.client.post('/student/classes/join', data=dict(class_code=self.class1_code), follow_redirects=True)
        self.client.get('/logout')

    def tearDown(self):
        if os.path.exists(app.config['DATABASE']):
            try:
                os.remove(app.config['DATABASE'])
            except:
                pass
            
    def login(self, email, password):
        return self.client.post('/login', data=dict(email=email, password=password), follow_redirects=True)

    def test_01_03_tables_and_constraints(self):
        conn = get_db_connection(app.config['DATABASE'])
        sess = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='attendance_sessions'").fetchone()
        rec = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='attendance_records'").fetchone()
        
        # Test unique constraint on attendance_records (session_id, student_id)
        # by attempting duplicate insert manually
        try:
            conn.execute("INSERT INTO attendance_sessions (class_id, session_code, expires_at) VALUES (1, 'CODE1', '2030')")
            conn.execute("INSERT INTO attendance_records (session_id, student_id) VALUES (1, 1)")
            conn.execute("INSERT INTO attendance_records (session_id, student_id) VALUES (1, 1)")
            duplicate_handled = False
        except Exception:
            duplicate_handled = True
            
        conn.close()
        self.assertIsNotNone(sess)
        self.assertIsNotNone(rec)
        self.assertTrue(duplicate_handled)

    def test_04_08_teacher_manage_session(self):
        self.login('t1@example.com', 'password')
        rv = self.client.post('/teacher/classes/1/attendance', data=dict(duration=10), follow_redirects=True)
        self.assertIn(b'Attendance session started', rv.data)
        self.assertIn(b'Active Session', rv.data)
        
        # End session
        rv2 = self.client.post('/teacher/attendance/1/end', follow_redirects=True)
        self.assertIn(b'Attendance session ended', rv2.data)

    def test_09_10_teacher_authorization(self):
        # T1 starts session
        self.login('t1@example.com', 'password')
        self.client.post('/teacher/classes/1/attendance', data=dict(duration=10), follow_redirects=True)
        self.client.get('/logout')
        
        # T2 tries to access/end T1's session
        self.login('t2@example.com', 'password')
        rv = self.client.get('/teacher/attendance/1', follow_redirects=True)
        self.assertIn(b'Unauthorized', rv.data)
        
        rv2 = self.client.post('/teacher/attendance/1/end', follow_redirects=True)
        self.assertIn(b'Unauthorized', rv2.data)

    def test_11_16_student_checkin(self):
        self.login('t1@example.com', 'password')
        self.client.post('/teacher/classes/1/attendance', data=dict(duration=10), follow_redirects=True)
        conn = get_db_connection(app.config['DATABASE'])
        session_code = conn.execute('SELECT session_code FROM attendance_sessions WHERE id=1').fetchone()['session_code']
        conn.close()
        self.client.get('/logout')
        
        # S1 checkin
        self.login('s1@example.com', 'password')
        rv = self.client.post(f'/student/attendance/checkin/{session_code}', follow_redirects=True)
        self.assertIn(b'Attendance marked successfully', rv.data)
        
        # Duplicate checkin
        rv2 = self.client.post(f'/student/attendance/checkin/{session_code}', follow_redirects=True)
        self.assertIn(b'already checked in', rv2.data)

    def test_12_unenrolled_checkin(self):
        self.login('t1@example.com', 'password')
        self.client.post('/teacher/classes/1/attendance', data=dict(duration=10), follow_redirects=True)
        conn = get_db_connection(app.config['DATABASE'])
        session_code = conn.execute('SELECT session_code FROM attendance_sessions WHERE id=1').fetchone()['session_code']
        conn.close()
        self.client.get('/logout')
        
        # S2 (not enrolled in class 1)
        self.login('s2@example.com', 'password')
        rv = self.client.post(f'/student/attendance/checkin/{session_code}', follow_redirects=True)
        self.assertIn(b'not enrolled', rv.data)

    def test_15_ended_session_checkin(self):
        self.login('t1@example.com', 'password')
        self.client.post('/teacher/classes/1/attendance', data=dict(duration=10), follow_redirects=True)
        conn = get_db_connection(app.config['DATABASE'])
        session_code = conn.execute('SELECT session_code FROM attendance_sessions WHERE id=1').fetchone()['session_code']
        conn.close()
        self.client.post('/teacher/attendance/1/end', follow_redirects=True)
        self.client.get('/logout')
        
        self.login('s1@example.com', 'password')
        rv = self.client.post(f'/student/attendance/checkin/{session_code}', follow_redirects=True)
        self.assertIn(b'ended', rv.data)

    def test_14_expired_session(self):
        # We simulate expiration by forcing db update
        self.login('t1@example.com', 'password')
        self.client.post('/teacher/classes/1/attendance', data=dict(duration=10), follow_redirects=True)
        conn = get_db_connection(app.config['DATABASE'])
        session_code = conn.execute('SELECT session_code FROM attendance_sessions WHERE id=1').fetchone()['session_code']
        conn.execute("UPDATE attendance_sessions SET expires_at = '2000-01-01 00:00:00' WHERE id=1")
        conn.commit()
        conn.close()
        self.client.get('/logout')
        
        self.login('s1@example.com', 'password')
        rv = self.client.post(f'/student/attendance/checkin/{session_code}', follow_redirects=True)
        self.assertIn(b'expired', rv.data)

    def test_17_18_student_history(self):
        self.login('t1@example.com', 'password')
        self.client.post('/teacher/classes/1/attendance', data=dict(duration=10), follow_redirects=True)
        conn = get_db_connection(app.config['DATABASE'])
        session_code = conn.execute('SELECT session_code FROM attendance_sessions WHERE id=1').fetchone()['session_code']
        conn.close()
        self.client.get('/logout')
        
        self.login('s1@example.com', 'password')
        self.client.post(f'/student/attendance/checkin/{session_code}', follow_redirects=True)
        
        rv = self.client.get('/student/attendance')
        self.assertIn(b'Math 101', rv.data)
        
        # S2 history should be empty
        self.client.get('/logout')
        self.login('s2@example.com', 'password')
        rv2 = self.client.get('/student/attendance')
        self.assertNotIn(b'Math 101', rv2.data)

    def test_19_21_access_control(self):
        rv = self.client.post('/student/attendance/checkin/CODE', follow_redirects=True)
        self.assertIn(b'Please log in', rv.data)
        
        self.login('s1@example.com', 'password')
        rv2 = self.client.get('/teacher/classes/1/attendance', follow_redirects=True)
        self.assertIn(b'Unauthorized access', rv2.data)
        self.client.get('/logout')
        
        self.login('t1@example.com', 'password')
        rv3 = self.client.get('/student/attendance', follow_redirects=True)
        self.assertIn(b'Unauthorized access', rv3.data)

if __name__ == '__main__':
    unittest.main(verbosity=2)
