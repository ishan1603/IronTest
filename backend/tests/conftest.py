import os
import sys

# Make the backend package importable as top-level modules (agents, models, ...)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
