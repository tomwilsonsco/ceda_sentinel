"""
Pytest configuration for ceda_sentinel tests.

Adds the src directory to sys.path to enable imports of ceda_s1, ceda_s2, etc.
"""
import sys
from pathlib import Path

# Add src directory to Python path
src_dir = Path(__file__).parent.parent / "src"
if src_dir.exists():
    sys.path.insert(0, str(src_dir))