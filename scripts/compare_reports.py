"""Compare report states without exposing raw measurements."""
import sys
from zhibi.cli import main

raise SystemExit(main(["compare", *sys.argv[1:]]))
