"use client";

import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { Input, Textarea } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Slider } from "@/components/ui/slider";
import { api, errorText, type Schemas } from "@/lib/api/client";
import { num, percent, pp, rubString } from "@/lib/format";

const today = () => new Date().toISOString().slice(0, 10);
const MIN_GROUP = 100;
const MAX_MDE = 0.1;

function useDebounced<T>(value: T, ms: number): T {
  const [v, setV] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return v;
}

export default function NewExperimentPage() {
  const router = useRouter();
  const [title, setTitle] = useState("Звонок тренера ушедшим клиентам");
  const [hypothesis, setHypothesis] = useState("Личный звонок тренера возвращает часть ушедших клиентов");
  const [action, setAction] = useState("Тренер звонит и предлагает бесплатное пробное занятие");
  const [asOf, setAsOf] = useState(today());
  const [inactiveDays, setInactiveDays] = useState(30);
  const [maxInactiveDays, setMaxInactiveDays] = useState(180);
  const [windowDays, setWindowDays] = useState(30);
  const [costRub, setCostRub] = useState("20000");
  const [share, setShare] = useState(50); // %
  const [preview, setPreview] = useState<Schemas["PreviewOut"] | null>(null);
  const [mde, setMde] = useState<Schemas["MdeResponse"] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const protocol = useMemo(
    () => ({
      hypothesis,
      action,
      as_of: asOf,
      inactive_days: inactiveDays,
      max_inactive_days: maxInactiveDays,
      window_days: windowDays,
      control_share: (share / 100).toFixed(2),
      cost_rub: Number(costRub || 0).toFixed(2),
    }),
    [hypothesis, action, asOf, inactiveDays, maxInactiveDays, windowDays, share, costRub],
  );

  // Размер когорты и базовая доля возврата — с сервера, по реальным данным бизнеса.
  const cohortKey = useDebounced(JSON.stringify([asOf, inactiveDays, maxInactiveDays, windowDays]), 400);
  useEffect(() => {
    api.POST("/api/v1/experiments/preview", { body: { ...protocol, control_share: "0.5" } }).then(({ data }) =>
      setPreview(data ?? null),
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cohortKey]);

  // Живой MDE: пересчитываем при движении ползунка тем же кодом, что и в расчёте результата.
  const shareDeb = useDebounced(share, 120);
  useEffect(() => {
    if (!preview) return;
    api
      .POST("/api/v1/stats/mde", {
        body: {
          baseline: Math.min(Math.max(preview.baseline ?? 0.05, 0.01), 0.99),
          cohort_size: preview.cohort_size,
          control_share: shareDeb / 100,
        },
      })
      .then(({ data }) => setMde(data ?? null));
  }, [preview, shareDeb]);

  const tooSmall = mde != null && (mde.n_control < MIN_GROUP || mde.n_test < MIN_GROUP);
  const mdeTooBig = mde?.mde != null && mde.mde > MAX_MDE;

  async function create() {
    setBusy(true);
    setError(null);
    const { data, error } = await api.POST("/api/v1/experiments", { body: { title, protocol } });
    setBusy(false);
    if (error || !data) return setError(errorText(error));
    router.push(`/experiments/${data.id}`);
  }

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Новый эксперимент</h1>
        <p className="text-sm text-muted-foreground">
          Протокол сохраняется черновиком. После регистрации его нельзя изменить, а клиенты делятся на группы.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>1. Что проверяем</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <Field label="Название" id="title">
            <Input id="title" value={title} onChange={(e) => setTitle(e.target.value)} />
          </Field>
          <Field label="Гипотеза" id="hyp">
            <Textarea id="hyp" value={hypothesis} onChange={(e) => setHypothesis(e.target.value)} />
          </Field>
          <Field label="Действие с тестовой группой" id="act">
            <Textarea id="act" value={action} onChange={(e) => setAction(e.target.value)} />
          </Field>
          <Field label="Стоимость действия C, ₽" id="cost" hint={`Сейчас: ${rubString(costRub || 0)}. Вычитается из прироста выручки.`}>
            <Input id="cost" inputMode="decimal" value={costRub} onChange={(e) => setCostRub(e.target.value.replace(/[^\d.,]/g, "").replace(",", "."))} />
          </Field>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>2. Кого берём</CardTitle>
          <CardDescription>Ушедшие клиенты: нет действующего абонемента и не было активности в заданном диапазоне дней.</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-4 sm:grid-cols-2">
          <Field label="Дата среза" id="asof">
            <Input id="asof" type="date" value={asOf} onChange={(e) => setAsOf(e.target.value)} />
          </Field>
          <Field label="Окно замера, дней" id="win" hint="Сколько ждём возврата после среза">
            <Input id="win" type="number" min={7} max={180} value={windowDays} onChange={(e) => setWindowDays(+e.target.value)} />
          </Field>
          <Field label="Без активности от, дней" id="in">
            <Input id="in" type="number" min={7} value={inactiveDays} onChange={(e) => setInactiveDays(+e.target.value)} />
          </Field>
          <Field label="до, дней" id="max">
            <Input id="max" type="number" min={14} value={maxInactiveDays} onChange={(e) => setMaxInactiveDays(+e.target.value)} />
          </Field>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>3. Доля контрольной группы</CardTitle>
          <CardDescription>
            Контрольной группе ничего не делаем. Чем она больше, тем точнее замер, но тем меньше клиентов получат действие.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-5">
          <div className="flex items-center gap-4">
            <Slider min={10} max={50} step={1} value={[share]} onValueChange={([v]) => setShare(v)} />
            <span className="w-14 text-right text-lg font-semibold tabular-nums">{share}%</span>
          </div>
          <dl className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <Metric label="Когорта" value={preview ? num(preview.cohort_size) : "…"} />
            <Metric label="Контроль" value={mde ? num(mde.n_control) : "…"} />
            <Metric label="Тест" value={mde ? num(mde.n_test) : "…"} />
            <Metric label="Базовый возврат" value={preview?.baseline != null ? percent(preview.baseline) : "нет истории"} />
          </dl>
          <div className="rounded-lg bg-muted p-4">
            <p className="text-sm text-muted-foreground">Минимальный эффект, который замер заметит (MDE)</p>
            <p className="text-3xl font-semibold tabular-nums">{mde?.mde != null ? pp(mde.mde).replace("+", "") : "—"}</p>
            <p className="mt-1 text-sm text-muted-foreground">
              Если действие поднимет возврат меньше, чем на эту величину, замер, скорее всего, покажет «эффект не обнаружен».
            </p>
          </div>
          {preview?.cohort_size === 0 && <Alert variant="warning">По этим условиям клиентов нет. Проверьте загрузки и даты.</Alert>}
          {tooSmall && <Alert variant="warning">В одной из групп меньше {MIN_GROUP} клиентов: результат будет «недостаточно данных».</Alert>}
          {!tooSmall && mdeTooBig && (
            <Alert variant="warning">MDE больше 10 п.п.: результат будет «недостаточно данных». Расширьте когорту.</Alert>
          )}
        </CardContent>
        <CardFooter className="justify-end">
          {error && <Alert variant="destructive">{error}</Alert>}
          <Button onClick={create} disabled={busy || !title || !hypothesis || !action}>
            {busy ? "Сохраняем…" : "Сохранить черновик"}
          </Button>
        </CardFooter>
      </Card>
    </div>
  );
}

function Field({ label, id, hint, children }: { label: string; id: string; hint?: string; children: React.ReactNode }) {
  return (
    <div className="space-y-2">
      <Label htmlFor={id}>{label}</Label>
      {children}
      {hint && <p className="text-xs text-muted-foreground">{hint}</p>}
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border p-3">
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="mt-1 text-lg font-semibold tabular-nums">{value}</dd>
    </div>
  );
}
