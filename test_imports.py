#!/usr/bin/env python3
"""Test that the imports work correctly."""

import sys
import os

# Add the current directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from library_assistant.app import app
    from library_assistant.models import Session, Citation, AskRequest
    from library_assistant.config import Settings
    from library_assistant.dependencies import SessionDep, get_settings
    print("All imports successful!")
except Exception as e:
    print(f"Import error: {e}")
    sys.exit(1)