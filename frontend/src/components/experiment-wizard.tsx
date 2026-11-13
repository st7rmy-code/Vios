"use client";

import { Check } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  ReferenceDot,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { Alert } from "@/components/ui/alert";
import { ConfirmDialog } from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input, Textarea } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Slider } from "@/components/ui/slider";
import { api, businessParam, errorText, type Experiment, type Schemas } from "@/lib/api/client";
import { addDays, date, num, percent, rubString, todayIso } from "@/lib/format";
import { stratumLabel } from "@/lib/labels";
import { MAX_MDE, MIN_GROUP, expectedSplit } from "@/lib/stats";
import { cn } from "@/lib/utils";

const STEPS = ["Идея", "Когорта", "Деление", "Проверка"];
const SHARES = [10, 15, 20, 25, 30, 35, 40, 45, 50];
const ppText = (x: number) => (x * 100).toFixed(1).replace(".", ",");
const tooltipStyle = { background: "hsl(var(--card))", border: "1px solid hsl(var(--border))", borderRadius: 8 };

function useDebounced<T>(value: T, ms: number): T {
  const [v, setV] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return v;
}

type P = {
  hypothesis: string;
  action: string;
  as_of: string;
  inactive_days: number;
  max_inactive_days: number;
  window_days: number;
  cost_rub: string;
  control_share: string;
};

