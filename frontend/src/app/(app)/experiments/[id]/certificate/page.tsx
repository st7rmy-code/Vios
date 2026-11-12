"use client";

import { Printer } from "lucide-react";
import { useEffect, useState } from "react";

import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { api, errorText, type Schemas } from "@/lib/api/client";
import { date, dateTime, kopecksToRub, num, percent, pp, rubString } from "@/lib/format";
import { AUDIT_ACTION, RESULT_EXPLAIN, RESULT_VARIANT } from "@/lib/labels";
import type { ResultPayload } from "@/lib/result";
import { useExperiment } from "@/lib/use-experiment";

export default function CertificatePage() {
  const { id } = useExperiment();
  const [c, setC] = useState<Schemas["CertificateOut"] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.GET("/api/v1/experiments/{exp_id}/certificate", { params: { path: { exp_id: id } } }).then(({ data, error }) => {
      setC(data ?? null);
      if (error) setError(errorText(error));
    });
  }, [id]);

  if (error) return <Alert>{error}</Alert>;
  if (!c) return <p className="text-muted-foreground">Загрузка…</p>;
  const r = c.result as unknown as ResultPayload;
  const p = c.protocol as Record<string, string | number>;

  return (
    <div className="mx-auto max-w-3xl space-y-4">
      <div className="no-print flex justify-end">
        <Button variant="outline" onClick={() => window.print()}>
          <Printer className="h-4 w-4" /> Распечатать или сохранить PDF
        </Button>
      </div>

      <article className="space-y-6 rounded-lg border bg-card p-5 sm:p-10 print:border-0 print:p-0">
        <header className="space-y-2 border-b pb-5 text-center">
          <p className="text-xs uppercase tracking-widest text-muted-foreground">Сертификат замера</p>
          <h1 className="text-2xl font-semibold sm:text-3xl">{c.title}</h1>
          <p className="text-sm text-muted-foreground">
            Замер с {date(String(p.as_of))} по {date(addDays(String(p.as_of), Number(p.window_days)))}
          </p>
        </header>

        <section className="space-y-2 text-center">
          <Badge variant={RESULT_VARIANT[r.status]} className="px-3 py-1 text-sm">
            {r.status[0].toUpperCase() + r.status.slice(1)}
          </Badge>
          <p className="mx-auto max-w-xl text-sm text-muted-foreground">{RESULT_EXPLAIN[r.status]}</p>
        </section>

        <section className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <Big label="Возврат в контроле" value={percent(r.rate_control)} />
          <Big label="Возврат в тесте" value={percent(r.rate_test)} />
          <Big label="Прирост" value={pp(r.uplift)} sub={r.uplift_ci[0] != null ? `${pp(r.uplift_ci[0])} … ${pp(r.uplift_ci[1])}` : undefined} />
          <Big
            label="Чистый эффект"
            value={kopecksToRub(r.net_effect_kopecks)}
            sub={r.iterations ? `${kopecksToRub(r.net_effect_ci_kopecks[0])} … ${kopecksToRub(r.net_effect_ci_kopecks[1])}` : undefined}
          />
        </section>

        <section className="space-y-2 text-sm">
          <h2 className="font-semibold">Протокол</h2>
          <dl className="grid gap-x-6 gap-y-1 sm:grid-cols-[auto_1fr]">
            <dt className="text-muted-foreground">Гипотеза</dt>
            <dd>{String(p.hypothesis)}</dd>
            <dt className="text-muted-foreground">Действие</dt>
            <dd>{String(p.action)}</dd>
            <dt className="text-muted-foreground">Когорта</dt>
            <dd>
              ушедшие на {date(String(p.as_of))}, без активности {p.inactive_days}–{p.max_inactive_days} дней
            </dd>
            <dt className="text-muted-foreground">Группы</dt>
            <dd>
              тест {num(r.n_test)}, контроль {num(r.n_control)} (доля {Math.round(Number(p.control_share) * 100)}%)
            </dd>
            <dt className="text-muted-foreground">Окно замера</dt>
            <dd>{p.window_days} дней</dd>
            <dt className="text-muted-foreground">Стоимость действия</dt>
            <dd>{rubString(p.cost_rub)}</dd>
            <dt className="text-muted-foreground">Метод</dt>
            <dd>
              деление HMAC-SHA256 по seed внутри страт, расчёт по назначенным группам, бутстрэп {num(r.iterations)} повторов,
              95% интервал
            </dd>
          </dl>
        </section>

        <section className="space-y-2">
          <h2 className="text-sm font-semibold">Проверка подлинности</h2>
          <dl className="grid gap-x-6 gap-y-1 break-all font-mono text-xs sm:grid-cols-[auto_1fr]">
            <dt className="font-sans text-muted-foreground">Протокол</dt>
            <dd>{c.protocol_hash}</dd>
            <dt className="font-sans text-muted-foreground">Seed</dt>
            <dd>{c.seed}</dd>
            <dt className="font-sans text-muted-foreground">Результат</dt>
            <dd>{c.result_hash}</dd>
          </dl>
          <ol className="space-y-1 text-xs">
            {c.audit.map((a) => (
              <li key={a.seq} className="flex flex-col gap-0.5 border-t pt-1 sm:flex-row sm:gap-3">
                <span className="shrink-0 tabular-nums text-muted-foreground">
                  №{a.seq} · {dateTime(a.occurred_at)}
                </span>
                <span className="shrink-0">{AUDIT_ACTION[a.action] ?? a.action}</span>
                <span className="break-all font-mono text-muted-foreground">{a.hash}</span>
              </li>
            ))}
          </ol>
        </section>
      </article>
    </div>
  );
}

function addDays(iso: string, days: number) {
  const d = new Date(iso);
  d.setDate(d.getDate() + days);
  return d.toISOString();
}

function Big({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="rounded-md border p-3 text-center">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="mt-1 text-lg font-semibold tabular-nums sm:text-xl">{value}</p>
      {sub && <p className="text-[11px] tabular-nums text-muted-foreground">{sub}</p>}
    </div>
  );
}
