"use client";

import { Upload } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { QualityReport } from "@/components/quality-report";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { api, errorText, type Experiment, type ImportFile } from "@/lib/api/client";
import { dateTime, num } from "@/lib/format";
import { EXPERIMENT_STATUS, IMPORT_KIND } from "@/lib/labels";
import { isManager, useSession } from "@/lib/session";

type Kind = "customers" | "payments" | "visits";

export default function CabinetPage() {
  const { user } = useSession();
  const manager = isManager(user);
  const [imports, setImports] = useState<ImportFile[]>([]);
  const [experiments, setExperiments] = useState<Experiment[]>([]);
  const [selected, setSelected] = useState<ImportFile | null>(null);

  const load = useCallback(async () => {
    const [e, i] = await Promise.all([
      api.GET("/api/v1/experiments"),
      manager && user?.business_id ? api.GET("/api/v1/imports") : Promise.resolve({ data: [] as ImportFile[] }),
    ]);
    setExperiments(e.data ?? []);
    setImports(i.data ?? []);
  }, [manager, user?.business_id]);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">Кабинет</h1>
          <p className="text-sm text-muted-foreground">
            {manager ? "Загрузите выгрузки из CRM и запускайте замеры." : "Эксперименты, в которых вы работаете с клиентами."}
          </p>
        </div>
        {manager && (
          <Button asChild>
            <Link href="/experiments/new">Новый эксперимент</Link>
          </Button>
        )}
      </div>

      {manager && user?.business_id && (
        <div className="grid gap-6 lg:grid-cols-5">
          <UploadCard
            className="lg:col-span-2"
            onUploaded={(imp) => {
              setSelected(imp);
              load();
            }}
          />
          <Card className="lg:col-span-3">
            <CardHeader>
              <CardTitle>Отчёт о качестве</CardTitle>
              <CardDescription>Выберите загрузку в списке ниже или загрузите новый файл.</CardDescription>
            </CardHeader>
            <CardContent>
              {selected ? <QualityReport imp={selected} /> : <p className="text-sm text-muted-foreground">Пока ничего не выбрано.</p>}
            </CardContent>
          </Card>
        </div>
      )}

      {manager && !user?.business_id && (
        <Alert>Администратор платформы не привязан к бизнесу: загрузка данных доступна собственнику.</Alert>
      )}

      <Card>
        <CardHeader>
          <CardTitle>Эксперименты</CardTitle>
        </CardHeader>
        <CardContent>
          {experiments.length === 0 ? (
            <p className="text-sm text-muted-foreground">Экспериментов пока нет.</p>
          ) : (
            <ul className="divide-y">
              {experiments.map((e) => (
                <li key={e.id}>
                  <Link href={`/experiments/${e.id}`} className="flex flex-wrap items-center gap-x-3 gap-y-1 py-3 hover:underline">
                    <span className="font-medium">{e.title}</span>
                    <Badge variant={EXPERIMENT_STATUS[e.status].variant}>{EXPERIMENT_STATUS[e.status].label}</Badge>
                    {e.n_test != null && (
                      <span className="text-sm text-muted-foreground">
                        тест {num(e.n_test)}
                        {e.n_control != null && ` · контроль ${num(e.n_control)}`}
                      </span>
                    )}
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      {manager && imports.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Загрузки</CardTitle>
          </CardHeader>
          <CardContent>
            <Table>
              <THead>
                <TR>
                  <TH className="hidden sm:table-cell">Когда</TH>
                  <TH>Что</TH>
                  <TH className="hidden sm:table-cell">Файл</TH>
                  <TH>Строк</TH>
                  <TH>Статус</TH>
                </TR>
              </THead>
              <TBody>
                {imports.map((i) => (
                  <TR key={i.id} className="cursor-pointer" onClick={() => setSelected(i)}>
                    <TD className="hidden whitespace-nowrap sm:table-cell">{dateTime(i.created_at)}</TD>
                    <TD>{IMPORT_KIND[i.kind]}</TD>
                    <TD className="hidden max-w-48 truncate sm:table-cell">{i.filename}</TD>
                    <TD className="whitespace-nowrap tabular-nums">
                      {num((i.quality_report as { rows_valid?: number }).rows_valid)} /{" "}
                      {num((i.quality_report as { rows_total?: number }).rows_total)}
                    </TD>
                    <TD>
                      <Badge variant={i.status === "accepted" ? "success" : "destructive"}>
                        {i.status === "accepted" ? "принят" : "отклонён"}
                      </Badge>
                    </TD>
                  </TR>
                ))}
              </TBody>
            </Table>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

function UploadCard({ className, onUploaded }: { className?: string; onUploaded: (i: ImportFile) => void }) {
  const [kind, setKind] = useState<Kind>("customers");
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!file) return;
    setBusy(true);
    setError(null);
    const { data, error } = await api.POST("/api/v1/imports", {
      body: { kind, file: file as unknown as string },
      bodySerializer: (b) => {
        const fd = new FormData();
        fd.append("kind", b.kind);
        fd.append("file", file);
        return fd;
      },
    });
    setBusy(false);
    if (error || !data) return setError(errorText(error));
    setFile(null);
    (e.target as HTMLFormElement).reset();
    onUploaded(data);
  }

  return (
    <Card className={className}>
      <CardHeader>
        <CardTitle>Загрузка CSV</CardTitle>
        <CardDescription>
          Только идентификатор клиента, без ФИО, телефонов и email. Файл с ними будет отклонён.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={submit} className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="kind">Что загружаем</Label>
            <select
              id="kind"
              value={kind}
              onChange={(e) => setKind(e.target.value as Kind)}
              className="flex h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
            >
              <option value="customers">Клиенты: customer_id, first_paid_at, subscription_ends_at, branch</option>
              <option value="payments">Оплаты: payment_id, customer_id, paid_at, amount</option>
              <option value="visits">Посещения: customer_id, visited_at</option>
            </select>
          </div>
          <div className="space-y-2">
            <Label htmlFor="file">Файл</Label>
            <div className="flex min-w-0 items-center gap-3">
              <label
                htmlFor="file"
                className="shrink-0 cursor-pointer rounded-md bg-secondary px-3 py-2 text-sm font-medium hover:bg-secondary/80"
              >
                Выбрать файл
              </label>
              <span className="truncate text-sm text-muted-foreground">{file ? file.name : "файл не выбран"}</span>
              <input
                id="file"
                type="file"
                accept=".csv,text/csv"
                onChange={(e) => setFile(e.target.files?.[0] ?? null)}
                className="sr-only"
              />
            </div>
            <p className="text-xs text-muted-foreground">CSV через «;» или «,», UTF-8 или Windows-1251, даты ГГГГ-ММ-ДД или ДД.ММ.ГГГГ.</p>
          </div>
          {error && <Alert variant="destructive">{error}</Alert>}
          <Button type="submit" disabled={!file || busy} className="w-full sm:w-auto">
            <Upload className="h-4 w-4" />
            {busy ? "Проверяем…" : "Загрузить и проверить"}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}
