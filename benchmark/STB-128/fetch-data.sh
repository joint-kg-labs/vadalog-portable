#!/bin/sh
# Fetch this scenario's source data from ChaseBench into data/10k.
#
# The data is 209 MB unpacked (111 relations, about 10 000 rows each), which is
# why it is not in this repository: ChaseBench ships it as a two-part split zip,
# and this script downloads the parts, joins them and unpacks them.
#
#   sh fetch-data.sh          # about 100 MB over the network
#
# Needs curl (or wget) and unzip. Run again to refresh; data/ is ignored by git.
set -e

scenario=STB-128
parts="001 002"
base="https://raw.githubusercontent.com/dbunibas/chasebench/master/scenarios/$scenario/data"

here=$(cd "$(dirname "$0")" && pwd)
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

for part in $parts; do
    echo "fetching data.zip.$part"
    if command -v curl >/dev/null 2>&1; then
        curl -fsSL "$base/data.zip.$part" -o "$tmp/data.zip.$part"
    else
        wget -q -O "$tmp/data.zip.$part" "$base/data.zip.$part"
    fi
done

cat "$tmp"/data.zip.* > "$tmp/data.zip"
mkdir -p "$here/data/10k"
unzip -q -o "$tmp/data.zip" -d "$here/data/10k"
echo "unpacked $(ls "$here/data/10k" | wc -l | tr -d ' ') files into data/10k"
