from tests.csrf_wrapper import CSRFTestClient
import unittest
from app import app
from database.database import init_db, get_db_connection, get_class_by_code
import os

class Phase5TestCase(unittest.TestCase):
    def setUp(self):
        app.config['TESTING'] = True
        app.config['DATABASE'] = os.path.join(app.root_path, 'database', 'test_attendance_p5.db')
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
            
    def login_teacher(self):
        return self.client.post('/login', data=dict(email='t1@example.com', password='password'), follow_redirects=True)
        
    def login_teacher2(self):
        return self.client.post('/login', data=dict(email='t2@example.com', password='password'), follow_redirects=True)
        
    def login_student(self):
        return self.client.post('/login', data=dict(email='s1@example.com', password='password'), follow_redirects=True)

    def login_student2(self):
        return self.client.post('/login', data=dict(email='s2@example.com', password='password'), follow_redirects=True)

    def test_01_02_tables_exist(self):
        conn = get_db_connection(app.config['DATABASE'])
        classes = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='classes'").fetchone()
        enroll = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='enrollments'").fetchone()
        conn.close()
        self.assertIsNotNone(classes)
        self.assertIsNotNone(enroll)

    def test_04_06_create_class_and_view(self):
        self.login_teacher()
        rv = self.client.post('/teacher/classes/create', data=dict(
            class_name='Math 101', subject='Math', course='BSc', semester='1'
        ), follow_redirects=True)
        self.assertIn(b'Class created successfully', rv.data)
        
        # Verify in view
        rv_view = self.client.get('/teacher/classes')
        self.assertIn(b'Math 101', rv_view.data)

    def test_05_create_class_validation(self):
        self.login_teacher()
        rv = self.client.post('/teacher/classes/create', data=dict(
            class_name='', subject='Math', course='BSc', semester='1'
        ), follow_redirects=True)
        self.assertIn(b'All fields are required', rv.data)

    def test_08_09_10_edit_class(self):
        self.login_teacher()
        self.client.post('/teacher/classes/create', data=dict(
            class_name='Math 101', subject='Math', course='BSc', semester='1'
        ), follow_redirects=True)
        
        rv = self.client.post('/teacher/classes/1/edit', data=dict(
            class_name='Math 102', subject='Math', course='BSc', semester='2'
        ), follow_redirects=True)
        self.assertIn(b'Class updated successfully', rv.data)
        
        # Check details
        rv_detail = self.client.get('/teacher/classes/1')
        self.assertIn(b'Math 102', rv_detail.data)

    def test_14_teacher_cannot_access_other_class(self):
        self.login_teacher()
        self.client.post('/teacher/classes/create', data=dict(
            class_name='Math 101', subject='Math', course='BSc', semester='1'
        ), follow_redirects=True)
        
        self.client.get('/logout')
        self.login_teacher2()
        rv = self.client.get('/teacher/classes/1', follow_redirects=True)
        self.assertIn(b'Class not found or unauthorized', rv.data)

    def test_15_17_student_join_class(self):
        self.login_teacher()
        self.client.post('/teacher/classes/create', data=dict(
            class_name='Math 101', subject='Math', course='BSc', semester='1'
        ), follow_redirects=True)
        
        conn = get_db_connection(app.config['DATABASE'])
        class_code = conn.execute('SELECT class_code FROM classes WHERE id=1').fetchone()['class_code']
        conn.close()
        
        self.client.get('/logout')
        self.login_student()
        
        rv = self.client.post('/student/classes/join', data=dict(class_code=class_code), follow_redirects=True)
        self.assertIn(b'Successfully joined the class', rv.data)
        
        # Test 17: Duplicate enrollment
        rv2 = self.client.post('/student/classes/join', data=dict(class_code=class_code), follow_redirects=True)
        self.assertIn(b'already enrolled', rv2.data)

    def test_16_invalid_class_code(self):
        self.login_student()
        rv = self.client.post('/student/classes/join', data=dict(class_code='INVALID'), follow_redirects=True)
        self.assertIn(b'Invalid class code', rv.data)

    def test_18_19_20_leave_class(self):
        # Setup class and join
        self.login_teacher()
        self.client.post('/teacher/classes/create', data=dict(
            class_name='Math 101', subject='Math', course='BSc', semester='1'
        ), follow_redirects=True)
        conn = get_db_connection(app.config['DATABASE'])
        class_code = conn.execute('SELECT class_code FROM classes WHERE id=1').fetchone()['class_code']
        conn.close()
        
        self.client.get('/logout')
        self.login_student()
        self.client.post('/student/classes/join', data=dict(class_code=class_code), follow_redirects=True)
        
        # Leave class
        rv = self.client.post('/student/classes/1/leave', follow_redirects=True)
        self.assertIn(b'Successfully left the class', rv.data)
        
        # Class still exists
        self.client.get('/logout')
        self.login_teacher()
        rv2 = self.client.get('/teacher/classes/1')
        self.assertIn(b'Math 101', rv2.data)

    def test_11_12_13_teacher_delete_class(self):
        self.login_teacher()
        self.client.post('/teacher/classes/create', data=dict(
            class_name='Math 101', subject='Math', course='BSc', semester='1'
        ), follow_redirects=True)
        conn = get_db_connection(app.config['DATABASE'])
        class_code = conn.execute('SELECT class_code FROM classes WHERE id=1').fetchone()['class_code']
        conn.close()
        
        self.client.get('/logout')
        self.login_student()
        self.client.post('/student/classes/join', data=dict(class_code=class_code), follow_redirects=True)
        
        self.client.get('/logout')
        self.login_teacher()
        rv = self.client.post('/teacher/classes/1/delete', follow_redirects=True)
        self.assertIn(b'Class deleted successfully', rv.data)
        
        # Check student still exists
        self.client.get('/logout')
        rv2 = self.login_student()
        self.assertIn(b'My Attendance Analytics', rv2.data)

    def test_22_23_24_access_control(self):
        # 22 Unauthenticated
        rv1 = self.client.get('/teacher/classes', follow_redirects=True)
        self.assertIn(b'Please log in', rv1.data)
        
        # 23 Student accessing teacher
        self.login_student()
        rv2 = self.client.get('/teacher/classes', follow_redirects=True)
        self.assertIn(b'Unauthorized access', rv2.data)
        
        # 24 Teacher accessing student
        self.client.get('/logout')
        self.login_teacher()
        rv3 = self.client.get('/student/classes', follow_redirects=True)
        self.assertIn(b'Unauthorized access', rv3.data)

if __name__ == '__main__':
    unittest.main(verbosity=2)
