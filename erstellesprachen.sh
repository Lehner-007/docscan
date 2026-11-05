#!/bin/sh
set -eu
PROJECT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
/usr/bin/python3 -B "$PROJECT_DIR/packaging/build_languages.py"
exec /usr/bin/python3 -B "$PROJECT_DIR/packaging/build.py" languages "$@"
