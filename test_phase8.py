from tests.csrf_wrapper import CSRFTestClient
import unittest
from app import app
from database.database import init_db, get_db_connection
import os
import time

class Phase8TestCase(unittest.TestCase):
    def setUp(self):
        app.config['TESTING'] = True
        app.config['DATABASE'] = os.path.join(app.root_path, 'database', 'test_attendance_p8.db')
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
        
        # S1 and S2 join Class 1
        self.login('s1@example.com', 'password')
        self.client.post('/student/classes/join', data=dict(class_code=self.class1_code), follow_redirects=True)
        self.client.get('/logout')
        
        self.login('s2@example.com', 'password')
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

    def test_analytics_permissions(self):
        # Unauthenticated
        rv = self.client.get('/teacher/dashboard', follow_redirects=True)
        self.assertIn(b'Please log in', rv.data)
        
        # Student trying to access teacher dashboard
        self.login('s1@example.com', 'password')
        rv2 = self.client.get('/teacher/dashboard', follow_redirects=True)
        self.assertIn(b'Unauthorized access', rv2.data)
        self.client.get('/logout')
        
        # Teacher trying to access student dashboard
        self.login('t1@example.com', 'password')
        rv3 = self.client.get('/student/dashboard', follow_redirects=True)
        self.assertIn(b'Unauthorized access', rv3.data)

    def test_teacher_analytics_data(self):
        for i in range(3):
            # Teacher starts session
            self.login('t1@example.com', 'password')
            self.client.post('/teacher/classes/1/attendance', data=dict(duration=10), follow_redirects=True)
            from app import app, get_db_connection
            conn = get_db_connection(app.config['DATABASE'])
            s = conn.execute('SELECT id, session_code FROM attendance_sessions WHERE status="active" ORDER BY id DESC LIMIT 1').fetchone()
            s_id, code = s['id'], s['session_code']
            conn.close()
            self.client.get('/logout')
            
            # S1 checks in to all 3
            self.login('s1@example.com', 'password')
            self.client.post(f'/student/attendance/checkin/{code}', follow_redirects=True)
            self.client.get('/logout')
            
            # S2 checks in to first 2 only
            if i < 2:
                self.login('s2@example.com', 'password')
                self.client.post(f'/student/attendance/checkin/{code}', follow_redirects=True)
                self.client.get('/logout')
                
            # Teacher ends session
            self.login('t1@example.com', 'password')
            self.client.post(f'/teacher/attendance/{s_id}/end', follow_redirects=True)
            self.client.get('/logout')

        self.login('t1@example.com', 'password')
        rv = self.client.get('/teacher/dashboard')
        self.assertIn(b'83.3%', rv.data)

    def test_student_analytics_data(self):
        for i in range(3):
            # Teacher starts session
            self.login('t1@example.com', 'password')
            self.client.post('/teacher/classes/1/attendance', data=dict(duration=10), follow_redirects=True)
            from app import app, get_db_connection
            conn = get_db_connection(app.config['DATABASE'])
            s = conn.execute('SELECT id, session_code FROM attendance_sessions WHERE status="active" ORDER BY id DESC LIMIT 1').fetchone()
            s_id, code = s['id'], s['session_code']
            conn.close()
            self.client.get('/logout')
            
            # S1 checks in to all 3
            self.login('s1@example.com', 'password')
            self.client.post(f'/student/attendance/checkin/{code}', follow_redirects=True)
            self.client.get('/logout')
            
            # S2 checks in to first 2 only
            if i < 2:
                self.login('s2@example.com', 'password')
                self.client.post(f'/student/attendance/checkin/{code}', follow_redirects=True)
                self.client.get('/logout')
                
            # Teacher ends session
            self.login('t1@example.com', 'password')
            self.client.post(f'/teacher/attendance/{s_id}/end', follow_redirects=True)
            self.client.get('/logout')

        self.login('s1@example.com', 'password')
        rv_s1 = self.client.get('/student/dashboard')
        self.assertIn(b'100.0%', rv_s1.data)
        self.client.get('/logout')
        
        self.login('s2@example.com', 'password')
        rv_s2 = self.client.get('/student/dashboard')
        self.assertIn(b'66.7%', rv_s2.data)


