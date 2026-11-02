"""Thin entrypoint: one public homepage HEAD, without account credentials."""
import sys
from zhibi.cli import main

if __name__ == "__main__":
    raise SystemExit(main(["check", "--network", "--connectivity"] + sys.argv[1:]))
