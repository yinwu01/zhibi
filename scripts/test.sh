#!/bin/sh
# Run the suite from a plain clone: no install, no network.
set -e
cd "$(dirname "$0")/.."
PYTHONPATH=src exec "${PYTHON:-python3}" -m unittest discover -s tests "$@"
