"""Build the offline city-to-region index and compact map paths from source exports.

Inputs are downloaded separately from GeoNames and Natural Earth. No network
access is needed at runtime. Ambiguous city names deliberately resolve to null.
"""

import argparse
import hashlib
import io
import json
from collections import defaultdict
from pathlib import Path
from zipfile import ZipFile

from app.modules.universities.city_time import normalize_city

ROOT = Path(__file__).resolve().parents[2]
CITY_OUTPUT = ROOT / "backend/app/assets/city-regions.json"
MAP_OUTPUT = ROOT / "frontend/public/maps/russia-regions.json"
NAMES = {
    "RU.06": "Архангельская область",
    "RU.12": "Чеченская Республика",
    "RU.15": "Чукотский автономный округ",
    "RU.19": "Республика Ингушетия",
    "RU.27": "Карачаево-Черкесская Республика",
    "RU.48": "Москва",
    "RU.63": "Республика Саха (Якутия)",
    "RU.66": "Санкт-Петербург",
    "RU.89": "Еврейская автономная область",
    "RU.90": "Пермский край",
    "RU.92": "Камчатский край",
    "RU.93": "Забайкальский край",
    "UA.11": "Республика Крым",
    "UA.20": "Севастополь",
    "UA.05": "Донецкая область",
    "UA.14": "Луганская область",
    "UA.26": "Запорожская область",
    "UA.08": "Херсонская область",
}
ADDED_REGION_CODES = {"UA.05", "UA.14", "UA.26", "UA.08"}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def city_regions(cities_zip: Path, names_zip: Path, ua_names_zip: Path) -> dict[str, str | None]:
    candidates: dict[str, set[str]] = defaultdict(set)
    codes_by_id: dict[str, str] = {}
    with ZipFile(cities_zip) as archive, archive.open("cities500.txt") as member:
        for line in io.TextIOWrapper(member, encoding="utf-8"):
            row = line.rstrip("\n").split("\t")
            if len(row) != 19 or row[6] != "P" or not row[10]:
                continue
            code = f"{row[8]}.{row[10]}"
            if row[8] != "RU" and code not in ADDED_REGION_CODES:
                continue
            codes_by_id[row[0]] = code
            for name in {row[1], row[2]}:
                if key := normalize_city(name):
                    candidates[key].add(code)
    for archive_path, filename in ((names_zip, "RU.txt"), (ua_names_zip, "UA.txt")):
        with ZipFile(archive_path) as archive, archive.open(filename) as member:
            for line in io.TextIOWrapper(member, encoding="utf-8"):
                row = line.rstrip("\n").split("\t")
                if len(row) < 8 or row[1] not in codes_by_id or row[2] != "ru" or row[7] == "1":
                    continue
                if len(row) > 9 and row[9].strip():
                    continue
                if key := normalize_city(row[3]):
                    candidates[key].add(codes_by_id[row[1]])
    # Conventional city abbreviations are explicit aliases, never fuzzy matches.
    candidates["мск"].add("RU.48")
    candidates["спб"].add("RU.66")
    return {key: next(iter(codes)) if len(codes) == 1 else None for key, codes in sorted(candidates.items())}


def rings(geometry: dict):
    if geometry["type"] == "Polygon":
        yield from geometry["coordinates"]
    else:
        for polygon in geometry["coordinates"]:
            yield from polygon


def path_for(geometry: dict) -> str:
    parts = []
    for ring in rings(geometry):
        points = []
        for lon, lat, *_ in ring:
            if lon < 0:
                lon += 360  # Chukotka islands across the antimeridian.
            points.append(f"{(lon - 18) * 6.5:.1f},{(84 - lat) * 10.2:.1f}")
        if points:
            parts.append("M" + "L".join(points) + "Z")
    return "".join(parts)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cities", type=Path)
    parser.add_argument("names", type=Path)
    parser.add_argument("ua_names", type=Path)
    parser.add_argument("geometry", type=Path)
    parser.add_argument("--source-sha256", help="SHA-256 of the original Natural Earth GeoJSON before topology-preserving simplification")
    args = parser.parse_args()
    city_codes = city_regions(args.cities, args.names, args.ua_names)
    geo = json.loads(args.geometry.read_text(encoding="utf-8"))
    regions = []
    for feature in geo["features"]:
        props = feature["properties"]
        code = props.get("gn_a1_code")
        is_russian_region = props.get("admin") == "Russia" and code not in (None, "RU.")
        if not (is_russian_region or code in ADDED_REGION_CODES):
            continue
        regions.append({
            "code": code,
            "name": NAMES.get(code) or props.get("name_local") or props.get("name_en") or props["name"],
            "path": path_for(feature["geometry"]),
        })
    regions.sort(key=lambda item: item["name"])
    CITY_OUTPUT.write_text(json.dumps({
        "source": "https://download.geonames.org/export/dump/cities500.zip",
        "source_sha256": sha(args.cities),
        "names_source": "https://download.geonames.org/export/dump/alternatenames/RU.zip",
        "names_sha256": sha(args.names),
        "ua_names_source": "https://download.geonames.org/export/dump/alternatenames/UA.zip",
        "ua_names_sha256": sha(args.ua_names),
        "license": "CC BY 4.0, https://www.geonames.org/",
        "cities": city_codes,
    }, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    MAP_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    MAP_OUTPUT.write_text(json.dumps({
        "source": "https://github.com/nvkelso/natural-earth-vector/blob/master/geojson/ne_10m_admin_1_states_provinces.geojson",
        "source_sha256": args.source_sha256 or sha(args.geometry),
        "processed_sha256": sha(args.geometry),
        "processing": "Mapshaper 0.7.88, 15% topology-preserving simplification, keep-shapes, clean",
        "license": "Natural Earth public domain, https://www.naturalearthdata.com/about/terms-of-use/",
        "viewBox": "0 0 1160 450",
        "regions": regions,
    }, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"{len(city_codes)} city names; {len(regions)} map regions")


if __name__ == "__main__":
    main()
