import sys
import os

# Add openmemory/api to sys.path so that `app.*` imports resolve
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "openmemory", "api"))
