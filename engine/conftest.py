"""Put the engine root on sys.path so `import modules.*` works under pytest."""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
