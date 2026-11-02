"""Thin entrypoint: opt-in IPv6 endpoint observation."""
import sys
from zhibi.cli import main

if __name__ == "__main__":
    raise SystemExit(main(["check", "--network", "--ipv6"] + sys.argv[1:]))
