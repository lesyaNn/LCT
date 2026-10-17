# Карта вузов

Карта встроена во второе представление страницы «Вузы». Список и карта используют одно состояние фильтров. Список сохраняет переключение «Карточки / Таблица», а выбранное представление «Список / Карта» хранится в `localStorage`.

## Географические данные

- Границы субъектов: [Natural Earth Admin 1, 1:50m](https://www.naturalearthdata.com/downloads/50m-cultural-vectors/50m-admin-1-states-provinces/), [public domain](https://www.naturalearthdata.com/about/terms-of-use/). В репозитории хранится преобразованная в SVG-пути выборка 85 полигонов из исходного GeoJSON. Исходный SHA-256: `69a0e06e640b2d505858ae1cb63034e4677f3000b35a98e16312932b98c426b9`.
- Связь города с субъектом: [GeoNames cities500](https://download.geonames.org/export/dump/cities500.zip) и [русские варианты названий](https://download.geonames.org/export/dump/alternatenames/RU.zip), [CC BY 4.0](https://www.geonames.org/about.html). Исходные SHA-256: `fedf197c2b4aabffe5941ff85be5c5bd101b85ea00547547d3326e21df63ccce` и `698035350409def65795775d7326ec2e55006e319a378dc8af795935b2e4724c`.

Индекс городов создаётся из точного кода `admin1` каждой записи GeoNames. Русские варианты учитываются без исторических названий. Если одно нормализованное название относится к нескольким регионам, код равен `null`. Неизвестные и неоднозначные города показываются отдельно под картой. Совпадение названия города по подстроке и геокодирование в браузере не используются. Natural Earth содержит два полигона с кодами `UA.11` и `UA.20` в выборке `admin=Russia`; справочник городов RU их не сопоставляет автоматически.

Для воспроизводимого обновления скачайте три исходных файла и выполните из каталога `backend`:

```bash
PYTHONPATH=. ./.venv/bin/python -m scripts.build_university_map_assets /path/cities500.zip /path/RU.zip /path/ne_50m_admin_1_states_provinces.geojson
```

Генератор обновляет `backend/app/assets/city-regions.json` и `frontend/public/maps/russia-regions.json`. Эти файлы загружаются локально; внешний геосервис при открытии страницы не вызывается. Атрибуция GeoNames показана под картой.

## Данные и права

`GET /api/v1/universities/map` использует те же `university_conditions`, `UnifiedFilter` и `apply_security_scope`, что и список. Право `university.read` проверяется в маршруте. Ответ содержит только видимые пользователю вузы и лёгкие поля для карты. Три SQL-запроса получают выборку вузов, статусы связанных программ и вузы с активным Workflow; N+1 запросов нет. Геометрия кэшируется отдельно от данных. React отображает 85 регионов и не более 30 вузов в открытой панели одновременно.

«Программа запущена» означает сохранённый `university_programs.status = 'launched'`. «Программа в работе» означает `status = 'active'`. «Вуз с активным Workflow» означает существование `workflow_instances.status = 'active'`. Сам факт связи программы с вузом не считается запуском. Заливка региона отражает только количество вузов по текущим фильтрам.