export function ExperimentWizard({ initial }: { initial?: Experiment }) {
  const router = useRouter();
  const ip = initial?.protocol as Partial<P> | undefined;
  const [id, setId] = useState<string | null>(initial?.id ?? null);
  const [step, setStep] = useState(0);
  const [title, setTitle] = useState(initial?.title ?? "");
  const [hypothesis, setHypothesis] = useState(ip?.hypothesis ?? "");
  const [action, setAction] = useState(ip?.action ?? "");
  const [costRub, setCostRub] = useState(ip?.cost_rub ? String(Number(ip.cost_rub)) : "");
  const [asOf, setAsOf] = useState(ip?.as_of ?? todayIso());
  const [inactiveDays, setInactiveDays] = useState(ip?.inactive_days ?? 30);
  const [maxInactiveDays, setMaxInactiveDays] = useState(ip?.max_inactive_days ?? 180);
  const [windowDays, setWindowDays] = useState(ip?.window_days ?? 30);
  const [share, setShare] = useState(ip?.control_share ? Math.round(Number(ip.control_share) * 100) : 50);
  const [preview, setPreview] = useState<Schemas["PreviewOut"] | null>(null);
  const [mde, setMde] = useState<Schemas["MdeResponse"] | null>(null);
  const [curve, setCurve] = useState<{ share: number; mde: number | null }[]>([]);
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

  // Шаг 2: живой предпросмотр когорты с задержкой 400 мс.
  const cohortKey = useDebounced(JSON.stringify([asOf, inactiveDays, maxInactiveDays, windowDays]), 400);
  useEffect(() => {
    // Старый предпросмотр сразу убираем: цифры на экране всегда соответствуют текущим параметрам
    setPreview(null);
    setMde(null);
    setCurve([]);
    if (inactiveDays >= maxInactiveDays) return;
    let stale = false; // ответ на устаревший запрос (пришёл позже нового) отбрасываем
    api
      .POST("/api/v1/experiments/preview", {
        params: { query: businessParam() },
        body: { ...protocol, hypothesis: protocol.hypothesis || "—", action: protocol.action || "—", control_share: "0.5" },
      })
      .then(({ data }) => !stale && setPreview(data ?? null))
      .catch(() => !stale && setError("Не удалось посчитать когорту, проверьте соединение"));
    return () => {
      stale = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cohortKey]);

  // Шаг 3: MDE для текущей доли и кривая MDE по всем долям. Считает бэкенд тем же кодом, что и результат.
  const baseline = preview?.baseline_used ?? 0.05;
  const n = preview?.cohort_size ?? 0;
  useEffect(() => {
    if (!preview) return;
    let stale = false;
    Promise.all(
      SHARES.map((s) =>
        api.POST("/api/v1/stats/mde", { body: { baseline, ...expectedSplit(n, s / 100) } }).then(({ data }) => ({
          share: s,
          mde: data?.mde ?? null,
        })),
      ),
    )
      .then((c) => !stale && setCurve(c))
      .catch(() => undefined);
    return () => {
      stale = true;
    };
  }, [preview, baseline, n]);
  useEffect(() => {
    if (!preview) return;
    let stale = false;
    setMde(null);
    api
      .POST("/api/v1/stats/mde", { body: { baseline, ...expectedSplit(n, share / 100) } })
      .then(({ data }) => !stale && setMde(data ?? null))
      .catch(() => !stale && setError("Не удалось посчитать MDE, проверьте соединение"));
    return () => {
      stale = true;
    };
  }, [preview, baseline, n, share]);

  const tooSmall = mde != null && (mde.n_control < MIN_GROUP || mde.n_test < MIN_GROUP);
  const mdeTooBig = mde?.mde == null || mde.mde > MAX_MDE;
  const stepValid = [
    title.trim() && hypothesis.trim() && action.trim() && costRub !== "",
    inactiveDays < maxInactiveDays && (preview?.cohort_size ?? 0) > 0,
    mde != null, // дальше только с посчитанным MDE для текущей доли
    true,
  ];

  async function save(): Promise<string | null> {
    setBusy(true);
    setError(null);
    // сетевая ошибка не должна оставлять кнопки заблокированными
    const res = await (async () => {
      try {
        return id
          ? await api.PATCH("/api/v1/experiments/{exp_id}", { params: { path: { exp_id: id } }, body: { title, protocol } })
          : await api.POST("/api/v1/experiments", { body: { title, protocol, ...businessParam() } });
      } catch {
        return null;
      }
    })();
    setBusy(false);
    if (res === null) {
      setError("Сервер недоступен, попробуйте ещё раз");
      return null;
    }
    if (res.error || !res.data) {
      setError(errorText(res.error));
      return null;
    }
    if (!id) {
      setId(res.data.id);
      window.history.replaceState(null, "", `/experiments/${res.data.id}/edit`);
    }
    return res.data.id;
  }

  async function next() {
    if (await save()) setStep((s) => Math.min(s + 1, STEPS.length - 1));
  }

  async function register() {
    const eid = await save();
    if (!eid) return;
    setBusy(true);
    const res = await api
      .POST("/api/v1/experiments/{exp_id}/register", { params: { path: { exp_id: eid } } })
      .catch(() => null);
    setBusy(false);
    if (res === null) return setError("Сервер недоступен, попробуйте ещё раз");
    if (res.error) return setError(errorText(res.error));
    router.push(`/experiments/${eid}`);
  }

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">{initial ? "Черновик эксперимента" : "Новый эксперимент"}</h1>
        <p className="text-sm text-muted-foreground">Черновик сохраняется на каждом шаге. После регистрации протокол менять нельзя.</p>
      </div>

      <ol className="flex flex-wrap gap-2" aria-label="Шаги">
        {STEPS.map((s, i) => (
          <li key={s}>
            <button
              type="button"
              onClick={() => i < step && setStep(i)}
              disabled={i > step}
              className={cn(
                "flex items-center gap-2 rounded-full border px-3 py-1 text-sm",
                i === step ? "border-primary bg-primary text-primary-foreground" : i < step ? "hover:bg-accent" : "opacity-60",
              )}
            >
              {i < step ? <Check className="h-3.5 w-3.5" /> : <span className="tabular-nums">{i + 1}</span>}
              {s}
            </button>
          </li>
        ))}
      </ol>

      {step === 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Что проверяем</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <Field label="Название" id="title">
              <Input id="title" value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Звонок тренера ушедшим клиентам" />
            </Field>
            <Field label="Гипотеза" id="hyp">
              <Textarea id="hyp" value={hypothesis} onChange={(e) => setHypothesis(e.target.value)} placeholder="Личный звонок тренера возвращает часть ушедших клиентов" />
            </Field>
            <Field label="Действие с тестовой группой" id="act" hint="Это увидит исполнитель. Пишите так, чтобы было понятно, что делать.">
              <Textarea id="act" value={action} onChange={(e) => setAction(e.target.value)} placeholder="Тренер звонит и предлагает бесплатное пробное занятие" />
            </Field>
            <Field label="Стоимость действия C, ₽" id="cost" hint={`${rubString(costRub || 0)} на всю тестовую группу. Вычитается из прироста выручки.`}>
              <Input
                id="cost"
                inputMode="decimal"
                value={costRub}
                onChange={(e) => setCostRub(e.target.value.replace(/[^\d.,]/g, "").replace(",", "."))}
                placeholder="20000"
              />
            </Field>
          </CardContent>
        </Card>
      )}

      {step === 1 && (
        <div className="grid gap-6 lg:grid-cols-2">
          <Card>
            <CardHeader>
              <CardTitle>Кого берём</CardTitle>
              <CardDescription>Ушедшие клиенты: платили, сейчас без действующего абонемента и без визитов в заданном диапазоне.</CardDescription>
            </CardHeader>
            <CardContent className="grid gap-4 sm:grid-cols-2">
              <Field label="Дата среза" id="asof" hint="Не позже сегодня и не раньше чем за 7 дней до регистрации">
                <Input id="asof" type="date" value={asOf} onChange={(e) => setAsOf(e.target.value)} />
              </Field>
              <Field label="Окно замера, дней" id="win" hint={`Ждём возврата до ${date(addDays(asOf, windowDays))}`}>
                <Input id="win" type="number" min={7} max={180} value={windowDays} onChange={(e) => setWindowDays(+e.target.value)} />
              </Field>
              <Field label="Без активности от, дней" id="in">
                <Input id="in" type="number" min={7} value={inactiveDays} onChange={(e) => setInactiveDays(+e.target.value)} />
              </Field>
              <Field label="до, дней" id="max">
                <Input id="max" type="number" min={14} value={maxInactiveDays} onChange={(e) => setMaxInactiveDays(+e.target.value)} />
              </Field>
              {inactiveDays >= maxInactiveDays && (
                <Alert variant="warning" className="sm:col-span-2">
                  «От» должно быть меньше «до».
                </Alert>
              )}
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>Предпросмотр</CardTitle>
              <CardDescription>По загруженным данным, обновляется на лету.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <dl className="grid grid-cols-3 gap-3">
                <Metric label="Когорта" value={preview ? num(preview.cohort_size) : "…"} />
                <Metric label="Базовый возврат" value={preview?.baseline != null ? percent(preview.baseline) : "нет истории"} />
                <Metric label="В других экспериментах" value={preview ? num(preview.excluded_other_experiments) : "…"} />
              </dl>
              {preview && preview.strata.length > 0 && (
                <div className="h-56" aria-label="Клиенты по стратам">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={preview.strata} layout="vertical" margin={{ left: 0, right: 12 }}>
                      <CartesianGrid horizontal={false} strokeDasharray="3 3" stroke="hsl(var(--border))" />
                      <XAxis type="number" tickLine={false} axisLine={false} tick={{ fill: "hsl(var(--muted-foreground))", fontSize: 12 }} />
                      <YAxis
                        type="category"
                        dataKey="stratum"
                        width={150}
                        tickFormatter={stratumLabel}
                        tickLine={false}
                        axisLine={false}
                        tick={{ fill: "hsl(var(--muted-foreground))", fontSize: 11 }}
                      />
                      <Tooltip
                        formatter={(v: number) => [num(v), "клиентов"]}
                        labelFormatter={(l) => stratumLabel(String(l))}
                        contentStyle={tooltipStyle}
                      />
                      <Bar dataKey="n" fill="hsl(var(--primary))" radius={[0, 4, 4, 0]} maxBarSize={18} isAnimationActive={false} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              )}
              {preview?.cohort_size === 0 && <Alert variant="warning">По этим условиям клиентов нет. Проверьте загрузки и даты.</Alert>}
            </CardContent>
          </Card>
        </div>
      )}

      {step === 2 && (
        <Card>
          <CardHeader>
            <CardTitle>Доля контрольной группы</CardTitle>
            <CardDescription>
              Контрольной группе ничего не делаем. Чем она больше, тем точнее замер, но тем меньше клиентов получат действие.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-5">
            <div className="flex items-center gap-4">
              <Slider min={10} max={50} step={5} value={[share]} onValueChange={([v]) => setShare(v)} />
              <span className="w-14 text-right text-lg font-semibold tabular-nums">{share}%</span>
            </div>
            <dl className="grid grid-cols-3 gap-3">
              <Metric label="Когорта" value={num(n)} />
              <Metric label="Контроль" value={mde ? num(mde.n_control) : "…"} />
              <Metric label="Тест" value={mde ? num(mde.n_test) : "…"} />
            </dl>
            <div className="rounded-lg bg-muted p-4">
              <p className="text-sm text-muted-foreground">Минимальный эффект, который замер заметит (MDE)</p>
              <p className="text-3xl font-semibold tabular-nums">{mde?.mde != null ? `${ppText(mde.mde)} п.п.` : "—"}</p>
              {preview && preview.baseline == null && (
                <p className="mt-1 text-sm text-muted-foreground">
                  Истории возвратов нет, поэтому базовый возврат взят условно: {percent(baseline)}. Реальный MDE может
                  отличаться.
                </p>
              )}
              {mde?.mde != null && (
                <p className="mt-1">
                  Если действие вернёт на {ppText(mde.mde)} п.п. клиентов больше или сильнее, замер заметит это с
                  вероятностью 80% (при уровне значимости 5%). Меньший эффект может остаться незамеченным: MDE — порог
                  чувствительности, а не прогноз результата.
                </p>
              )}
            </div>
            {curve.length > 0 && (
              <div className="h-48" aria-label="MDE в зависимости от доли контроля">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={curve} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                    <XAxis dataKey="share" tickFormatter={(v) => `${v}%`} tickLine={false} axisLine={false} tick={{ fill: "hsl(var(--muted-foreground))", fontSize: 12 }} />
                    <YAxis
                      tickFormatter={(v) => `${ppText(v)}`}
                      width={44}
                      tickLine={false}
                      axisLine={false}
                      tick={{ fill: "hsl(var(--muted-foreground))", fontSize: 12 }}
                      label={{ value: "п.п.", position: "insideTopLeft", offset: 0, fill: "hsl(var(--muted-foreground))", fontSize: 11 }}
                    />
                    <Tooltip
                      formatter={(v: number) => [`${ppText(v)} п.п.`, "MDE"]}
                      labelFormatter={(l) => `Контроль ${l}%`}
                      contentStyle={tooltipStyle}
                    />
                    <Line type="monotone" dataKey="mde" stroke="hsl(var(--primary))" strokeWidth={2} dot={{ r: 2 }} connectNulls isAnimationActive={false} />
                    {mde?.mde != null && <ReferenceDot x={share} y={mde.mde} r={5} fill="hsl(var(--primary))" stroke="hsl(var(--background))" />}
                  </LineChart>
                </ResponsiveContainer>
              </div>
            )}
            {(tooSmall || mdeTooBig) && mde && (
              <Alert variant="warning">
                Результат будет «недостаточно данных»:{" "}
                {tooSmall ? `в группе меньше ${MIN_GROUP} клиентов.` : "MDE больше 10 п.п. Расширьте когорту или окно неактивности."}
              </Alert>
            )}
          </CardContent>
        </Card>
      )}

      {step === 3 && (
        <Card>
          <CardHeader>
            <CardTitle>Проверка протокола</CardTitle>
            <CardDescription>При регистрации клиенты делятся на группы, протокол и seed фиксируются в журнале.</CardDescription>
          </CardHeader>
          <CardContent>
            <dl className="grid gap-3 text-sm sm:grid-cols-[auto_1fr] sm:gap-x-6">
              <Row k="Название" v={title} />
              <Row k="Гипотеза" v={hypothesis} />
              <Row k="Действие" v={action} />
              <Row k="Стоимость C" v={rubString(costRub || 0)} />
              <Row k="Дата среза" v={date(asOf)} />
              <Row k="Когорта" v={`без активности ${inactiveDays}–${maxInactiveDays} дней, ${num(n)} клиентов`} />
              <Row k="Окно замера" v={`${windowDays} дней, до ${date(addDays(asOf, windowDays))}`} />
              <Row k="Группы" v={mde ? `контроль ${share}% (${num(mde.n_control)}), тест ${num(mde.n_test)}` : `контроль ${share}%`} />
              <Row k="MDE" v={mde?.mde != null ? `${ppText(mde.mde)} п.п.` : "—"} />
            </dl>
          </CardContent>
        </Card>
      )}

      {error && <Alert variant="destructive">{error}</Alert>}

      <div className="flex flex-wrap justify-between gap-2">
        <Button variant="outline" onClick={() => setStep((s) => s - 1)} disabled={step === 0 || busy}>
          Назад
        </Button>
        {step < STEPS.length - 1 ? (
          <Button onClick={next} disabled={busy || !stepValid[step]}>
            {busy ? "Сохраняем…" : "Сохранить и дальше"}
          </Button>
        ) : (
          <ConfirmDialog
            trigger={<Button disabled={busy}>Зарегистрировать</Button>}
            title="После регистрации протокол нельзя изменить"
            description={
              <>
                Клиенты будут разделены на тестовую и контрольную группы, протокол, seed и хэш назначений попадут в журнал. Изменить
                условия или переделить группы будет нельзя.
              </>
            }
            confirm="Зарегистрировать"
            onConfirm={register}
          />
        )}
      </div>
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

function Row({ k, v }: { k: string; v: string }) {
  return (
    <>
      <dt className="text-muted-foreground">{k}</dt>
      <dd className="break-words">{v}</dd>
    </>
  );
}
