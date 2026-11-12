"use client";

import { Download, Lock } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { api, errorText, type Schemas } from "@/lib/api/client";
import { date, dateTime, num, rubString } from "@/lib/format";
import { EXPERIMENT_STATUS } from "@/lib/labels";
import { isManager, useSession } from "@/lib/session";
import { useExperiment } from "@/lib/use-experiment";

type P = Record<string, string | number>;

export default function ExperimentCard() {
  const { user } = useSession();
  const manager = isManager(user);
  const router = useRouter();
  const { id, exp, setExp, notFound } = useExperiment();
  const [rows, setRows] = useState<Schemas["AssignmentOut"][]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!exp || exp.status === "draft") return;
    api
      .GET("/api/v1/experiments/{exp_id}/assignments", { params: { path: { exp_id: id }, query: { group: "test" } } })
      .then(({ data }) => setRows(data ?? []));
  }, [exp, id]);

  if (notFound) return <Alert>Эксперимент не найден.</Alert>;
  if (!exp) return <p className="text-muted-foreground">Загрузка…</p>;
  const p = exp.protocol as P;
  const st = EXPERIMENT_STATUS[exp.status];

  async function act(path: "register" | "close" | "calculate", confirmText?: string) {
    if (confirmText && !window.confirm(confirmText)) return;
    setBusy(true);
    setError(null);
    const url = `/api/v1/experiments/{exp_id}/${path}` as "/api/v1/experiments/{exp_id}/register";
    const { data, error } = await api.POST(url, { params: { path: { exp_id: id } } });
    setBusy(false);
    if (error) return setError(errorText(error));
    if (path === "calculate") return router.push(`/experiments/${id}/result`);
    if (data) setExp(data as typeof exp);
  }

  function downloadCsv() {
    const csv = "customer_id\n" + rows.map((r) => r.customer_id).join("\n");
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([csv], { type: "text/csv" }));
    a.download = `test-group-${id.slice(0, 8)}.csv`;
    a.click();
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="space-y-1">
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="text-2xl font-semibold">{exp.title}</h1>
            <Badge variant={st.variant}>{st.label}</Badge>
          </div>
          <p className="text-sm text-muted-foreground">
            {exp.registered_at ? `Зарегистрирован ${dateTime(exp.registered_at)}` : "Черновик, группы ещё не назначены"}
            {exp.closed_at && ` · закрыт ${dateTime(exp.closed_at)}`}
          </p>
        </div>
        {manager && (
          <div className="flex flex-wrap gap-2">
            {exp.status === "draft" && (
              <Button
                disabled={busy}
                onClick={() =>
                  act("register", "После регистрации протокол нельзя изменить, а клиенты будут разделены на группы. Продолжить?")
                }
              >
                Зарегистрировать
              </Button>
            )}
            {exp.status === "registered" && (
              <Button disabled={busy} variant="outline" onClick={() => act("close", "Закрыть эксперимент? Исполнители увидят контрольную группу.")}>
                Закрыть
              </Button>
            )}
            {exp.status === "closed" && (
              <>
                <Button disabled={busy} onClick={() => act("calculate")}>
                  Рассчитать результат
                </Button>
                <Button variant="outline" asChild>
                  <Link href={`/experiments/${id}/result`}>Результат</Link>
                </Button>
                <Button variant="outline" asChild>
                  <Link href={`/experiments/${id}/certificate`}>Сертификат</Link>
                </Button>
              </>
            )}
          </div>
        )}
      </div>
      {error && <Alert variant="destructive">{error}</Alert>}

      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              Протокол {exp.protocol_hash && <Lock className="h-4 w-4 text-muted-foreground" aria-label="зафиксирован" />}
            </CardTitle>
            {exp.protocol_hash && (
              <CardDescription className="break-all font-mono text-xs">sha256 {exp.protocol_hash}</CardDescription>
            )}
          </CardHeader>
          <CardContent>
            <dl className="grid gap-3 text-sm sm:grid-cols-[auto_1fr] sm:gap-x-6">
              <Row k="Гипотеза" v={String(p.hypothesis)} />
              <Row k="Действие" v={String(p.action)} />
              <Row k="Дата среза" v={date(String(p.as_of))} />
              <Row k="Когорта" v={`без активности ${p.inactive_days}–${p.max_inactive_days} дней`} />
              <Row k="Окно замера" v={`${p.window_days} дней`} />
              <Row k="Стоимость C" v={rubString(p.cost_rub)} />
              {p.control_share != null && <Row k="Доля контроля" v={`${Math.round(Number(p.control_share) * 100)}%`} />}
            </dl>
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
                  : "Работайте только с клиентами из этого списка."}
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {exp.n_test != null && (
              <dl className="grid grid-cols-2 gap-3">
                <div className="rounded-md border p-3">
                  <dt className="text-xs text-muted-foreground">Тест</dt>
                  <dd className="text-xl font-semibold tabular-nums">{num(exp.n_test)}</dd>
                </div>
                <div className="rounded-md border p-3">
                  <dt className="text-xs text-muted-foreground">Контроль</dt>
                  <dd className="text-xl font-semibold tabular-nums">
                    {exp.n_control != null ? num(exp.n_control) : <span className="text-sm font-normal text-muted-foreground">скрыт до закрытия</span>}
                  </dd>
                </div>
              </dl>
            )}
            {rows.length > 0 && (
              <>
                <div className="max-h-64 overflow-y-auto rounded-md border">
                  <ul className="divide-y text-sm">
                    {rows.slice(0, 500).map((r) => (
                      <li key={r.customer_id} className="flex justify-between px-3 py-1.5 font-mono">
                        {r.customer_id}
                      </li>
                    ))}
                  </ul>
                </div>
                <Button variant="outline" size="sm" onClick={downloadCsv}>
                  <Download className="h-4 w-4" /> Скачать тестовую группу (CSV)
                </Button>
              </>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

function Row({ k, v }: { k: string; v: string }) {
  return (
    <>
      <dt className="text-muted-foreground">{k}</dt>
      <dd>{v}</dd>
    </>
  );
}
