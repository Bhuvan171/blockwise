#!/usr/bin/env bash
# Official SingStat tables (Singapore Open Data Licence; attribute "Department of Statistics Singapore").
# M550001: International visitor arrivals by place of residence, monthly (row "India").
# M550081: Hotel statistics, monthly (room rate and occupancy by hotel size band).
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p data/raw
for T in M550001 M550081; do
  curl -fsS -m 120 "https://tablebuilder.singstat.gov.sg/api/table/tabledata/$T" \
    -H "Accept: application/json" -H "User-Agent: blockwise-research" -o "data/raw/singstat_$T.json"
  echo "OK data/raw/singstat_$T.json ($(wc -c < "data/raw/singstat_$T.json" | tr -d ' ') bytes)"
done
