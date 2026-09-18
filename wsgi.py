"""
WSGI config for Attendify project.

This module exposes the WSGI callable as a module-level variable named ``application``.
"""

import os
from dotenv import load_dotenv

# Load environment variables from .env if present
load_dotenv()

from app import app as application

if __name__ == "__main__":
    application.run()
