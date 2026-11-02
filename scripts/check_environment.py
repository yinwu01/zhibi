"""Thin standalone entrypoint; install the local package first."""
import sys
from zhibi.cli import main

raise SystemExit(main(["check", *sys.argv[1:]]))
