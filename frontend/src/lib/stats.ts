/** Округление как в бэкенде (ROUND_HALF_EVEN), чтобы размеры групп в мастере совпали с регистрацией. */
export function roundHalfEven(x: number): number {
  const f = Math.floor(x);
  const d = x - f;
  if (Math.abs(d - 0.5) < 1e-9) return f % 2 === 0 ? f : f + 1;
  return Math.round(x);
}

export function expectedSplit(n: number, share: number): { n_control: number; n_test: number } {
  const n_control = roundHalfEven(n * share);
  return { n_control, n_test: n - n_control };
}

/**
 * Сколько клиентов нужно в каждой группе, чтобы MDE был не больше target (две доли, α=0.05, мощность 80%).
 * Оценка для подсказки на экране «недостаточно данных», не для расчёта результата.
 */
export function neededPerGroup(baseline: number, target = 0.05): number {
  const z = 1.959964 + 0.841621;
  const p1 = Math.min(Math.max(baseline, 0.01), 0.99);
  const p2 = Math.min(p1 + target, 0.99);
  return Math.ceil((z * z * (p1 * (1 - p1) + p2 * (1 - p2))) / (target * target));
}

export const MIN_GROUP = 100;
export const MAX_MDE = 0.1;
