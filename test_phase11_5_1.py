import unittest
import os
import sqlite3
import numpy as np
from database.database import init_db, get_db_connection, upsert_face_embedding
from utils.face_recognition_engine import FaceRecognitionEngine, FACE_RECOGNITION_THRESHOLD

class Phase11_5_1_TestCase(unittest.TestCase):
    def setUp(self):
        self.db_path = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'test_attendance_p11_5_1.db')
        if os.path.exists(self.db_path):
            os.remove(self.db_path)
        init_db(self.db_path)
        
        # Insert a dummy user
        conn = get_db_connection(self.db_path)
        conn.execute('''
            INSERT INTO users (name, email, password_hash, role, student_id)
            VALUES (?, ?, ?, ?, ?)
        ''', ("Test Student", "test@example.com", "hash", "student", "S100"))
        conn.commit()
        self.user_id = conn.execute("SELECT id FROM users WHERE email='test@example.com'").fetchone()['id']
        conn.close()
        
    def tearDown(self):
        if os.path.exists(self.db_path):
            try:
                os.remove(self.db_path)
            except:
                pass

    def get_image_bytes(self, path):
        with open(path, 'rb') as f:
            return f.read()

    def enroll_lena(self):
        # We need Lena's embedding to enroll her
        from utils.cv_engine import extract_single_face_embedding
        img_bytes = self.get_image_bytes('tests/temp/lena.jpg')
        res = extract_single_face_embedding(img_bytes)
        self.assertTrue(res['success'])
        
        upsert_face_embedding(self.db_path, self.user_id, res['embedding'], res['model_name'])
        
    def test_01_model_loading_and_empty_db(self):
        # Empty enrollment DB
        engine = FaceRecognitionEngine(self.db_path)
        self.assertEqual(len(engine.enrolled_students), 0)
        
        img_bytes = self.get_image_bytes('tests/temp/lena.jpg')
        res = engine.process_classroom_image(img_bytes)
        
        self.assertTrue(res['success'])
        self.assertEqual(res['total_detected_faces'], 1)
        self.assertEqual(res['recognized_faces'], 0)
        self.assertEqual(res['unknown_faces'], 1)
        
        face = res['results'][0]
        self.assertFalse(face['recognized'])
        self.assertIsNone(face['user_id'])
        
    def test_02_known_enrolled_face(self):
        self.enroll_lena()
        engine = FaceRecognitionEngine(self.db_path)
        self.assertEqual(len(engine.enrolled_students), 1)
        
        img_bytes = self.get_image_bytes('tests/temp/lena.jpg')
        res = engine.process_classroom_image(img_bytes)
        
        self.assertTrue(res['success'])
        self.assertEqual(res['total_detected_faces'], 1)
        self.assertEqual(res['recognized_faces'], 1)
        self.assertEqual(res['unknown_faces'], 0)
        
        face = res['results'][0]
        self.assertTrue(face['recognized'])
        self.assertEqual(face['user_id'], self.user_id)
        self.assertGreaterEqual(face['similarity'], FACE_RECOGNITION_THRESHOLD)

    def test_03_no_face_image(self):
        engine = FaceRecognitionEngine(self.db_path)
        img_bytes = self.get_image_bytes('tests/temp/zero_face.jpg')
        res = engine.process_classroom_image(img_bytes)
        
        self.assertTrue(res['success'])
        self.assertEqual(res['total_detected_faces'], 0)
        
    def test_04_multiple_faces_duplicate_recognized(self):
        self.enroll_lena()
        engine = FaceRecognitionEngine(self.db_path)
        
        # Image contains two lenas
        img_bytes = self.get_image_bytes('tests/temp/multi_face.jpg')
        res = engine.process_classroom_image(img_bytes)
        
        self.assertTrue(res['success'])
        self.assertEqual(res['total_detected_faces'], 2)
        self.assertEqual(res['recognized_faces'], 2)
        self.assertEqual(res['unknown_faces'], 0)
        
        # Ensure we can identify the duplicates
        ids = [f['user_id'] for f in res['results']]
        self.assertEqual(ids, [self.user_id, self.user_id])
        
    def test_05_malformed_embedding(self):
        # Insert bad embedding
        conn = get_db_connection(self.db_path)
        conn.execute('''
            INSERT INTO face_embeddings (student_id, embedding, model_name)
            VALUES (?, ?, ?)
        ''', (self.user_id, b'bad_data_not_float32', 'sface_2021dec'))
        conn.commit()
        conn.close()
        
        engine = FaceRecognitionEngine(self.db_path)
        # Should silently skip the bad embedding
        self.assertEqual(len(engine.enrolled_students), 0)

    def test_06_similarity_threshold_behavior(self):
        self.enroll_lena()
        
        # We manually modify the enrolled student's embedding to be orthogonal
        engine = FaceRecognitionEngine(self.db_path)
        orthogonal_feature = np.zeros((1, 128), dtype=np.float32)
        orthogonal_feature[0, 0] = 1.0 # just an arbitrary vector that won't match lena
        engine.enrolled_students[0]['feature'] = orthogonal_feature
        
        img_bytes = self.get_image_bytes('tests/temp/lena.jpg')
        res = engine.process_classroom_image(img_bytes)
        
        self.assertTrue(res['success'])
        self.assertEqual(res['total_detected_faces'], 1)
        self.assertEqual(res['recognized_faces'], 0) # Fails threshold
        self.assertEqual(res['unknown_faces'], 1)

    def test_07_invalid_image(self):
        engine = FaceRecognitionEngine(self.db_path)
        res = engine.process_classroom_image(b'invalid bytes')
        self.assertFalse(res['success'])
        self.assertIn("Failed to decode image", res['error'])

if __name__ == '__main__':
    unittest.main(verbosity=2)
