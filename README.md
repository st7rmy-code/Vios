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
# 2 000 ушедших клиентов и закрытый эксперимент с результатом
docker compose exec backend python scripts/demo.py http://localhost:8000 admin <пароль>
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
* Деление на группы: HMAC-SHA256(seed, customer_id) внутри страт. Seed фиксируется
  при регистрации, протокол после регистрации менять нельзя (409).
* Доверительные интервалы: бутстрэп 5000 повторов с seed из seed эксперимента,
  повторный расчёт даёт те же числа и тот же хэш.
* `audit_log` — только INSERT (триггер), `hash = sha256(prev_hash + canonical_json(запись))`,
  проверка: `GET /api/v1/audit/verify`.

## Допущения до получения спецификации

Разделы «Роли и права», «Методика замера», «Данные и импорт», «Модель данных»,
«API бэкенда» ещё не получены. Всё, что ниже, сделано как рабочее допущение и
будет приведено к спецификации:

| Что | Допущение | Где |
|---|---|---|
| Когорта | нет действующего абонемента, без активности 30–180 дней, хотя бы одна оплата | `app/stats/cohort.py` |
| Страты | стаж (<3 мес, 3–12, >12) × сумма оплат (<10, 10–30, >30 тыс. ₽) | `app/stats/strata.py` |
| Исход | любая оплата в окне `window_days` после среза; выручка = сумма этих оплат | `app/services/experiments.py` |
| C | стоимость действия; чистый эффект = Δ средней выручки × n_test − C | `app/stats/estimate.py` |
| Статусы | недостаточно данных / положительный / эффект есть, окупаемость не доказана / отрицательный / не обнаружен | `app/stats/estimate.py` |
| «Недостаточно данных» | группа < 100 или MDE > 10 п.п. | `app/stats/estimate.py` |
| Роли | admin, owner (собственник), executor (исполнитель) | `app/models.py`, `app/api/experiments.py` |
| CSV | `customers`, `payments`, `visits`; `;`/`,`, UTF-8 или Windows-1251, даты ГГГГ-ММ-ДД или ДД.ММ.ГГГГ | `app/services/csv_import.py` |
