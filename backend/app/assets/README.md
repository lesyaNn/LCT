`rostelecom-horizontal.png` is a print-resolution copy of the existing official
CRM asset `frontend/public/brand/rostelecom-horizontal.svg`. Aspect ratio and
colours are preserved; no new logo was created. Included in the backend image
under `app/assets` so PDF generation needs neither network access nor the frontend.

Regenerate from the repository root with the frontend's installed Sharp:

```sh
node -e "require('./frontend/node_modules/sharp')('frontend/public/brand/rostelecom-horizontal.svg').resize({width:1800}).png().toFile('backend/app/assets/rostelecom-horizontal.png')"
```
