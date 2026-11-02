"""Explicitly enable both disclosed IP data services for this run."""
import sys
from zhibi.cli import main

raise SystemExit(main(["check", "--network", "--ip-metadata", *sys.argv[1:]]))
