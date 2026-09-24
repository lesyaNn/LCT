# P5-16-01: ArchiMate + PNG

- `architecture.archimate` — модель (ArchiMate Open Exchange). Открыть в
  [Archi](https://www.archimatetool.com), дальше `File → Export Model As
  Image` → `architecture.png` (PNG для презентации положить рядом, в git не
  обязательно — PNG трекаем только релизный).
- Быстрый PNG без Archi — из Mermaid-блока `docs/ARCHITECTURE.md`:

```bash
npx @mermaid-js/mermaid-cli -i arch-context.mmd -o architecture.png
```

(`arch-context.mmd` — скопировать `flowchart LR`-блок из ARCHITECTURE.md.)
