"""Explicitly enabled ipify request; see zhibi plan --network."""
import sys
from zhibi.cli import main

raise SystemExit(main(["check", "--network", *sys.argv[1:]]))
