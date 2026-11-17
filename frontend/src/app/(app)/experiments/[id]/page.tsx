"use client";

import { Check, Download, Lock, Search } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { CopyValue } from "@/components/copy";
import { Alert } from "@/components/ui/alert";
import { ConfirmDialog } from "@/components/ui/alert-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { api, errorCode, errorText, type Experiment, type Schemas } from "@/lib/api/client";
import { addDays, date, dateTime, num, rubString, todayIso } from "@/lib/format";
import { EXPERIMENT_STATUS } from "@/lib/labels";
import { isManager, useSession } from "@/lib/session";
import { useExperiment } from "@/lib/use-experiment";
import { cn } from "@/lib/utils";

type P = Record<string, string | number | undefined>;

export default function ExperimentCard() {
  const { user } = useSession();
  const manager = isManager(user);
  const router = useRouter();
  const { id, exp, setExp, notFound } = useExperiment();
  const [hasResult, setHasResult] = useState(false);
  const [error, setError] = useState<{ text: string; code?: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [completeThrough, setCompleteThrough] = useState(todayIso());
  const [needReason, setNeedReason] = useState(false);
  const [reason, setReason] = useState("");

  useEffect(() => {
    if (exp?.status !== "closed") return;
    api.GET("/api/v1/experiments/{exp_id}/result", { params: { path: { exp_id: id } } }).then(({ data }) => setHasResult(!!data));
  }, [exp?.status, id]);

  if (notFound) return <Alert>Эксперимент не найден.</Alert>;
  if (!exp) return <p className="text-muted-foreground">Загрузка…</p>;
  const p = exp.protocol as P;
  const st = EXPERIMENT_STATUS[exp.status];
  // окно замера начинается в день регистрации; у черновика его ещё нет
  const windowEnd = exp.window_end ?? null;
  const closeFrom = windowEnd ? addDays(windowEnd, 1) : null;
  const windowOver = closeFrom != null && todayIso() >= closeFrom;
  const controlVisible = manager || exp.status === "closed";

  async function close() {
    setBusy(true);
    setError(null);
    const { data, error } = await api.POST("/api/v1/experiments/{exp_id}/close", {
      params: { path: { exp_id: id } },
      body: { data_complete_through: completeThrough },
    });
    setBusy(false);
    if (error) return setError({ text: errorText(error), code: errorCode(error) });
    if (data) setExp(data);
  }

  async function calculate() {
    setBusy(true);
    setError(null);
    const { error } = await api.POST("/api/v1/experiments/{exp_id}/calculate", {
      params: { path: { exp_id: id } },
      body: needReason ? { reason } : null,
    });
    setBusy(false);
    if (error) {
      // цифры изменились после исправления данных: новая версия только с причиной
      if (errorCode(error) === "reason_required") setNeedReason(true);
      return setError({ text: errorText(error), code: errorCode(error) });
    }
    router.push(`/experiments/${id}/result`);
  }

  async function remove() {
    const { error } = await api.DELETE("/api/v1/experiments/{exp_id}", { params: { path: { exp_id: id } } });
    if (error) return setError({ text: errorText(error) });
    router.push("/experiments");
  }

  return (
    <div className="space-y-6">
      <div className="space-y-3">
        <div className="flex flex-wrap items-center gap-2">
          <h1 className="text-2xl font-semibold">{exp.title}</h1>
          <Badge variant={st.variant}>{st.label}</Badge>
        </div>
        <Stages exp={exp} hasResult={hasResult} closeFrom={closeFrom} />
        {exp.status === "registered" && windowEnd && <Countdown end={windowEnd} />}
      </div>

      {!manager && exp.status !== "closed" && (
        <Card className="border-primary/40 bg-accent/30">
          <CardHeader>
            <CardDescription>Что делать с клиентами из списка</CardDescription>
            <CardTitle className="text-xl leading-snug">{String(p.action)}</CardTitle>
          </CardHeader>
          <CardContent className="text-sm text-muted-foreground">
            Только с клиентами из тестовой группы ниже. Остальным ничего не предлагайте, иначе замер будет неверным.
          </CardContent>
        </Card>
      )}

      {manager && (
        <div className="flex flex-wrap gap-2">
          {exp.status === "draft" && (
            <>
              <Button asChild>
                <Link href={`/experiments/${id}/edit`}>Продолжить в мастере</Link>
              </Button>
              <ConfirmDialog
                trigger={<Button variant="outline">Удалить черновик</Button>}
                title="Удалить черновик?"
                description="Черновик исчезнет из списка, запись об удалении останется в журнале."
                confirm="Удалить"
                onConfirm={remove}
              />
            </>
          )}
          {exp.status === "registered" && (
            <div className="space-y-1">
              <ConfirmDialog
                trigger={
                  <Button
                    disabled={busy || !windowOver}
                    title={windowOver || !closeFrom ? undefined : `Можно закрыть с ${date(closeFrom)}`}
                  >
                    Закрыть эксперимент
                  </Button>
                }
                title="Закрыть эксперимент?"
                description={
                  <div className="space-y-3">
                    <p>После закрытия исполнители увидят контрольную группу, а результат можно будет рассчитать.</p>
                    <p>
                      Подтвердите, что оплаты и возвраты выгружены полностью. Новые оплаты за окно замера после
                      закрытия не примутся.
                    </p>
                    <label className="block space-y-1">
                      <span className="font-medium text-foreground">Выгрузка полная по дату включительно</span>
                      <Input
                        type="date"
                        value={completeThrough}
                        min={windowEnd ?? undefined}
                        max={todayIso()}
                        onChange={(e) => setCompleteThrough(e.target.value)}
                      />
                    </label>
                  </div>
                }
                confirm="Подтверждаю и закрываю"
                onConfirm={close}
              />
              {!windowOver && closeFrom && (
                <p className="text-xs text-muted-foreground">Закрыть можно с {date(closeFrom)}, когда закончится окно замера.</p>
              )}
            </div>
          )}
          {exp.status === "closed" && (
            <div className="flex flex-wrap items-end gap-2">
              {needReason && (
                <label className="space-y-1 text-sm">
                  <span className="text-muted-foreground">Причина пересчёта (сохранится в журнале)</span>
                  <Input value={reason} onChange={(e) => setReason(e.target.value)} className="w-80" />
                </label>
              )}
              <Button
                disabled={busy || (needReason && reason.trim().length < 3)}
                variant={hasResult ? "outline" : "default"}
                onClick={calculate}
              >
                {needReason ? "Сохранить новую версию" : hasResult ? "Пересчитать результат" : "Рассчитать результат"}
              </Button>
            </div>
          )}
        </div>
      )}
      {exp.status === "closed" && hasResult && (
        <div className="flex flex-wrap gap-2">
          <Button asChild>
            <Link href={`/experiments/${id}/result`}>Открыть результат</Link>
          </Button>
          <Button variant="outline" asChild>
            <Link href={`/experiments/${id}/certificate`}>Сертификат</Link>
          </Button>
        </div>
      )}
      {error && (
        <Alert variant="destructive" className="space-y-1">
          <p>{error.text}</p>
          {error.code === "payments_not_covering_window" && (
            <Link href="/" className="font-medium underline">
              Загрузить платежи
            </Link>
          )}
        </Alert>
      )}

      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              Протокол {exp.protocol_hash && <Lock className="h-4 w-4 text-muted-foreground" aria-label="зафиксирован" />}
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <dl className="grid gap-3 text-sm sm:grid-cols-[auto_1fr] sm:gap-x-6">
              <Row k="Гипотеза" v={String(p.hypothesis)} />
              {manager && <Row k="Действие" v={String(p.action)} />}
              <Row k="Дата среза" v={date(String(p.as_of))} />
              <Row k="Когорта" v={`без активности ${p.inactive_days}–${p.max_inactive_days} дней`} />
              <Row
                k="Окно замера"
                v={
                  exp.window_start && windowEnd
                    ? `${p.window_days} дней: ${date(exp.window_start)} – ${date(windowEnd)}`
                    : `${p.window_days} дней с даты регистрации`
                }
              />
              {p.cost_rub != null && <Row k="Стоимость C" v={rubString(p.cost_rub)} />}
              {p.margin_pct != null && <Row k="Маржа" v={`${Number(p.margin_pct)}%`} />}
              {exp.data_complete_through && <Row k="Выгрузка полная по" v={date(exp.data_complete_through)} />}
              {exp.control_share != null && <Row k="Доля контроля" v={`${Math.round(Number(exp.control_share) * 100)}%`} />}
              {exp.n_test != null && (
                <Row k="Группы" v={`тест ${num(exp.n_test)}${exp.n_control != null ? `, контроль ${num(exp.n_control)}` : ""}`} />
              )}
            </dl>
            {exp.protocol_hash && (
              <dl className="grid gap-2 border-t pt-3 text-sm sm:grid-cols-[auto_1fr] sm:gap-x-6">
                <dt className="text-muted-foreground">Хэш протокола</dt>
                <dd>
                  <CopyValue value={exp.protocol_hash} />
                </dd>
                <dt className="text-muted-foreground">Seed</dt>
                <dd>
                  <CopyValue value={exp.seed} />
                </dd>
              </dl>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Группы</CardTitle>
            <CardDescription>
              {exp.status === "draft"
                ? "Появятся после регистрации."
                : manager
                  ? "Действие применяется только к тестовой группе."
                  : "Работайте только с клиентами из тестовой группы."}
            </CardDescription>
          </CardHeader>
          {exp.status !== "draft" && (
            <CardContent>
              <Tabs defaultValue="test">
                <TabsList>
                  <TabsTrigger value="test">Тестовая группа</TabsTrigger>
                  {controlVisible && <TabsTrigger value="control">Контрольная группа</TabsTrigger>}
                </TabsList>
                <TabsContent value="test">
                  <GroupList expId={id} group="test" />
                </TabsContent>
                {controlVisible && (
                  <TabsContent value="control">
                    <GroupList expId={id} group="control" />
                  </TabsContent>
                )}
              </Tabs>
            </CardContent>
          )}
        </Card>
      </div>
    </div>
  );
}

function Stages({ exp, hasResult, closeFrom }: { exp: Experiment; hasResult: boolean; closeFrom: string | null }) {
  const steps = [
    { label: "Черновик", done: true, when: null as string | null },
    { label: "Зарегистрирован", done: !!exp.registered_at, when: exp.registered_at ? dateTime(exp.registered_at) : null },
    {
      label: "Закрыт",
      done: !!exp.closed_at,
      when: exp.closed_at ? dateTime(exp.closed_at) : exp.registered_at && closeFrom ? `не раньше ${date(closeFrom)}` : null,
    },
    { label: "Результат", done: hasResult, when: null },
  ];
  return (
    <ol className="flex flex-wrap items-center gap-x-2 gap-y-2 text-sm" aria-label="Этапы">
      {steps.map((s, i) => (
        <li key={s.label} className="flex items-center gap-2">
          {i > 0 && <span className="h-px w-4 bg-border" aria-hidden />}
          <span
            className={cn(
              "flex h-5 w-5 items-center justify-center rounded-full border text-[10px]",
              s.done ? "border-primary bg-primary text-primary-foreground" : "text-muted-foreground",
            )}
          >
            {s.done ? <Check className="h-3 w-3" /> : i + 1}
          </span>
          <span className={s.done ? "" : "text-muted-foreground"}>
            {s.label}
            {s.when && <span className="ml-1 text-xs text-muted-foreground">{s.when}</span>}
          </span>
        </li>
      ))}
    </ol>
  );
}

function Countdown({ end }: { end: string }) {
  const days = Math.ceil((new Date(`${end}T00:00:00`).getTime() - Date.now()) / 86_400_000);
  return (
    <p className="text-sm">
      {days > 0 ? (
        <>
          До конца окна замера <strong className="tabular-nums">{days}</strong> {plural(days, "день", "дня", "дней")} ({date(end)})
        </>
      ) : (
        <>Окно замера закончилось {date(end)}. Загрузите свежие платежи и закройте эксперимент.</>
      )}
    </p>
  );
}

function GroupList({ expId, group }: { expId: string; group: "test" | "control" }) {
  const [rows, setRows] = useState<Schemas["AssignmentOut"][] | null>(null);
  const [q, setQ] = useState("");
  useEffect(() => {
    api
      .GET("/api/v1/experiments/{exp_id}/assignments", { params: { path: { exp_id: expId }, query: { group } } })
      .then(({ data }) => setRows(data ?? []));
  }, [expId, group]);
  const shown = useMemo(() => (rows ?? []).filter((r) => r.customer_id.toLowerCase().includes(q.trim().toLowerCase())), [rows, q]);
  if (rows === null) return <p className="text-sm text-muted-foreground">Загрузка…</p>;
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <div className="relative min-w-0 flex-1">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input className="pl-9" placeholder="Найти ID клиента" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Поиск по ID" />
        </div>
        <Button variant="outline" asChild>
          <a href={`/api/v1/experiments/${expId}/assignments.csv?group=${group}`} download>
            <Download className="h-4 w-4" /> Выгрузить CSV
          </a>
        </Button>
      </div>
      <p className="text-xs text-muted-foreground">
        {q ? `Найдено ${num(shown.length)} из ${num(rows.length)}` : `${num(rows.length)} клиентов`}
      </p>
      <div className="max-h-80 overflow-y-auto rounded-md border">
        <ul className="divide-y text-sm">
          {shown.slice(0, 1000).map((r) => (
            <li key={r.customer_id} className="px-3 py-2 font-mono">
              {r.customer_id}
            </li>
          ))}
        </ul>
      </div>
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

function plural(n: number, one: string, few: string, many: string) {
  const m10 = n % 10;
  const m100 = n % 100;
  if (m10 === 1 && m100 !== 11) return one;
  if (m10 >= 2 && m10 <= 4 && (m100 < 12 || m100 > 14)) return few;
  return many;
}
