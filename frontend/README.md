# frontend

Next.js 15 (App Router), TypeScript, Tailwind, компоненты в стиле shadcn/ui, Recharts.

```bash
npm install
npm run dev            # http://localhost:3000, запросы /api/v1/* проксируются на SVERKA_BACKEND_URL (по умолчанию :8000)
npm run gen:api        # перегенерировать типы клиента из ../backend/openapi.json
```

Экраны: вход → кабинет (загрузка CSV и отчёт о качестве) → мастер эксперимента
(ползунок доли контроля, живой MDE с бэкенда) → карточка → результат → сертификат
(печать в PDF) → журнал с проверкой цепочки.

Суммы приходят в копейках и форматируются только в `src/lib/format.ts`; фронтенд
ничего не считает, все числа результата берутся из API.
