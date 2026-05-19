"""
Entry point for CI integration tests.

Called by ci.yml:
    docker exec kassa_integratie python tools/run_integration_tests.py

Runs the bus integration test suite against the live Odoo stack that CI
spins up via docker-compose. Exits non-zero on any test failure so the CI
job fails and reports the issue.
"""
import subprocess
import sys
import os

# Inside the container the integratie package is at /integratie/
test_file = os.path.join(os.path.dirname(__file__), "..", "tests", "test_bus_integration.py")
test_file = os.path.normpath(test_file)

result = subprocess.run(
    [sys.executable, "-m", "pytest", test_file, "-v", "--tb=short"],
    cwd=os.path.dirname(test_file),
)
sys.exit(result.returncode)
