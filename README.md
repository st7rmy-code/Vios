# Сверка

Модуль измерения эффекта действий для клубов с абонементами: возвращаем ушедших
клиентов и честно считаем, сколько денег это принесло, с контрольной группой.

* `backend/` — Python 3.12, FastAPI, SQLAlchemy 2, Alembic, PostgreSQL, Pydantic v2.
* `frontend/` — Next.js 15, TypeScript, Tailwind, shadcn/ui, Recharts; клиент API из `backend/openapi.json`.
* `docker-compose.yml` — Postgres 16, MinIO (S3), бэкенд и фронтенд.

## Запуск

```bash
docker compose up --build
docker compose exec backend python -m app.cli create-admin admin <пароль>
# Интерфейс: http://localhost:3000, API: http://localhost:8000/docs

# Демо: бизнес, собственник owner/owner-pass, исполнитель coach/coach-pass,
# 2 000 ушедших клиентов, закрытый эксперимент с результатом, идущий и черновик
docker compose exec backend python scripts/demo.py admin <пароль>
```

## Тесты

```bash
cd backend
pip install ".[dev]"
SVERKA_DATABASE_URL=postgresql+psycopg://postgres@127.0.0.1:5432/sverka_test pytest -q
```

## Принципы

* Деньги считает только детерминированный код, в копейках. LLM нет.
* В базе нет ФИО, телефонов и email клиентов: CSV с такими колонками отклоняется
  целиком и не сохраняется.
* Деление на группы: HMAC-SHA256(seed, customer_id) внутри страт. Seed создаётся
  при регистрации, протокол после регистрации менять нельзя (409 в API и триггер в БД).
* Доверительные интервалы: бутстрэп 5000 повторов с seed из seed эксперимента,
  повторный расчёт даёт те же числа и тот же хэш.
* `audit_log` — только INSERT (триггер), `hash = sha256(prev_hash + canonical_json(запись))`,
  проверка: `GET /api/v1/audit/verify`.

## Спецификация

Роли и права, методика замера, данные и импорт, модель данных, API и экраны описаны
в спецификации: https://claude.ai/artifact/CUfFQXKPnijb1LwUbynJzj. Код приведён к ней
в ветке `spec-v1` (таблица расхождений П1–П3 в начале документа).

Обслуживание:

* `python -m app.cli anchor-audit` раз в сутки (cron) пишет последний hash журнала
  в S3 `audit-anchors/ГГГГ-ММ-ДД.json`. Подмена цепочки целиком видна по расхождению с якорем.
* Перед первой загрузкой CSV собственник даёт согласие на обработку данных
  (`POST /api/v1/consents`), без него импорт отвечает `409 consent_required`.
