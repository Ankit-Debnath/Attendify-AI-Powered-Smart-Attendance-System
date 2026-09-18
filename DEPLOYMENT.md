# Attendify Deployment Guide

This guide covers deploying the Attendify application in a production environment.

## 1. Prerequisites
- Python 3.8+ 
- A modern production WSGI server (e.g., Gunicorn or Waitress)
- A reverse proxy for HTTPS (e.g., Nginx, Apache)

## 2. Initial Setup
Clone the repository and set up a virtual environment:
```bash
python -m venv myvenv
# On Windows:
myvenv\Scripts\activate
# On Linux/Mac:
source myvenv/bin/activate
```

## 3. Install Dependencies
```bash
pip install -r requirements.txt
```

## 4. Configuration
Create a `.env` file from the example:
```bash
cp .env.example .env
```
Edit `.env` to configure your production settings. 
**Important**: Generate a secure production secret for `FLASK_SECRET_KEY`:
```bash
python -c "import secrets; print(secrets.token_hex(32))"
```
Place this secret inside `.env`.

## 5. Model Files
Ensure that the YuNet and SFace ONNX models are present in your configured `MODEL_DIRECTORY` (default is the `models/` directory).
- `face_detection_yunet_2023mar.onnx`
- `face_recognition_sface_2021dec.onnx`

## 6. Database Initialization
Ensure the database schema is initialized:
```bash
python -c "from database.database import init_db; import os; init_db(os.environ.get('DATABASE_PATH', 'database/attendance.db'))"
```

## 7. Starting the Application
Do not use Flask's built-in development server in production. Use a WSGI server like Waitress (Windows) or Gunicorn (Linux).

Install Waitress (Windows):
```bash
pip install waitress
```

Start the application:
```bash
waitress-serve --host=0.0.0.0 --port=5000 wsgi:application
```

## 8. Reverse Proxy & HTTPS
For production, run Attendify behind a reverse proxy like Nginx. Configure Nginx to forward requests to `127.0.0.1:5000` and handle SSL termination. Ensure `SESSION_COOKIE_SECURE=1` is set in your `.env` when using HTTPS.

## 9. Monitoring
Check the `/health` endpoint to verify the application process and database connection are active.
Application logs are written to the directory specified by `LOG_DIRECTORY` (default is `logs/`).

## 10. Backups
Attendify uses SQLite. To safely back up the database:
1. Locate the file configured in `DATABASE_PATH` (default `database/attendance.db`).
2. Use standard SQLite backup tools: `sqlite3 attendance.db ".backup attendance_backup.db"`
Do not delete or overwrite the production database during migration.
