import type { BadgeProps } from "@/components/ui/badge";

export const EXPERIMENT_STATUS: Record<string, { label: string; variant: BadgeProps["variant"] }> = {
  draft: { label: "Черновик", variant: "secondary" },
  registered: { label: "Идёт замер", variant: "default" },
  closed: { label: "Закрыт", variant: "outline" },
};

/** Статусы результата приходят из бэкенда строкой на русском. */
export const RESULT_VARIANT: Record<string, BadgeProps["variant"]> = {
  "положительный эффект": "success",
  "эффект есть, окупаемость не доказана": "warning",
  "эффект не обнаружен": "secondary",
  "отрицательный эффект": "destructive",
  "недостаточно данных": "outline",
};

export const RESULT_EXPLAIN: Record<string, string> = {
  "положительный эффект":
    "Возвратов в тестовой группе больше, и даже по нижней границе интервала действие окупает свою стоимость.",
  "эффект есть, окупаемость не доказана":
    "Возвратов стало больше, но с учётом разброса нельзя утверждать, что действие окупило свою стоимость.",
  "эффект не обнаружен":
    "Разница между группами в пределах случайного разброса. Это не доказывает, что эффекта нет, но и подтвердить его нельзя.",
  "отрицательный эффект": "В тестовой группе возвратов меньше, чем в контрольной, и это выходит за пределы случайного разброса.",
  "недостаточно данных": "Клиентов слишком мало, чтобы отличить эффект от случайности. Нужна когорта больше или окно дольше.",
};

export const IMPORT_KIND: Record<string, string> = {
  customers: "Клиенты",
  payments: "Оплаты",
  visits: "Посещения",
};

export const AUDIT_ACTION: Record<string, string> = {
  "business.created": "Создан бизнес",
  "user.created": "Добавлен пользователь",
  "import.accepted": "Импорт принят",
  "import.rejected": "Импорт отклонён",
  "experiment.created": "Создан эксперимент",
  "experiment.updated": "Изменён черновик",
  "experiment.registered": "Протокол зарегистрирован",
  "experiment.closed": "Эксперимент закрыт",
  "experiment.calculated": "Рассчитан результат",
};
