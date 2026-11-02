"""Route a selected error category; no raw logs or authentication data."""
import sys
from zhibi.cli import main

raise SystemExit(main(["triage", *sys.argv[1:]]))
