"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Bar, BarChart, CartesianGrid, LabelList, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { Interval } from "@/components/interval";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { api, errorText, type Schemas } from "@/lib/api/client";
import { dateTime, kopecksToRub, num, percent, pp } from "@/lib/format";
import { RESULT_EXPLAIN, RESULT_VARIANT } from "@/lib/labels";
import type { ResultPayload } from "@/lib/result";
import { useExperiment } from "@/lib/use-experiment";

export default function ResultPage() {
  const { id, exp } = useExperiment();
  const [res, setRes] = useState<Schemas["ResultOut"] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.GET("/api/v1/experiments/{exp_id}/result", { params: { path: { exp_id: id } } }).then(({ data, error }) => {
      setRes(data ?? null);
      if (error) setError(errorText(error));
    });
  }, [id]);

  if (error) return <Alert>{error}</Alert>;
  if (!res || !exp) return <p className="text-muted-foreground">Загрузка…</p>;
  const r = res.payload as unknown as ResultPayload;
  const chart = [
    { group: "Контроль", rate: r.rate_control, n: r.n_control },
    { group: "Тест", rate: r.rate_test, n: r.n_test },
  ];

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-sm text-muted-foreground">
            <Link href={`/experiments/${id}`} className="hover:underline">
              {exp.title}
            </Link>
          </p>
          <h1 className="text-2xl font-semibold">Результат</h1>
          <p className="text-sm text-muted-foreground">Рассчитан {dateTime(res.computed_at)}</p>
        </div>
        <Button variant="outline" asChild>
          <Link href={`/experiments/${id}/certificate`}>Сертификат</Link>
        </Button>
      </div>

      <Card>
        <CardContent className="space-y-3 pt-4 sm:pt-6">
          <Badge variant={RESULT_VARIANT[r.status]} className="px-3 py-1 text-sm">
            {r.status[0].toUpperCase() + r.status.slice(1)}
          </Badge>
          <p className="max-w-2xl">{RESULT_EXPLAIN[r.status]}</p>
        </CardContent>
      </Card>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Доля вернувшихся</CardTitle>
            <CardDescription>По назначенным группам, включая тех, до кого не дозвонились.</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="h-56">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={chart} margin={{ top: 24, right: 8, left: 0, bottom: 0 }}>
                  <CartesianGrid vertical={false} strokeDasharray="3 3" stroke="hsl(var(--border))" />
                  <XAxis dataKey="group" tickLine={false} axisLine={false} tick={{ fill: "hsl(var(--muted-foreground))" }} />
                  <YAxis tickFormatter={(v) => percent(v)} width={56} tickLine={false} axisLine={false} tick={{ fill: "hsl(var(--muted-foreground))", fontSize: 12 }} />
                  <Tooltip
                    formatter={(v: number) => percent(v)}
                    labelFormatter={(l, p) => `${l}: ${num(p?.[0]?.payload?.n)} клиентов`}
                    contentStyle={{ background: "hsl(var(--card))", border: "1px solid hsl(var(--border))", borderRadius: 8 }}
                  />
                  <Bar dataKey="rate" name="Вернулись" fill="hsl(var(--primary))" radius={[6, 6, 0, 0]} maxBarSize={96}>
                    <LabelList dataKey="rate" position="top" formatter={(v: unknown) => percent(v as number)} className="fill-foreground text-sm" />
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
            <dl className="mt-4 grid grid-cols-2 gap-3 text-sm">
              <div>
                <dt className="text-muted-foreground">Контроль</dt>
                <dd className="tabular-nums">{num(r.n_control)} клиентов</dd>
              </div>
              <div>
                <dt className="text-muted-foreground">Тест</dt>
                <dd className="tabular-nums">{num(r.n_test)} клиентов</dd>
              </div>
            </dl>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Эффект с 95% интервалом</CardTitle>
            <CardDescription>Бутстрэп {num(r.iterations)} повторов. Если интервал целиком правее нуля, эффект подтверждён.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-6">
            <div className="space-y-2">
              <div className="flex items-baseline justify-between gap-2">
                <span className="text-sm text-muted-foreground">Прирост возврата</span>
                <span className="text-xl font-semibold tabular-nums">{pp(r.uplift)}</span>
              </div>
              <Interval lo={r.uplift_ci[0]} hi={r.uplift_ci[1]} point={r.uplift} format={pp} />
            </div>
            <div className="space-y-2">
              <div className="flex items-baseline justify-between gap-2">
                <span className="text-sm text-muted-foreground">Чистый эффект в деньгах</span>
                <span className="text-xl font-semibold tabular-nums">{kopecksToRub(r.net_effect_kopecks)}</span>
              </div>
              <Interval
                lo={r.iterations ? r.net_effect_ci_kopecks[0] : null}
                hi={r.iterations ? r.net_effect_ci_kopecks[1] : null}
                point={r.net_effect_kopecks}
                format={kopecksToRub}
              />
              <p className="text-xs text-muted-foreground">
                Прирост выручки тестовой группы минус стоимость действия {kopecksToRub(r.cost_kopecks)}.
              </p>
            </div>
            <p className="text-sm text-muted-foreground">
              Минимальный обнаружимый эффект при таком размере групп: {r.mde != null ? pp(r.mde).replace("+", "") : "—"}
            </p>
          </CardContent>
        </Card>
      </div>
      <p className="break-all font-mono text-xs text-muted-foreground">sha256 результата {res.result_hash}</p>
    </div>
  );
}
