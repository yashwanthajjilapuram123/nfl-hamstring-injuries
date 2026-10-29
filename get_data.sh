#!/usr/bin/env bash
# Downloads public NFL data from the nflverse project (https://github.com/nflverse/nflverse-data).
set -e
mkdir -p data && cd data
B=https://github.com/nflverse/nflverse-data/releases/download
for y in $(seq 2009 2025); do [ -f injuries_$y.csv ] || curl -sfL -o injuries_$y.csv $B/injuries/injuries_$y.csv || echo "no injuries $y"; done
for y in $(seq 2012 2025); do [ -f snap_counts_$y.csv ] || curl -sfL -o snap_counts_$y.csv $B/snap_counts/snap_counts_$y.csv || echo "no snaps $y"; done
[ -f players.csv ] || curl -sfL -o players.csv $B/players/players.csv
echo done
