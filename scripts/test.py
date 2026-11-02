"""Run the offline repository suite with explicit local fixture configuration."""
from pathlib import Path
import os
import sys
import tempfile
import unittest


def main():
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "src"))
    with tempfile.TemporaryDirectory(prefix="bioduet-tests-") as scratch:
        os.environ["BW01_INTEGRATION_SCRATCH"] = scratch
        suite = unittest.defaultTestLoader.discover(str(root / "tests"))
        result = unittest.TextTestRunner(verbosity=1).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
