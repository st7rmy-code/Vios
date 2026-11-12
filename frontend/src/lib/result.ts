/** Поля payload результата расчёта (app/stats/estimate.py → EffectResult.to_dict). */
export type ResultPayload = {
  status: string;
  n_control: number;
  n_test: number;
  rate_control: number;
  rate_test: number;
  uplift: number;
  uplift_ci: [number | null, number | null];
  mde: number | null;
  net_effect_kopecks: number;
  net_effect_ci_kopecks: [number, number];
  cost_kopecks: number;
  iterations: number;
  bootstrap_seed: number;
  baseline_rate: number | null;
  protocol_hash: string;
};
