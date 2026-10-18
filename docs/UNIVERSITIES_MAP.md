# Карта вузов

На странице «Вузы» один переключатель «Карточки / Таблица / Карта». При открытии страницы показываются существующие карточки. Все режимы используют одни URL-фильтры; карточки и таблица используют общий запрос списка, карта — существующий агрегированный запрос.

## Географические данные

- Границы: [Natural Earth Admin 1, 1:10m](https://www.naturalearthdata.com/downloads/10m-cultural-vectors/10m-admin-1-states-provinces/), [public domain](https://www.naturalearthdata.com/about/terms-of-use/). Исходный GeoJSON SHA-256: `22d0e3ad85eb3e27f17cabf8ba2d50e554fbc27a87796ff891d958185da62fb5`. В статическом файле 89 регионов: прежние 85 и `UA.05` (Донецкая область), `UA.14` (Луганская область), `UA.26` (Запорожская область), `UA.08` (Херсонская область). Все контуры взяты из **одного** набора Natural Earth и спроецированы прежним преобразованием `(lon − 18) × 6.5; (84 − lat) × 10.2` в SVG `1160 × 450`. Перед преобразованием Mapshaper 0.7.88 упрощает общие границы с сохранением топологии до 15% вершин (`keep-shapes`) и очищает пересечения (`clean`). Статический файл около 250 КБ вместо 1,6 МБ без упрощения.
- Города: [GeoNames cities500](https://download.geonames.org/export/dump/cities500.zip), [русские варианты RU](https://download.geonames.org/export/dump/alternatenames/RU.zip) и [русские варианты UA](https://download.geonames.org/export/dump/alternatenames/UA.zip), [CC BY 4.0](https://www.geonames.org/about.html). SHA-256: `fedf197c2b4aabffe5941ff85be5c5bd101b85ea00547547d3326e21df63ccce`, `698035350409def65795775d7326ec2e55006e319a378dc8af795935b2e4724c`, `5d669c50e130161e3821c0e4077ff56c1b6f5ae02b5eabdd679f8ad10ef60150` соответственно.

Карта использует именования областей и коды `gn_a1_code` выбранной версии Natural Earth, а не утверждает универсальную политическую классификацию. Статус и границы этих территорий оспариваются на международном уровне; изображение-ориентир не использовалось как источник координат.

Индекс городов строится по точному `admin1` каждой записи GeoNames. Для добавленных территорий включены только четыре перечисленных кода UA. Русские варианты имён учитываются без исторических названий. Если одно нормализованное название относится к нескольким регионам, код равен `null`. Например, «Донецк» неоднозначен из-за одноимённого города в Ростовской области. Единственный вуз с таким городом в текущей базе — «Донецкий национальный технический университет» — привязан к `UA.05` по [опубликованному адресу самого вуза](https://dev.donntu.ru/sveden/common). Для других неоднозначных названий регион не угадывается: они показываются отдельно под картой. Совпадение по подстроке и геокодирование в браузере не используются.

Для воспроизводимого обновления скачайте четыре исходных файла и выполните из корня проекта:

```bash
python3 - <<'PY'
import json
from pathlib import Path

source = json.loads(Path('/path/ne_10m_admin_1_states_provinces.geojson').read_text())
added = {'UA.05', 'UA.14', 'UA.26', 'UA.08'}
features = [feature for feature in source['features'] if (
    (feature['properties'].get('admin') == 'Russia' and feature['properties'].get('gn_a1_code') not in (None, 'RU.'))
    or feature['properties'].get('gn_a1_code') in added
)]
Path('/tmp/university-map-regions-source.geojson').write_text(json.dumps({'type': 'FeatureCollection', 'features': features}))
PY
npx --yes mapshaper@0.7.88 /tmp/university-map-regions-source.geojson -simplify 15% keep-shapes -o force /tmp/university-map-regions-simplified.geojson
npx --yes mapshaper@0.7.88 /tmp/university-map-regions-simplified.geojson -clean -o force /tmp/university-map-regions-clean.geojson
cd backend
PYTHONPATH=. ./.venv/bin/python -m scripts.build_university_map_assets /path/cities500.zip /path/RU.zip /path/UA.zip /tmp/university-map-regions-clean.geojson --source-sha256 22d0e3ad85eb3e27f17cabf8ba2d50e554fbc27a87796ff891d958185da62fb5
```

Генератор обновляет `backend/app/assets/city-regions.json` и `frontend/public/maps/russia-regions.json`. Эти файлы загружаются локально; внешний геосервис при открытии страницы не вызывается. Сведения об источниках и лицензии GeoNames приведены выше.

## Данные и права

`GET /api/v1/universities/map` использует те же `university_conditions`, `UnifiedFilter` и `apply_security_scope`, что и список. Право `university.read` проверяется в маршруте. Ответ содержит только видимые пользователю вузы и лёгкие поля для карты. Три SQL-запроса получают выборку вузов, статусы связанных программ и вузы с активным Workflow; N+1 запросов нет. Геометрия кэшируется отдельно от данных.

«Программа запущена» означает сохранённый `university_programs.status = 'launched'`. «Программа в работе» означает `status = 'active'`. «Вуз с активным Workflow» означает существование `workflow_instances.status = 'active'`. Сам факт связи программы с вузом не считается запуском. Заливка региона отражает только количество вузов по текущим фильтрам.

Карта хранит положение и масштаб вне React state и применяет изменения один раз за кадр через `requestAnimationFrame`. Наведение обновляет данные подсказки только при смене региона. Мемоизированный слой SVG-полигонов не перерисовывается при перемещении указателя; интерактивна только заливка региона, а подсказка игнорирует события указателя.
