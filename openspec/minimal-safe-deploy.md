# Минимально безопасный деплой на прод (db.t4g.micro)

Контекст: один `db.t4g.micro` (~95 доступных коннектов) обслуживает **и** метаданные
Superset, **и** аналитические запросы дашбордов. Цель — снять боль со скрина
(`QueuePool limit`, `Request timed out`) с минимальным риском. Главный рычаг на таком
железе — **кэш**, а не размер пула. Пул на undersized-БД увеличивать нельзя.

Бюджет коннектов: целимся в пик ≤ ~70 из ~95.

---

## 1. Что ОСТАВИТЬ из дифа (низкий риск, реальный выигрыш)

`docker/pythonpath_dev/superset_config.py`:
- Разнесение Redis по логическим DB: `3` data-cache, `4` sqllab.
- `APP_CACHE_TIMEOUT` / `DATA_CACHE_TIMEOUT` и кэши `CACHE_CONFIG` / `DATA_CACHE_CONFIG`
  / `THUMBNAIL_CACHE_CONFIG`.
- `RESULTS_BACKEND` на db4.
- Гейтинг `SQLALCHEMY_ECHO`, уровней логов engine/pool и `QUERY_LOGGER` за флагом.
- `pool_pre_ping=True`, `pool_recycle=1800`.

`docker/.env-goldie`:
- `SQLALCHEMY_ECHO=false`, `DATA_CACHE_TIMEOUT=3600` (1ч), `APP_CACHE_TIMEOUT=300`,
  `SQLALCHEMY_POOL_RECYCLE=1800`.

> Кэш данных — главный выигрыш: при попадании в кэш запрос к БД = 0. TTL=1ч
> выбран как баланс «разгрузка БД vs свежесть данных» для живого embedded-прода.
>
> ВАЖНО (решено при ревью): `FILTER_STATE_CACHE_CONFIG` /
> `EXPLORE_FORM_DATA_CACHE_CONFIG` НЕ переносим в Redis — оставляем дефолт Superset
> (метадата-БД, durable). Перенос ломал бы старые сохранённые `?filterState=` /
> `?form_data_key=` ссылки и терял состояние при flush Redis; выигрыш для пула
> ничтожный. Поэтому db5 (state) не используется.

---

## 2. Что УБРАТЬ из дифа (снимает 2 блокера + риск)

Удалить целиком блок Global Async Queries и сам флаг:
- В `FEATURE_FLAGS` — строку `'GLOBAL_ASYNC_QUERIES': ...`.
- Весь блок `# Global Async Queries` (`GLOBAL_ASYNC_QUERIES_TRANSPORT`,
  `..._JWT_SECRET`, `..._JWT_COOKIE_SECURE` ← это и есть строка с NameError,
  `..._CACHE_BACKEND`).
- Строку `REDIS_ASYNC_DB` (db6 больше не нужен).
- В `.env-goldie` — `GLOBAL_ASYNC_QUERIES=true` и комментарий про JWT-секрет.

> Это разом убирает: Блокер 1 (NameError `SESSION_COOKIE_SECURE` до объявления)
> и Риск 3 (async-cookie SameSite ломает графики в iframe). GAQ — отдельной фазой
> позже, после проверки на стейдже.

---

## 3. Что ИЗМЕНИТЬ (пулы вниз под micro)

`docker/.env-goldie`:
```
SERVER_WORKER_AMOUNT=2
SERVER_THREADS_AMOUNT=6
SQLALCHEMY_POOL_SIZE=6
SQLALCHEMY_MAX_OVERFLOW=4
SQLALCHEMY_POOL_TIMEOUT=30
```

`superset_config.py` — **безопасные дефолты в коде** на случай, если `.env-goldie`
не подхватится (сейчас он подключён как `required: false`!). Заменить дефолты
`SQLALCHEMY_POOL_SIZE`/`MAX_OVERFLOW` с `20`/`40` на `5`/`3`.

---

## 4. ВНЕ этих двух файлов — обязательно, иначе тюнинг бессмысленен

- **Пул аналитической БД** (Superset UI → Settings → Database Connections →
  ваша БД → Advanced → Performance / engine params): `pool_size=3`, `max_overflow=2`.
  Без этого аналитика по дефолту берёт 5+10 на процесс и съедает бюджет.
- **Celery concurrency = 2** (в команде воркера / env), чтобы фоновые задачи
  не открывали много коннектов.
- Сделать `docker/.env-goldie` `required: true` в `docker-compose-prod.yml`
  (чтобы прод-тюнинг не откатился молча на дефолты кода).

---

## 5. Проверка бюджета коннектов (цель ≤ ~70 из ~95)

```
web метаданные:   2 × (6+4) = 20
web аналитика:    2 × (3+2) = 10
celery:           ~10  (concurrency 2)
beat:             ~2
RDS admin/monitor ~8
──────────────────────────────
ИТОГО пик ≈ 50–60   ✅ с запасом под ~95
```

---

## 6. Чеклист перед деплоем

1. На RDS: `SHOW max_connections;` и `SELECT count(*) FROM pg_stat_activity;`
   — подтвердить реальный потолок и текущую загрузку.
2. Внести правки из п.1–4.
3. Проверить, что конфиг импортируется без ошибок (нет NameError):
   запуск контейнера / `python -c "import superset_config"`.
4. Выставить пул аналитической БД в UI (п.4).
5. Деплой. Под нагрузкой следить за `count(*) FROM pg_stat_activity` и логами на
   `QueuePool limit` / `too many connections`.
6. Откат = `git checkout` двух файлов.

---

## Фаза 2 (НЕ сейчас, отдельно после стейджа)

- GAQ с `GLOBAL_ASYNC_QUERIES_JWT_COOKIE_SAMESITE="None"` + проверка в реальном iframe.
- Cache warmup beat-таска для прогрева 24ч-кэша.
- Апгрейд RDS до `t4g.small`/`medium` или вынос аналитики в отдельную БД —
  настоящий долгосрочный фикс для undersized-инстанса.
```
