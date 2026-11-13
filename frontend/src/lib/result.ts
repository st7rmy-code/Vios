import { ppRange } from "@/lib/format";

/** Результат расчёта (app/stats/estimate.py → EffectResult.to_dict). Деньги в копейках. */
export type ResultPayload = {
  status: "positive" | "not_paying_off" | "negative" | "not_detected" | "insufficient";
  status_label: string;
  n_control: number;
  n_test: number;
  rate_control: number;
  rate_test: number;
  rate_control_ci: [number, number] | null;
  rate_test_ci: [number, number] | null;
  uplift: number;
  uplift_ci: [number, number] | null;
  mde: number | null;
  alpha: number;
  /** доля валовой маржи (0, 1]; 1 — эффект в выручке. В старых результатах поля нет */
  margin?: number;
  revenue_control_kopecks: number;
  revenue_test_kopecks: number;
  net_effect_kopecks: number;
  net_effect_ci_kopecks: [number, number] | null;
  cost_kopecks: number;
  iterations: number;
  bootstrap_seed: number;
  baseline_rate: number | null;
  protocol_hash: string;
  by_stratum?: Record<string, Record<"control" | "test", { n: number; rate: number }>> | null;
};

/** 0.042 → «4,2 п.п.», минус настоящий. */
export const pp1 = (x: number) => `${(x * 100).toFixed(1).replace(".", ",").replace("-", "−")} п.п.`;

/** «Возврат вырос на 3,1…8,9 п.п.» по интервалу прироста. */
export function upliftSentence(ci: [number, number] | null): string {
  if (!ci) return "Интервал не считался";
  const [lo, hi] = ci;
  if (lo > 0) return `Возврат вырос на ${ppRange(lo, hi)}`;
  if (hi < 0) return `Возврат снизился на ${ppRange(-hi, -lo)}`;
  return `Изменение возврата от ${pp1(lo)} до ${pp1(hi)}`;
}

/** Подпись денежного эффекта: при марже меньше 100% это валовая прибыль, а не выручка. */
export function moneyEffectLabel(r: { margin?: number }): string {
  return r.margin != null && r.margin < 1
    ? `Дополнительная валовая прибыль (маржа ${Math.round(r.margin * 100)}%) за вычетом стоимости действия`
    : "Дополнительная выручка за вычетом стоимости действия";
}
