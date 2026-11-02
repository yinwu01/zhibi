"""Export the self-contained browser probe page."""
import sys
from zhibi.cli import main

raise SystemExit(main(["browser", *sys.argv[1:]]))
