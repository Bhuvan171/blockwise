#!/usr/bin/env bash
# One-time download of the public "Hotel booking demand" data
# (António, de Almeida & Nunes, Data in Brief 22, 2019), TidyTuesday 2020-02-11 copy.
set -euo pipefail
cd "$(dirname "$0")/.."
URL="https://raw.githubusercontent.com/rfordatascience/tidytuesday/master/data/2020/2020-02-11/hotels.csv"
OUT="data/raw/hotels.csv"
EXPECTED=16855599
mkdir -p data/raw
if [ ! -f "$OUT" ]; then curl -fsSL "$URL" -o "$OUT"; fi
SIZE=$(stat -c %s "$OUT")
if [ "$SIZE" -ne "$EXPECTED" ]; then echo "Size mismatch: $SIZE != $EXPECTED" >&2; exit 1; fi
echo "OK $OUT ($SIZE bytes)"
