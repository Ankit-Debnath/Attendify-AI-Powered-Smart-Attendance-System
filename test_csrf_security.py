import unittest
import os
from app import app
from database.database import init_db

class CSRFSecurityTestCase(unittest.TestCase):
    def setUp(self):
        app.config['TESTING'] = True
        # Keep CSRF enabled! Do not disable it.
        app.config['DATABASE'] = os.path.join(app.root_path, 'database', 'test_csrf.db')
        self.client = app.test_client()
        init_db(app.config['DATABASE'])

    def tearDown(self):
        if os.path.exists(app.config['DATABASE']):
            os.remove(app.config['DATABASE'])

    def test_01_post_without_csrf_is_rejected(self):
        # Sending a POST to a protected form submission route without a CSRF token
        rv = self.client.post('/login', data=dict(email='t1@example.com', password='password'))
        self.assertEqual(rv.status_code, 400)
        self.assertIn(b'Bad Request', rv.data)

    def test_02_post_with_valid_csrf_succeeds(self):
        # We fetch the GET route to get a valid CSRF token
        rv_get = self.client.get('/login')
        import re
        match = re.search(b'name="csrf_token" value="(.*?)"', rv_get.data)
        self.assertIsNotNone(match)
        token = match.group(1).decode('utf-8')

        # Now send the POST request with the valid CSRF token
        rv_post = self.client.post('/login', data=dict(
            email='test@example.com',
            password='wrongpassword',
            csrf_token=token
        ))
        
        # We expect a 200 OK because the CSRF was accepted, and it returns the login form with "Invalid email or password"
        self.assertEqual(rv_post.status_code, 200)
        self.assertIn(b'Invalid email or password', rv_post.data)
        
    def test_03_get_requests_continue_working(self):
        rv = self.client.get('/')
        self.assertEqual(rv.status_code, 200)
        self.assertIn(b'Attendify', rv.data)

if __name__ == '__main__':
    unittest.main()
