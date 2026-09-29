import unittest
import os
import io
import shutil
from app import app
from database.database import get_db_connection
from tests.csrf_wrapper import CSRFTestClient

class TestRegistrationFaceValidation(unittest.TestCase):
    def setUp(self):
        app.config['TESTING'] = True
        app.config['DATABASE'] = 'test_database/test_reg_face.db'
        self.private_dir = os.path.join(app.root_path, 'tests', 'temp', 'private_refs')
        app.config['PRIVATE_REF_FOLDER'] = self.private_dir
        os.makedirs(self.private_dir, exist_ok=True)

        self.client = CSRFTestClient(app.test_client())

        from database.database import init_db
        init_db(app.config['DATABASE'])

    def tearDown(self):
        if os.path.exists(app.config['DATABASE']):
            os.remove(app.config['DATABASE'])
        if os.path.exists(self.private_dir):
            shutil.rmtree(self.private_dir)

    def get_valid_image(self):
        with open('tests/temp/lena.jpg', 'rb') as f:
            return f.read()

    def get_invalid_image(self):
        with open('tests/temp/zero_face.jpg', 'rb') as f:
            return f.read()

    def get_multiple_face_image(self):
        with open('tests/temp/multi_face.jpg', 'rb') as f:
            return f.read()

    def test_01_registration_with_0_photos(self):
        # By bypassing our CSRF wrapper's auto-injection for photo_1
        data = dict(
            name='S1', email='s1@example.com', password='password', confirm_password='password',
            student_id='S100', course='C1', semester='1'
        )
        # We manually inject 'photo_1' as empty so wrapper doesn't trigger
        data['photo_1'] = ''

        rv = self.client.post('/register/student', data=data, follow_redirects=True)
        self.assertIn(b'Please provide all 5 face photos.', rv.data)

    def test_02_registration_with_3_photos(self):
        data = dict(
            name='S1', email='s1@example.com', password='password', confirm_password='password',
            student_id='S100', course='C1', semester='1'
        )
        img = self.get_valid_image()
        data['photo_1'] = (io.BytesIO(img), '1.jpg')
        data['photo_2'] = (io.BytesIO(img), '2.jpg')
        data['photo_3'] = (io.BytesIO(img), '3.jpg')

        rv = self.client.post('/register/student', data=data, follow_redirects=True)
        self.assertIn(b'Please provide all 5 face photos.', rv.data)

    def test_03_registration_invalid_photo(self):
        data = dict(
            name='S1', email='s1@example.com', password='password', confirm_password='password',
            student_id='S100', course='C1', semester='1'
        )
        img = self.get_valid_image()
        inv_img = self.get_invalid_image()
        data['photo_1'] = (io.BytesIO(img), '1.jpg')
        data['photo_2'] = (io.BytesIO(img), '2.jpg')
        data['photo_3'] = (io.BytesIO(inv_img), '3.jpg')
        data['photo_4'] = (io.BytesIO(img), '4.jpg')
        data['photo_5'] = (io.BytesIO(img), '5.jpg')

        rv = self.client.post('/register/student', data=data, follow_redirects=True)
        self.assertIn(b'too blurry', rv.data.lower())

        # Verify no orphan files were saved and user not created
        conn = get_db_connection(app.config['DATABASE'])
        user = conn.execute("SELECT * FROM users WHERE email='s1@example.com'").fetchone()
        conn.close()
        self.assertIsNone(user)
        self.assertEqual(len(os.listdir(self.private_dir)), 0)

    def test_04_registration_multiple_faces(self):
        data = dict(
            name='S1', email='s1@example.com', password='password', confirm_password='password',
            student_id='S100', course='C1', semester='1'
        )
        img = self.get_valid_image()
        multi_img = self.get_multiple_face_image()
        data['photo_1'] = (io.BytesIO(img), '1.jpg')
        data['photo_2'] = (io.BytesIO(img), '2.jpg')
        data['photo_3'] = (io.BytesIO(img), '3.jpg')
        data['photo_4'] = (io.BytesIO(multi_img), '4.jpg')
        data['photo_5'] = (io.BytesIO(img), '5.jpg')

        rv = self.client.post('/register/student', data=data, follow_redirects=True)
        self.assertIn(b'must contain only your face', rv.data.lower())

    def test_05_successful_registration_5_photos(self):
        data = dict(
            name='S2', email='s2@example.com', password='password', confirm_password='password',
            student_id='S102', course='C1', semester='1'
        )
        img = self.get_valid_image()
        data['photo_1'] = (io.BytesIO(img), '1.jpg')
        data['photo_2'] = (io.BytesIO(img), '2.jpg')
        data['photo_3'] = (io.BytesIO(img), '3.jpg')
        data['photo_4'] = (io.BytesIO(img), '4.jpg')
        data['photo_5'] = (io.BytesIO(img), '5.jpg')

        rv = self.client.post('/register/student', data=data, follow_redirects=True)
        self.assertIn(b'registered successfully', rv.data)

        # Check DB
        conn = get_db_connection(app.config['DATABASE'])
        user = conn.execute("SELECT * FROM users WHERE email='s2@example.com'").fetchone()
        self.assertIsNotNone(user)

        refs = conn.execute("SELECT * FROM student_face_references WHERE student_id=?", (user['id'],)).fetchall()
        self.assertEqual(len(refs), 5)
        conn.close()

        # Check files exist
        saved_files = os.listdir(self.private_dir)
        self.assertEqual(len(saved_files), 5)

if __name__ == '__main__':
    unittest.main()
