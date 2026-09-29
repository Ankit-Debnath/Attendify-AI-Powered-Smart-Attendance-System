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
            else:
                match2 = re.search(b'name="csrf_token" value="(.*?)"', rv.data)
                if match2:
                    self.csrf_token = match2.group(1).decode('utf-8')

        # If logging out, clear the token
        if args and args[0] == '/logout':
            self.csrf_token = None

        return rv

    def post(self, url, data=None, **kwargs):
        if data is None:
            data = {}
        if isinstance(data, dict):
            if url in ['/login', '/register/student', '/register/teacher'] or not self.csrf_token:
                self.get('/')

            if self.csrf_token and 'csrf_token' not in data:
                data['csrf_token'] = self.csrf_token

            if url == '/register/student' and 'photo_1' not in data:
                import io, os
                img_path = 'tests/temp/lena.jpg' if os.path.exists('tests/temp/lena.jpg') else 'temp/lena.jpg'
                if not os.path.exists(img_path):
                    # fallback
                    img_path = os.path.join(os.path.dirname(__file__), 'temp', 'lena.jpg')
                if os.path.exists(img_path):
                    with open(img_path, 'rb') as f:
                        img_bytes = f.read()
                    for i in range(1, 6):
                        data[f'photo_{i}'] = (io.BytesIO(img_bytes), f'photo_{i}.jpg')

        return self.client.post(url, data=data, **kwargs)

    def __getattr__(self, name):
        return getattr(self.client, name)
