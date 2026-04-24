#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

echo "FantasyBaby Tennis Cut"
echo
echo "Select cut engine:"
echo "  1. Legacy audio/visual rules"
echo "  2. New model-assisted ball tracking"
echo
echo "Tip: the curated singles full-rally recipe is documented in README.md"
echo
while true; do
  read -r -p "Enter 1 or 2: " cut_engine
  case "$cut_engine" in
    1)
      echo
      echo "Legacy audio/visual mode selected."
      echo
      uv --cache-dir .uv-cache run tennis-cut
      break
      ;;
    2)
      echo
      echo "New model-assisted mode selected."
      echo "If this is the first run, install dependencies with:"
      echo "uv sync --extra model"
      echo
      uv --cache-dir .uv-cache run tennis-cut --model-assist ball
      break
      ;;
    *)
      echo "Invalid selection. Please enter 1 or 2."
      echo
      ;;
  esac
done
