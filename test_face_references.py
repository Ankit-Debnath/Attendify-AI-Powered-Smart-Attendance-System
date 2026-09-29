import unittest
import os
import tempfile
import io
from unittest.mock import patch

from app import app
from tests.csrf_wrapper import CSRFTestClient
from database.database import init_db, get_db_connection, add_student_face_reference
from werkzeug.security import generate_password_hash

class FaceReferenceTestCase(unittest.TestCase):
    def setUp(self):
        app.config['TESTING'] = True

        self.db_fd, self.db_path = tempfile.mkstemp()
        app.config['DATABASE'] = self.db_path

        self.private_dir = tempfile.mkdtemp()
        app.config['PRIVATE_REF_FOLDER'] = self.private_dir
        self.upload_dir = tempfile.mkdtemp()
        app.config['UPLOAD_FOLDER'] = self.upload_dir

        self.client = CSRFTestClient(app.test_client())
        init_db(self.db_path)

        conn = get_db_connection(self.db_path)
        conn.execute('''
            INSERT INTO users (name, email, password_hash, role, student_id, course, semester)
            VALUES (?, ?, ?, 'student', ?, ?, ?)
        ''', ("Test Student", "student@test.com", generate_password_hash("password123"), "STU001", "CS", "1"))
        self.user_id = conn.execute('SELECT last_insert_rowid()').fetchone()[0]

        conn.execute('''
            INSERT INTO users (name, email, password_hash, role, student_id, course, semester)
            VALUES (?, ?, ?, 'student', ?, ?, ?)
        ''', ("Student 2", "student2@test.com", generate_password_hash("password123"), "STU002", "CS", "1"))
        self.user_id2 = conn.execute('SELECT last_insert_rowid()').fetchone()[0]

        conn.commit()
        conn.close()

    def tearDown(self):
        os.close(self.db_fd)
        os.unlink(self.db_path)

    def login(self, email, password):
        return self.client.post('/login', data=dict(
            email=email,
            password=password
        ), follow_redirects=True)

    def test_upload_face_reference(self):
        self.login('student@test.com', 'password123')
        with open('tests/temp/lena.jpg', 'rb') as f: img_bytes = f.read()

        response = self.client.post('/api/student/face-references', data={
            'reference_image': (io.BytesIO(img_bytes), 'test.jpg')
        }, follow_redirects=True)

        self.assertIn(b'Image accepted', response.data)

        conn = get_db_connection(self.db_path)
        ref = conn.execute('SELECT * FROM student_face_references WHERE student_id = ?', (self.user_id,)).fetchone()
        conn.close()

        self.assertIsNotNone(ref)
        self.assertTrue(os.path.exists(os.path.join(self.private_dir, ref['image_path'])))

    @patch('app.add_student_face_reference', return_value="Database insertion failed mockup error")
    def test_upload_failure_orphan_cleanup(self, mock_add):
        self.login('student@test.com', 'password123')
        with open('tests/temp/lena.jpg', 'rb') as f: img_bytes = f.read()

        response = self.client.post('/api/student/face-references', data={
            'reference_image': (io.BytesIO(img_bytes), 'test.jpg')
        }, follow_redirects=True)

        self.assertIn(b'Database error', response.data)

        conn = get_db_connection(self.db_path)
        ref = conn.execute('SELECT * FROM student_face_references WHERE student_id = ?', (self.user_id,)).fetchone()
        conn.close()
        self.assertIsNone(ref)

        # Directory should be empty if cleanup worked
        self.assertEqual(len(os.listdir(self.private_dir)), 0)

    def test_delete_face_reference(self):
        add_student_face_reference(self.db_path, self.user_id, 'test.jpg', b'dummy_emb', 'Good')
        # Create a dummy file
        with open(os.path.join(self.private_dir, 'test.jpg'), 'w') as f: f.write('dummy')

        self.login('student@test.com', 'password123')

        conn = get_db_connection(self.db_path)
        ref = conn.execute('SELECT id FROM student_face_references WHERE student_id = ?', (self.user_id,)).fetchone()
        conn.close()

        response = self.client.post(f'/api/student/face-references/{ref["id"]}/delete', follow_redirects=True)
        self.assertIn(b'Reference image deleted.', response.data)

        self.assertFalse(os.path.exists(os.path.join(self.private_dir, 'test.jpg')))

    def test_unauthorized_delete(self):
        add_student_face_reference(self.db_path, self.user_id, 'test.jpg', b'dummy_emb', 'Good')
        with open(os.path.join(self.private_dir, 'test.jpg'), 'w') as f: f.write('dummy')

        conn = get_db_connection(self.db_path)
        ref = conn.execute('SELECT id FROM student_face_references WHERE student_id = ?', (self.user_id,)).fetchone()
        conn.close()

        self.login('student2@test.com', 'password123')
        response = self.client.post(f'/api/student/face-references/{ref["id"]}/delete', follow_redirects=True)
        self.assertIn(b'Reference not found or unauthorized', response.data)

        conn = get_db_connection(self.db_path)
        ref_still = conn.execute('SELECT id FROM student_face_references WHERE id = ?', (ref["id"],)).fetchone()
        conn.close()
        self.assertIsNotNone(ref_still)
        self.assertTrue(os.path.exists(os.path.join(self.private_dir, 'test.jpg')))

    def test_authorized_access(self):
        add_student_face_reference(self.db_path, self.user_id, 'test.jpg', b'dummy_emb', 'Good')
        with open(os.path.join(self.private_dir, 'test.jpg'), 'w') as f: f.write('dummy')

        conn = get_db_connection(self.db_path)
        ref = conn.execute('SELECT id FROM student_face_references WHERE student_id = ?', (self.user_id,)).fetchone()
        conn.close()

        self.login('student@test.com', 'password123')
        response = self.client.get(f'/api/student/face-references/{ref["id"]}/image')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, b'dummy')

    def test_unauthorized_access(self):
        add_student_face_reference(self.db_path, self.user_id, 'test.jpg', b'dummy_emb', 'Good')
        with open(os.path.join(self.private_dir, 'test.jpg'), 'w') as f: f.write('dummy')

        conn = get_db_connection(self.db_path)
        ref = conn.execute('SELECT id FROM student_face_references WHERE student_id = ?', (self.user_id,)).fetchone()
        conn.close()

        self.login('student2@test.com', 'password123')
        response = self.client.get(f'/api/student/face-references/{ref["id"]}/image')
        self.assertEqual(response.status_code, 403)

    def test_unauthenticated_access(self):
        add_student_face_reference(self.db_path, self.user_id, 'test.jpg', b'dummy_emb', 'Good')
        conn = get_db_connection(self.db_path)
        ref = conn.execute('SELECT id FROM student_face_references WHERE student_id = ?', (self.user_id,)).fetchone()
        conn.close()

        response = self.client.get(f'/api/student/face-references/{ref["id"]}/image')
        # Unauthenticated redirects to login
        self.assertEqual(response.status_code, 302)

    def test_invalid_reference(self):
        self.login('student@test.com', 'password123')
        response = self.client.get('/api/student/face-references/99999/image')
        self.assertEqual(response.status_code, 403)

if __name__ == '__main__':
    unittest.main()
