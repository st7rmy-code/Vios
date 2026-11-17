import type { BadgeProps } from "@/components/ui/badge";

export const EXPERIMENT_STATUS: Record<string, { label: string; variant: BadgeProps["variant"] }> = {
  draft: { label: "Черновик", variant: "secondary" },
  registered: { label: "Идёт замер", variant: "default" },
  closed: { label: "Закрыт", variant: "outline" },
};

/** Статусы результата по таблице 2.9 спецификации: код → цвет, подпись, вывод одной фразой. */
export const RESULT: Record<string, { label: string; variant: BadgeProps["variant"]; explain: string }> = {
  positive: {
    label: "Положительный эффект",
    variant: "success",
    explain: "Действие возвращает клиентов и окупается даже по нижней границе интервала.",
  },
  not_paying_off: {
    label: "Эффект есть, окупаемость не доказана",
    variant: "warning",
    explain: "Клиенты возвращаются чаще, но с учётом разброса действие может не окупить свою стоимость.",
  },
  negative: {
    label: "Отрицательный эффект",
    variant: "destructive",
    explain: "В тестовой группе возвращаются реже, чем без действия.",
  },
  not_detected: {
    label: "Эффект не обнаружен",
    variant: "secondary",
    explain: "Разницы между группами не видно. Если эффект есть, он, скорее всего, меньше MDE.",
  },
  insufficient: {
    label: "Недостаточно данных",
    variant: "secondary",
    explain: "Клиентов слишком мало, чтобы отличить эффект от случайности.",
  },
};

export const IMPORT_KIND: Record<string, string> = {
  customers: "Клиенты",
  payments: "Платежи",
  visits: "Посещения",
  obligations: "Обязательства",
};

export const AUDIT_ACTION: Record<string, string> = {
  "auth.login": "Вход",
  "auth.login_failed": "Неудачный вход",
  "business.created": "Создан бизнес",
  "user.created": "Добавлен пользователь",
  "user.deactivated": "Пользователь отключён",
  "consent.granted": "Дано согласие на обработку данных",
  "consent.revoked": "Согласие отозвано",
  "import.accepted": "Импорт принят",
  "import.rejected": "Импорт отклонён",
  "import.overwrote_payments": "Импорт перезаписал платежи",
  "experiment.created": "Создан эксперимент",
  "experiment.updated": "Изменён черновик",
  "experiment.deleted": "Черновик удалён",
  "experiment.registered": "Протокол зарегистрирован",
  "experiment.closed": "Эксперимент закрыт",
  "result.calculated": "Рассчитан результат",
  "assignments.exported": "Выгружен список группы",
};

export const ENTITY_TYPE: Record<string, string> = {
  experiment: "Эксперимент",
  import: "Импорт",
  user: "Пользователь",
  business: "Бизнес",
  consent: "Согласие",
};

const TENURE = ["стаж до 3 мес", "стаж 3–12 мес", "стаж от года"];
const PAID = ["оплат до 10 тыс.", "оплат 10–30 тыс.", "оплат от 30 тыс."];

/** «bЦентр-t1-p2» → «Центр · стаж 3–12 мес · оплат от 30 тыс.» */
export function stratumLabel(code: string): string {
  if (code === "small") return "малые страты";
  const parts = code.split("-");
  const out: string[] = [];
  for (const p of parts) {
    if (p.startsWith("b")) out.push(p.slice(1) || "без филиала");
    else if (/^t\d$/.test(p)) out.push(TENURE[+p[1]] ?? p);
    else if (/^p\d$/.test(p)) out.push(PAID[+p[1]] ?? p);
    else if (p === "small") out.push("малые страты");
  }
  return out.join(" · ") || code;
}
