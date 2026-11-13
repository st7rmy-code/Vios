"use client";

import { Printer, ShieldCheck, ShieldX } from "lucide-react";
import { useEffect, useState } from "react";

import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { api, errorText, type Schemas } from "@/lib/api/client";
import { addDays, date, dateTime, kopecksToRub, num, percent, rubString } from "@/lib/format";
import { AUDIT_ACTION, RESULT } from "@/lib/labels";
import { moneyEffectLabel, upliftSentence, type ResultPayload } from "@/lib/result";
import { isManager, useSession } from "@/lib/session";
import { useExperiment } from "@/lib/use-experiment";

export default function CertificatePage() {
  const { id } = useExperiment();
  const { user } = useSession();
  const [c, setC] = useState<Schemas["CertificateOut"] | null>(null);
  const [chain, setChain] = useState<{ ok: boolean; at: string; checked: number; broken?: number | null } | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.GET("/api/v1/experiments/{exp_id}/certificate", { params: { path: { exp_id: id } } }).then(({ data, error }) => {
      setC(data ?? null);
      if (error) setError(errorText(error));
    });
  }, [id]);
  useEffect(() => {
    if (!isManager(user)) return; // проверка цепочки доступна собственнику и администратору
    api.GET("/api/v1/audit/verify").then(({ data }) => {
      if (data) setChain({ ok: data.ok, at: new Date().toISOString(), checked: data.checked, broken: data.broken_at_seq });
    });
  }, [user]);

  if (error) return <Alert>{error}</Alert>;
  if (!c) return <p className="text-muted-foreground">Загрузка…</p>;
  const r = c.result as unknown as ResultPayload;
  const p = c.protocol as Record<string, string | number>;
  const st = RESULT[r.status];

  return (
    <div className="mx-auto max-w-3xl space-y-4">
      <div className="no-print flex justify-end">
        <Button variant="outline" onClick={() => window.print()}>
          <Printer className="h-4 w-4" /> Распечатать или сохранить PDF
        </Button>
      </div>

      <article className="certificate space-y-6 rounded-lg border bg-card p-4 sm:p-10 print:rounded-none print:border-0 print:p-0">
        <header className="space-y-2 border-b pb-5 text-center">
          <p className="text-xs uppercase tracking-widest text-muted-foreground">Сертификат замера</p>
          <p className="text-sm font-medium">{c.business_name}</p>
          <h1 className="text-2xl font-semibold sm:text-3xl">{c.title}</h1>
          <p className="text-sm text-muted-foreground">
            Зарегистрирован {date(c.registered_at)}, закрыт {date(c.closed_at)}. Окно замера с {date(c.window_start ?? String(p.as_of))} по{" "}
            {date(c.window_end ?? addDays(String(p.as_of), Number(p.window_days)))}
            {c.data_complete_through && <>, выгрузка оплат полная по {date(c.data_complete_through)}</>}
          </p>
        </header>

        <section className="space-y-3 text-center">
          <Badge variant={st.variant} className="px-3 py-1 text-sm">
            {st.label}
          </Badge>
          <p className="mx-auto max-w-xl text-sm text-muted-foreground">{st.explain}</p>
          {r.status !== "insufficient" && (
            <div className="grid gap-3 sm:grid-cols-2">
              <Big label={`Возврат клиентов, ${Math.round((1 - r.alpha) * 100)}% интервал`} value={upliftSentence(r.uplift_ci)} />
              <Big
                label={moneyEffectLabel(r)}
                value={
                  r.net_effect_ci_kopecks
                    ? `от ${kopecksToRub(r.net_effect_ci_kopecks[0])} до ${kopecksToRub(r.net_effect_ci_kopecks[1])}`
                    : "—"
                }
              />
            </div>
          )}
        </section>

        <section className="space-y-2 text-sm">
          <h2 className="font-semibold">Протокол</h2>
          <dl className="grid gap-x-6 gap-y-1 sm:grid-cols-[auto_1fr]">
            <Dt>Гипотеза</Dt>
            <dd>{String(p.hypothesis)}</dd>
            <Dt>Действие</Dt>
            <dd>{String(p.action)}</dd>
            <Dt>Когорта</Dt>
            <dd>
              ушедшие на {date(String(p.as_of))}, без активности {p.inactive_days}–{p.max_inactive_days} дней
            </dd>
            <Dt>Группы</Dt>
            <dd className="tabular-nums">
              тест {num(r.n_test)}, контроль {num(r.n_control)} (доля контроля {Math.round(Number(p.control_share) * 100)}%)
            </dd>
            <Dt>Доля вернувшихся</Dt>
            <dd className="tabular-nums">
              тест {percent(r.rate_test)}, контроль {percent(r.rate_control)}
            </dd>
            {p.margin_pct != null && (
              <>
                <Dt>Маржа</Dt>
                <dd>{Number(p.margin_pct)}%: деньги в эффекте — валовая прибыль = выручка × маржа</dd>
              </>
            )}
            <Dt>Версия результата</Dt>
            <dd>
              {c.result_version ?? 1}
              {c.revisions && c.revisions.length > 0 && (
                <span className="block text-muted-foreground">
                  Позже пересчитан: {c.revisions.map((v) => `версия ${v.version} (${v.reason ?? "без причины"})`).join("; ")}.
                  Сертификат выдан по первой версии.
                </span>
              )}
            </dd>
            <Dt>Стоимость действия</Dt>
            <dd>{rubString(p.cost_rub)}</dd>
            <Dt>Метод</Dt>
            <dd>
              деление HMAC-SHA256 по seed внутри страт, расчёт по назначенным группам, бутстрэп {num(r.iterations)} повторов, {Math.round((1 - r.alpha) * 100)}%
              интервал
            </dd>
          </dl>
        </section>

        <section className="space-y-3">
          <h2 className="text-sm font-semibold">Как проверить</h2>
          <p className="text-xs text-muted-foreground">
            Повторный расчёт по тем же данным и seed даёт тот же хэш результата. Записи журнала связаны хэшами, подмену видно.
          </p>
          <dl className="grid gap-x-6 gap-y-1 break-all font-mono text-xs sm:grid-cols-[auto_1fr]">
            <dt className="font-sans text-muted-foreground">Хэш протокола</dt>
            <dd>{c.protocol_hash}</dd>
            <dt className="font-sans text-muted-foreground">Seed</dt>
            <dd>{c.seed}</dd>
            <dt className="font-sans text-muted-foreground">Хэш назначений</dt>
            <dd>{c.assignment_sha256 ?? "—"}</dd>
            <dt className="font-sans text-muted-foreground">Хэш результата</dt>
            <dd>{c.result_hash}</dd>
          </dl>
          <ol className="space-y-1 text-xs">
            {c.audit.map((a) => (
              <li key={a.seq} className="flex flex-col gap-0.5 border-t pt-1 sm:flex-row sm:gap-3">
                <span className="shrink-0 tabular-nums text-muted-foreground">
                  запись №{a.seq} · {dateTime(a.occurred_at)}
                </span>
                <span className="shrink-0">{AUDIT_ACTION[a.action] ?? a.action}</span>
                <span className="break-all font-mono text-muted-foreground">{a.hash.slice(0, 24)}…</span>
              </li>
            ))}
          </ol>
          {chain &&
            (chain.ok ? (
              <p className="flex items-center gap-2 text-sm text-success">
                <ShieldCheck className="h-4 w-4" /> Цепочка журнала цела на {dateTime(chain.at)}, проверено {num(chain.checked)} записей
              </p>
            ) : (
              <p className="flex items-center gap-2 text-sm text-destructive">
                <ShieldX className="h-4 w-4" /> Цепочка журнала нарушена на записи №{chain.broken}
              </p>
            ))}
        </section>
      </article>
    </div>
  );
}

function Dt({ children }: { children: React.ReactNode }) {
  return <dt className="text-muted-foreground">{children}</dt>;
}

function Big({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border p-3">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="mt-1 text-base font-semibold tabular-nums sm:text-lg">{value}</p>
    </div>
  );
}
