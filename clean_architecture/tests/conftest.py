"""Pytest configuration: add the project root to PYTHONPATH."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
