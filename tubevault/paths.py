import sys
from pathlib import Path


def resource_root():
    return Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent.parent))
