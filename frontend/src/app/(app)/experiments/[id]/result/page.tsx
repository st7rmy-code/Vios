"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import {
  CartesianGrid,
  ComposedChart,
  ErrorBar,
  ReferenceLine,
  ResponsiveContainer,
  Scatter,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { CopyValue } from "@/components/copy";
import { Accordion, AccordionItem } from "@/components/ui/accordion";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { api, errorText, type Schemas } from "@/lib/api/client";
import { dateTime, kopecksToRub, num, percent } from "@/lib/format";
import { RESULT, stratumLabel } from "@/lib/labels";
import { pp1, upliftSentence, type ResultPayload } from "@/lib/result";
import { neededPerGroup } from "@/lib/stats";
import { useExperiment } from "@/lib/use-experiment";

const axisTick = { fill: "hsl(var(--muted-foreground))", fontSize: 12 };
const tooltipStyle = { background: "hsl(var(--card))", border: "1px solid hsl(var(--border))", borderRadius: 8 };

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
  const st = RESULT[r.status];
  const insufficient = r.status === "insufficient";

  const rates = [
    { group: "Контроль", rate: r.rate_control, err: ci2err(r.rate_control, r.rate_control_ci), n: r.n_control },
    { group: "Тест", rate: r.rate_test, err: ci2err(r.rate_test, r.rate_test_ci), n: r.n_test },
  ];
  const uplift = [{ name: "Прирост", u: r.uplift, err: ci2err(r.uplift, r.uplift_ci) }];
  const uDomain: [number, number] = r.uplift_ci ? padDomain([r.uplift_ci[0], r.uplift_ci[1], 0, r.mde ?? 0]) : [-0.1, 0.1];

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
        <CardContent className="space-y-4 pt-4 sm:pt-6">
          <div className="space-y-2">
            <Badge variant={st.variant} className="px-3 py-1 text-sm">
              {st.label}
            </Badge>
            <p className="max-w-2xl text-lg">{st.explain}</p>
          </div>
          {!insufficient && (
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="rounded-lg bg-muted p-4">
                <p className="text-sm text-muted-foreground">Возврат клиентов, 95% интервал</p>
                <p className="text-xl font-semibold tabular-nums sm:text-2xl">{upliftSentence(r.uplift_ci)}</p>
              </div>
              <div className="rounded-lg bg-muted p-4">
                <p className="text-sm text-muted-foreground">Чистый эффект после стоимости действия</p>
                <p className="text-xl font-semibold tabular-nums sm:text-2xl">
                  {r.net_effect_ci_kopecks
                    ? `от ${kopecksToRub(r.net_effect_ci_kopecks[0])} до ${kopecksToRub(r.net_effect_ci_kopecks[1])}`
                    : "—"}
                </p>
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {insufficient ? (
        <Card>
          <CardHeader>
            <CardTitle>Почему результата нет</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            <p>
              В замере было {num(r.n_test)} клиентов в тесте и {num(r.n_control)} в контроле. При такой численности замер замечает
              только эффект от {r.mde != null ? pp1(r.mde) : "—"}, а для вывода нужно не больше 10 п.п. и не меньше 100 клиентов в
              каждой группе.
            </p>
            <p>
              Чтобы увидеть эффект в 5 п.п. при базовом возврате {percent(r.baseline_rate ?? 0.05)}, нужно примерно{" "}
              <strong>{num(neededPerGroup(r.baseline_rate ?? 0.05))}</strong> клиентов в каждой группе. Расширьте когорту (диапазон
              неактивности, несколько филиалов) или повторите замер позже.
            </p>
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-6 lg:grid-cols-2">
          <Card>
            <CardHeader>
              <CardTitle>Доля вернувшихся</CardTitle>
              <CardDescription>По назначенным группам, включая тех, до кого не дошло действие. Усы — 95% интервал.</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="h-60" role="img" aria-label={`Контроль ${percent(r.rate_control)}, тест ${percent(r.rate_test)}`}>
                <ResponsiveContainer width="100%" height="100%">
                  <ComposedChart data={rates} margin={{ top: 12, right: 16, left: 0, bottom: 0 }}>
                    <CartesianGrid vertical={false} strokeDasharray="3 3" stroke="hsl(var(--border))" />
                    <XAxis dataKey="group" type="category" allowDuplicatedCategory={false} tickLine={false} axisLine={false} tick={axisTick} />
                    <YAxis tickFormatter={(v) => percent(v)} width={56} tickLine={false} axisLine={false} tick={axisTick} domain={[0, "auto"]} />
                    <Tooltip
                      formatter={(v: number) => [percent(v), "Вернулись"]}
                      labelFormatter={(l, p) => `${l}: ${num(p?.[0]?.payload?.n)} клиентов`}
                      contentStyle={tooltipStyle}
                    />
                    <Scatter dataKey="rate" fill="hsl(var(--primary))" shape="circle" isAnimationActive={false}>
                      <ErrorBar dataKey="err" direction="y" width={10} strokeWidth={2} stroke="hsl(var(--primary))" />
                    </Scatter>
                  </ComposedChart>
                </ResponsiveContainer>
              </div>
              <dl className="mt-3 grid grid-cols-2 gap-3 text-sm">
                {rates.map((x) => (
                  <div key={x.group}>
                    <dt className="text-muted-foreground">{x.group}</dt>
                    <dd className="tabular-nums">
                      {percent(x.rate)} из {num(x.n)}
                    </dd>
                  </div>
                ))}
              </dl>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Прирост возврата</CardTitle>
              <CardDescription>Если интервал целиком выше нуля, эффект подтверждён. Пунктир — MDE, меньше него замер не различает.</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="h-60" role="img" aria-label={upliftSentence(r.uplift_ci)}>
                <ResponsiveContainer width="100%" height="100%">
                  <ComposedChart data={uplift} margin={{ top: 12, right: 16, left: 0, bottom: 0 }}>
                    <CartesianGrid vertical={false} strokeDasharray="3 3" stroke="hsl(var(--border))" />
                    <XAxis dataKey="name" type="category" tickLine={false} axisLine={false} tick={axisTick} />
                    <YAxis tickFormatter={(v) => pp1(v)} width={72} tickLine={false} axisLine={false} tick={axisTick} domain={uDomain} ticks={niceTicks(uDomain)} />
                    <Tooltip formatter={(v: number) => [pp1(v), "Прирост"]} contentStyle={tooltipStyle} />
                    <ReferenceLine y={0} stroke="hsl(var(--foreground))" strokeOpacity={0.6} />
                    {r.mde != null && (
                      <ReferenceLine
                        y={r.mde}
                        stroke="hsl(var(--muted-foreground))"
                        strokeDasharray="5 4"
                        label={{ value: `MDE ${pp1(r.mde)}`, position: "insideTopRight", fill: "hsl(var(--muted-foreground))", fontSize: 11 }}
                      />
                    )}
                    <Scatter dataKey="u" isAnimationActive={false} fill={r.uplift_ci && r.uplift_ci[0] > 0 ? "hsl(var(--success))" : "hsl(var(--primary))"}>
                      <ErrorBar dataKey="err" direction="y" width={10} strokeWidth={2} stroke="hsl(var(--foreground))" />
                    </Scatter>
                  </ComposedChart>
                </ResponsiveContainer>
              </div>
            </CardContent>
          </Card>
        </div>
      )}

      <Card>
        <CardContent className="pt-2 sm:pt-2">
          <Accordion type="multiple">
            <AccordionItem value="groups" title="Группы и деньги">
              <dl className="grid gap-2 sm:grid-cols-[auto_1fr] sm:gap-x-6">
                <Dt>Размер групп</Dt>
                <dd className="tabular-nums">
                  тест {num(r.n_test)}, контроль {num(r.n_control)}
                </dd>
                <Dt>Выручка в окне</Dt>
                <dd className="tabular-nums">
                  тест {kopecksToRub(r.revenue_test_kopecks)}, контроль {kopecksToRub(r.revenue_control_kopecks)}
                </dd>
                <Dt>Стоимость действия C</Dt>
                <dd className="tabular-nums">{kopecksToRub(r.cost_kopecks)}</dd>
                <Dt>Чистый эффект (точечно)</Dt>
                <dd className="tabular-nums">{kopecksToRub(r.net_effect_kopecks)}</dd>
                <Dt>MDE</Dt>
                <dd className="tabular-nums">{r.mde != null ? pp1(r.mde) : "—"}</dd>
                <Dt>Базовая доля возврата</Dt>
                <dd className="tabular-nums">{r.baseline_rate != null ? percent(r.baseline_rate) : "нет истории, взято 5%"}</dd>
              </dl>
            </AccordionItem>
            {r.by_stratum && (
              <AccordionItem value="strata" title="По стратам">
                <Table>
                  <THead>
                    <TR>
                      <TH>Страта</TH>
                      <TH className="text-right">Тест</TH>
                      <TH className="text-right">Контроль</TH>
                    </TR>
                  </THead>
                  <TBody>
                    {Object.entries(r.by_stratum).map(([s, g]) => (
                      <TR key={s}>
                        <TD>{stratumLabel(s)}</TD>
                        <TD className="text-right tabular-nums">
                          {percent(g.test?.rate)} из {num(g.test?.n)}
                        </TD>
                        <TD className="text-right tabular-nums">
                          {percent(g.control?.rate)} из {num(g.control?.n)}
                        </TD>
                      </TR>
                    ))}
                  </TBody>
                </Table>
              </AccordionItem>
            )}
            <AccordionItem value="method" title="Метод и проверка">
              <dl className="grid gap-2 sm:grid-cols-[auto_1fr] sm:gap-x-6">
                <Dt>Повторов бутстрэпа</Dt>
                <dd className="tabular-nums">{num(r.iterations)}</dd>
                <Dt>Уровень значимости</Dt>
                <dd className="tabular-nums">{percent(r.alpha)}</dd>
                <Dt>Хэш результата</Dt>
                <dd>
                  <CopyValue value={res.result_hash} />
                </dd>
                <Dt>Хэш протокола</Dt>
                <dd>
                  <CopyValue value={r.protocol_hash} />
                </dd>
              </dl>
            </AccordionItem>
          </Accordion>
        </CardContent>
      </Card>
    </div>
  );
}

function Dt({ children }: { children: React.ReactNode }) {
  return <dt className="text-muted-foreground">{children}</dt>;
}

function ci2err(point: number, ci: [number, number] | null): [number, number] {
  return ci ? [Math.max(point - ci[0], 0), Math.max(ci[1] - point, 0)] : [0, 0];
}

/** Границы оси прироста, кратные шагу: 1, 2 или 5 п.п. */
function padDomain(xs: number[]): [number, number] {
  const lo = Math.min(...xs);
  const hi = Math.max(...xs);
  const step = tickStep(hi - lo);
  return [Math.floor(lo / step) * step, Math.ceil(hi / step) * step];
}

function tickStep(span: number): number {
  return span <= 0.06 ? 0.01 : span <= 0.12 ? 0.02 : 0.05;
}

function niceTicks([lo, hi]: [number, number]): number[] {
  const step = tickStep(hi - lo);
  const out: number[] = [];
  for (let x = lo; x <= hi + 1e-9; x += step) out.push(Math.round(x * 1e4) / 1e4);
  return out;
}
