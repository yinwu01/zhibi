"""Evaluate a marked synthetic input through the installed core."""
import sys
from zhibi.cli import main

raise SystemExit(main(["evaluate", *sys.argv[1:]]))
