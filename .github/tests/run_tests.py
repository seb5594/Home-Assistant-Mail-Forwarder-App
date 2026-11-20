#!/usr/bin/env python3
"""Runs every test_*.py next to this file and prints one ``PASS: <name>`` line per passing test.

The release pipeline counts those lines, which is why the standard unittest output is not enough.
"""
import sys
import unittest
from pathlib import Path


class PassPrintingResult(unittest.TextTestResult):
    def addSuccess(self, test):  # noqa: N802 - name fixed by unittest
        super().addSuccess(test)
        print(f"PASS: {test.id().split('.', 1)[-1]}", flush=True)


def main() -> int:
    folder = Path(__file__).resolve().parent
    sys.path.insert(0, str(folder))
    suite = unittest.defaultTestLoader.discover(str(folder), pattern="test_*.py")
    runner = unittest.TextTestRunner(stream=sys.stderr, verbosity=1, resultclass=PassPrintingResult)
    return 0 if runner.run(suite).wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
