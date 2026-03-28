# conftest.py – pytest configuration for the Kassa integration tests
# Adds the integratie/ directory to sys.path so that receiver, sender, etc.
# can be imported directly without a package prefix.

import os
import sys

INTEGRATIE_DIR = os.path.join(os.path.dirname(__file__), "..", "integratie")
sys.path.insert(0, os.path.abspath(INTEGRATIE_DIR))
