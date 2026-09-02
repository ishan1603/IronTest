import os
import sys
import tempfile

# Make the backend package importable as top-level modules (agents, models, ...)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Point the app at a throwaway database and a fixed signing key before any
# module reads settings, since get_settings() is cached for the process.
os.environ.setdefault(
    "DATABASE_URL",
    "sqlite:///" + os.path.join(tempfile.mkdtemp(prefix="irontest-test-"), "test.db"),
)
os.environ.setdefault("SECRET_KEY", "test-secret-key-not-used-in-production")
os.environ.setdefault("ENVIRONMENT", "test")
