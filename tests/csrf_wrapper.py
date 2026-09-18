import re

class CSRFTestClient:
    def __init__(self, client):
        self.client = client
        self.csrf_token = None

    def get(self, *args, **kwargs):
        rv = self.client.get(*args, **kwargs)
        if rv and rv.data:
            match = re.search(b'meta name="csrf-token" content="(.*?)"', rv.data)
            if match:
                self.csrf_token = match.group(1).decode('utf-8')
            
        # If logging out, clear the token
        if args and args[0] == '/logout':
            self.csrf_token = None
            
        return rv

    def post(self, url, data=None, **kwargs):
        if data is None:
            data = {}
        if isinstance(data, dict):
            # Always get a fresh token for login and register routes to prevent stale session tokens
            if url in ['/login', '/register/student', '/register/teacher'] or not self.csrf_token:
                self.get('/')
                
            if self.csrf_token and 'csrf_token' not in data:
                data['csrf_token'] = self.csrf_token
        return self.client.post(url, data=data, **kwargs)
        
    def __getattr__(self, name):
        return getattr(self.client, name)
