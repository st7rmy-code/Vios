# frontend

Next.js 15 (App Router), TypeScript, Tailwind, компоненты в стиле shadcn/ui, Recharts.

```bash
npm install
npm run dev            # http://localhost:3000, /api/v1/* проксирует route handler на SVERKA_BACKEND_URL (по умолчанию :8000)
npm run gen:api        # перегенерировать типы клиента из ../backend/openapi.json
```

Экраны по разделу 6 спецификации: `/login`, `/` кабинет (данные, согласие, загрузка CSV,
отчёт о качестве, история), `/experiments`, мастер `/experiments/new` и `/experiments/[id]/edit`
(4 шага, живой предпросмотр когорты и MDE), карточка, результат, сертификат (печать A4),
`/audit` журнал, `/team`, `/admin/businesses`.

Вход: `POST /session` кладёт токен в httpOnly cookie `sverka_token`, прокси
`src/app/api/v1/[...path]/route.ts` добавляет его в заголовок Authorization. JavaScript
страницы токен не видит. Без cookie middleware отправляет на `/login?next=...`.
Шаблоны CSV лежат в `public/templates/`.

Суммы приходят в копейках и форматируются только в `src/lib/format.ts`; фронтенд
ничего не считает, все числа результата берутся из API.
