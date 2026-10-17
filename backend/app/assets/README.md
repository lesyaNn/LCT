`rostelecom-horizontal.png` is a print-resolution copy of the existing official
CRM asset `frontend/public/brand/rostelecom-horizontal.svg`. Aspect ratio and
colours are preserved; no new logo was created. Included in the backend image
under `app/assets` so PDF generation needs neither network access nor the frontend.

Regenerate from the repository root with the frontend's installed Sharp:

```sh
node -e "require('./frontend/node_modules/sharp')('frontend/public/brand/rostelecom-horizontal.svg').resize({width:1800}).png().toFile('backend/app/assets/rostelecom-horizontal.png')"
```

`city-time-zones.json` is a derived offline GeoNames city index. Source attribution,
CC BY 4.0 license, source hashes and snapshot date are embedded in the file.
Historical alternate names are excluded; names belonging to multiple zones map
to null. Regeneration and API behavior: `docs/UNIVERSITY_TIME_CONTACTS.md`.
