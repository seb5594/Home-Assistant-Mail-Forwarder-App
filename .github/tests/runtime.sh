#!/usr/bin/env bash
set -Eeuo pipefail

# Runs inside the built image (release pipeline): the unit and end-to-end tests of the
# application run against the code that was installed into the image.
export MF_CODE_DIR=/opt/mail-forwarder
export PYTHONDONTWRITEBYTECODE=1

command -v openssl >/dev/null || { echo 'FAIL: openssl is missing from the image' >&2; exit 1; }
echo 'PASS: openssl is installed'

python3 /tests/run_tests.py

test "$(cat /etc/mail-forwarder/version)" != "dev"
echo 'PASS: the image knows its version'
