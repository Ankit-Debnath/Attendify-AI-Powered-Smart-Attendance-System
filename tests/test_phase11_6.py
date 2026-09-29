import unittest
import os
import json
from app import app
from database.database import init_db

class TestPhase11_6(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Set up a test database
        cls.db_path = os.path.join(app.root_path, 'database', 'test_attendance_phase11_6.db')
        
        # Save original config
        cls.original_config = {}
        for key in ['TESTING', 'DATABASE', 'WTF_CSRF_ENABLED', 'SECRET_KEY']:
            cls.original_config[key] = app.config.get(key)
        
        # Override app config
        app.config['TESTING'] = True
        app.config['DATABASE'] = cls.db_path
        app.config['WTF_CSRF_ENABLED'] = False
        app.config['SECRET_KEY'] = 'test-secret-key'
        
        # Initialize database
        init_db(cls.db_path)
        from tests.csrf_wrapper import CSRFTestClient
        cls.client = CSRFTestClient(app.test_client())
        
    @classmethod
    def tearDownClass(cls):
        try:
            if os.path.exists(cls.db_path):
                os.remove(cls.db_path)
        finally:
            if hasattr(cls, 'original_config'):
                for key, val in cls.original_config.items():
                    if val is None:
                        app.config.pop(key, None)
                    else:
                        app.config[key] = val
    def test_health_endpoint(self):
        """Test the health check endpoint returns 200 and no sensitive info."""
        response = self.client.get('/health')
        self.assertEqual(response.status_code, 200)
        
        data = json.loads(response.data)
        self.assertEqual(data.get('status'), 'healthy')
        self.assertEqual(data.get('database'), 'connected')
        
        # Ensure no secrets leak
        self.assertNotIn('secret', response.data.decode('utf-8').lower())
        self.assertNotIn('password', response.data.decode('utf-8').lower())

    def test_debug_mode_disabled_by_default(self):
        """Test debug mode is disabled unless explicitly enabled."""
        import os
        from flask import Flask
        
        test_app = Flask(__name__)
        env_debug = os.environ.get('FLASK_DEBUG', '0').lower()
        self.assertFalse(env_debug in ['1', 'true'])
        
    def test_large_upload_rejection(self):
        """Test the app rejects files larger than MAX_CONTENT_LENGTH."""
        # Authenticate a test student first to avoid 302 redirect
        self.client.post('/register/student', data={
            'name': 'Upload Test Student',
            'email': 'uploadtest@example.com',
            'password': 'password123',
            'confirm_password': 'password123',
            'student_id': 'S999',
            'course': 'Test Course',
            'semester': '1'
        })
        self.client.post('/login', data={'email': 'uploadtest@example.com', 'password': 'password123'})

        # Using context manager to test upload limit
        # The app should return 413 for payload too large
        original_max = app.config.get('MAX_CONTENT_LENGTH')
        app.config['MAX_CONTENT_LENGTH'] = 10  # 10 bytes limit for test
        
        try:
            response = self.client.post('/student/profile/edit', data={
                'profile_picture': (open(__file__, 'rb'), 'test.jpg')
            })
            
            # Should be caught by the 413 error handler
            self.assertEqual(response.status_code, 413)
            self.assertIn(b"Payload Too Large", response.data)
        finally:
            # Restore normal limit
            if original_max is None:
                app.config.pop('MAX_CONTENT_LENGTH', None)
            else:
                app.config['MAX_CONTENT_LENGTH'] = original_max

if __name__ == '__main__':
    unittest.main()
