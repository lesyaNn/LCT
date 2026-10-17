"""Generate a small offline Russian city index from a downloaded GeoNames ZIP.

No network requests. Download cities500.zip separately; pass --snapshot-date.
Generated JSON is checked in and included in the backend package.
"""

import argparse
import hashlib
import io
import json
from collections import defaultdict
from pathlib import Path
from zipfile import ZipFile

from app.modules.universities.city_time import CITY_INDEX, normalize_city


def build(source: Path, alternate_names: Path, snapshot_date: str) -> dict:
    candidates: dict[str, set[str]] = defaultdict(set)
    zones_by_id: dict[str, str] = {}
    count = 0
    with ZipFile(source) as archive, archive.open("cities500.txt") as member:
        for line in io.TextIOWrapper(member, encoding="utf-8"):
            row = line.rstrip("\n").split("\t")
            if len(row) != 19 or row[8] != "RU" or row[6] != "P" or not row[17]:
                continue
            count += 1
            zones_by_id[row[0]] = row[17]
            for name in {row[1], row[2]}:
                key = normalize_city(name)
                if key:
                    candidates[key].add(row[17])
    # Unlike the comma-separated aliases in cities500, V2 marks historical
    # names. Otherwise Kaliningrad (the former name of Korolyov) is ambiguous.
    with ZipFile(alternate_names) as archive, archive.open("RU.txt") as member:
        for line in io.TextIOWrapper(member, encoding="utf-8"):
            row = line.rstrip("\n").split("\t")
            if len(row) < 8 or row[1] not in zones_by_id or row[2] != "ru" or row[7] == "1":
                continue
            if len(row) > 9 and row[9].strip():
                continue
            key = normalize_city(row[3])
            if key:
                candidates[key].add(zones_by_id[row[1]])
    cities = {
        key: next(iter(zones)) if len(zones) == 1 else None
        for key, zones in sorted(candidates.items())
    }
    # Conventional abbreviations, not substring matching or geocoding guesses.
    cities.update({"мск": "Europe/Moscow", "спб": "Europe/Moscow", "питер": "Europe/Moscow"})
    return {
        "source": "https://download.geonames.org/export/dump/cities500.zip",
        "attribution": "GeoNames, CC BY 4.0, https://www.geonames.org/",
        "license": "https://creativecommons.org/licenses/by/4.0/",
        "snapshot_date": snapshot_date,
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "names_source": "https://download.geonames.org/export/dump/alternatenames/RU.zip",
        "names_sha256": hashlib.sha256(alternate_names.read_bytes()).hexdigest(),
        "country": "RU",
        "settlements": count,
        "cities": dict(sorted(cities.items())),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--alternate-names", type=Path, required=True)
    parser.add_argument("--snapshot-date", required=True)
    parser.add_argument("--output", type=Path, default=CITY_INDEX)
    args = parser.parse_args()
    result = build(args.source, args.alternate_names, args.snapshot_date)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        f"{result['settlements']} settlements, {len(result['cities'])} names; output: {args.output}"
    )


if __name__ == "__main__":
    main()
