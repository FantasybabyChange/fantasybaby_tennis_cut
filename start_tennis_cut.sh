#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"
uv --cache-dir .uv-cache run tennis-cut
