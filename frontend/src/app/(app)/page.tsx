"use client";

import { FileDown, Upload } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import { QualityReport } from "@/components/quality-report";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Sheet } from "@/components/ui/sheet";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { api, businessParam, errorText, type Experiment, type ImportFile, type Schemas } from "@/lib/api/client";
import { date, dateTime, num, percent } from "@/lib/format";
import { EXPERIMENT_STATUS, IMPORT_KIND } from "@/lib/labels";
import { isManager, useSession } from "@/lib/session";

type Kind = "customers" | "payments" | "visits" | "obligations";
const KINDS: Kind[] = ["customers", "payments", "visits", "obligations"];
const CONSENT_VERSION = "csv-2026-11";

export default function CabinetPage() {
  const { user, businessId } = useSession();
  const router = useRouter();
  const manager = isManager(user);
  const [summary, setSummary] = useState<Schemas["DataSummary"] | null>(null);
  const [imports, setImports] = useState<ImportFile[]>([]);
  const [experiments, setExperiments] = useState<Experiment[]>([]);
  const [consent, setConsent] = useState<Schemas["ConsentOut"] | null | undefined>(undefined);
  const [lastUpload, setLastUpload] = useState<ImportFile | null>(null);
  const [opened, setOpened] = useState<ImportFile | null>(null);

  useEffect(() => {
    if (user && !manager) router.replace("/experiments");
  }, [user, manager, router]);

  const load = useCallback(async () => {
    if (!businessId) return;
    const [s, i, e, c] = await Promise.all([
      api.GET("/api/v1/data/summary"),
      api.GET("/api/v1/imports"),
      api.GET("/api/v1/experiments"),
      api.GET("/api/v1/consents"),
    ]);
    setSummary(s.data ?? null);
    setImports(i.data ?? []);
    setExperiments(e.data ?? []);
    setConsent((c.data ?? []).find((x) => x.kind === "csv_upload" && !x.revoked_at) ?? null);
  }, [businessId]);

  useEffect(() => {
    load();
  }, [load]);

  if (!manager) return null;
  if (!businessId)
    return (
      <Alert>
        Бизнесов пока нет. Создайте первый в разделе <Link href="/admin/businesses" className="underline">«Бизнесы»</Link>.
      </Alert>
    );

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">Кабинет</h1>
          <p className="text-sm text-muted-foreground">Загрузите выгрузки из CRM и кассы, затем запускайте замеры.</p>
        </div>
        <Button asChild>
          <Link href="/experiments/new">Новый эксперимент</Link>
        </Button>
      </div>

      <section className="grid grid-cols-2 gap-3 lg:grid-cols-4" aria-label="Данные">
        {KINDS.map((k) => {
          const d = summary?.[k];
          return (
            <Card key={k}>
              <CardContent className="space-y-1 pt-4 sm:pt-5">
                <p className="text-sm text-muted-foreground">{IMPORT_KIND[k]}</p>
                <p className="text-2xl font-semibold tabular-nums">{d ? num(d.rows) : "…"}</p>
                <p className="text-xs text-muted-foreground">
                  {d?.date_min ? `${date(d.date_min)} — ${date(d.date_max)}` : "нет дат"}
                </p>
                <p className="text-xs text-muted-foreground">
                  {d?.last_import_at ? `загружено ${dateTime(d.last_import_at)}` : "ещё не загружали"}
                </p>
              </CardContent>
            </Card>
          );
        })}
      </section>

      <div className="grid gap-6 lg:grid-cols-5">
        <div className="lg:col-span-2">
          {consent === undefined ? null : consent ? (
            <UploadCard
              onUploaded={(imp) => {
                setLastUpload(imp);
                load();
              }}
            />
          ) : (
            <ConsentCard canGrant={user?.role === "owner"} onGranted={load} />
          )}
        </div>
        <Card className="lg:col-span-3">
          <CardHeader>
            <CardTitle>Отчёт о качестве</CardTitle>
            <CardDescription>Появляется сразу после загрузки. Старые отчёты открываются из истории ниже.</CardDescription>
          </CardHeader>
          <CardContent>
            {lastUpload ? (
              <QualityReport imp={lastUpload} />
            ) : (
              <p className="text-sm text-muted-foreground">Загрузите файл, и здесь будет разбор: что принято, что нет и почему.</p>
            )}
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>История импортов</CardTitle>
        </CardHeader>
        <CardContent>
          {imports.length === 0 ? (
            <p className="text-sm text-muted-foreground">Загрузок пока не было.</p>
          ) : (
            <Table>
              <THead>
                <TR>
                  <TH>Дата</TH>
                  <TH>Вид</TH>
                  <TH className="hidden sm:table-cell">Файл</TH>
                  <TH>Статус</TH>
                  <TH className="text-right">Корректных</TH>
                </TR>
              </THead>
              <TBody>
                {imports.map((i) => {
                  const r = i.quality_report as { valid_share?: number; rows_invalid?: number; warnings?: string[] };
                  return (
                    <TR key={i.id} className="cursor-pointer" onClick={() => setOpened(i)}>
                      <TD className="whitespace-nowrap">{dateTime(i.created_at)}</TD>
                      <TD>{IMPORT_KIND[i.kind]}</TD>
                      <TD className="hidden max-w-[16rem] truncate sm:table-cell">{i.filename}</TD>
                      <TD>
                        {i.status === "rejected" ? (
                          <Badge variant="destructive">отклонён</Badge>
                        ) : r.rows_invalid || r.warnings?.length ? (
                          <Badge variant="warning">с предупреждением</Badge>
                        ) : (
                          <Badge variant="success">принят</Badge>
                        )}
                      </TD>
                      <TD className="text-right tabular-nums">{percent(r.valid_share)}</TD>
                    </TR>
                  );
                })}
              </TBody>
            </Table>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex-row flex-wrap items-center justify-between gap-2">
          <CardTitle>Эксперименты</CardTitle>
          <Button variant="outline" size="sm" asChild>
            <Link href="/experiments">Все</Link>
          </Button>
        </CardHeader>
        <CardContent>
          {experiments.length === 0 ? (
            <p className="text-sm text-muted-foreground">Пока нет. Начните с кнопки «Новый эксперимент».</p>
          ) : (
            <ul className="divide-y">
              {experiments.slice(0, 5).map((e) => (
                <li key={e.id}>
                  <Link href={`/experiments/${e.id}`} className="flex items-center justify-between gap-3 py-2.5 hover:underline">
                    <span className="min-w-0 truncate">{e.title}</span>
                    <Badge variant={EXPERIMENT_STATUS[e.status].variant}>{EXPERIMENT_STATUS[e.status].label}</Badge>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      <Sheet open={!!opened} onOpenChange={(v) => !v && setOpened(null)} title="Отчёт о качестве">
        {opened && <QualityReport imp={opened} />}
      </Sheet>
    </div>
  );
}

function ConsentCard({ canGrant, onGranted }: { canGrant: boolean; onGranted: () => void }) {
  const [agree, setAgree] = useState(false);
  const [error, setError] = useState<string | null>(null);
  if (!canGrant)
    return (
      <Card>
        <CardHeader>
          <CardTitle>Ждём согласия собственника</CardTitle>
          <CardDescription>Загрузка данных откроется, когда собственник бизнеса подтвердит согласие на обработку.</CardDescription>
        </CardHeader>
      </Card>
    );
  async function grant() {
    const { error } = await api.POST("/api/v1/consents", { body: { text_version: CONSENT_VERSION, ...businessParam() } });
    if (error) return setError(errorText(error));
    onGranted();
  }
  return (
    <Card>
      <CardHeader>
        <CardTitle>Согласие на обработку данных</CardTitle>
        <CardDescription>Нужно один раз перед первой загрузкой.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4 text-sm">
        <p>
          Я разрешаю загружать в сервис выгрузки клиентов, платежей, посещений и обязательств моего бизнеса для замера эффекта
          действий. В файлах только внутренние номера клиентов, без ФИО, телефонов и email. Согласие можно отозвать.
        </p>
        <label className="flex items-start gap-2">
          <Checkbox checked={agree} onCheckedChange={(v) => setAgree(v === true)} />
          <span>Согласен, я собственник бизнеса или действую от его имени</span>
        </label>
        {error && <Alert variant="destructive">{error}</Alert>}
        <Button onClick={grant} disabled={!agree}>
          Подтвердить
        </Button>
      </CardContent>
    </Card>
  );
}

function UploadCard({ onUploaded }: { onUploaded: (imp: ImportFile) => void }) {
  const [kind, setKind] = useState<Kind>("payments");
  const [busy, setBusy] = useState(false);
  const [drag, setDrag] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const input = useRef<HTMLInputElement>(null);

  async function send(file: File) {
    setBusy(true);
    setError(null);
    const fd = new FormData();
    fd.set("kind", kind);
    fd.set("file", file);
    const b = businessParam();
    if (b.business_id) fd.set("business_id", b.business_id);
    const res = await fetch("/api/v1/imports", { method: "POST", body: fd });
    const body = await res.json().catch(() => null);
    setBusy(false);
    if (input.current) input.current.value = "";
    if (!res.ok) return setError(errorText(body));
    onUploaded(body as ImportFile);
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Загрузка CSV</CardTitle>
        <CardDescription>Разделитель «;» или «,», кодировка UTF-8 или Windows-1251. ФИО и телефоны не нужны.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="space-y-2">
          <Label htmlFor="kind">Что загружаем</Label>
          <Select id="kind" value={kind} onChange={(e) => setKind(e.target.value as Kind)}>
            {KINDS.map((k) => (
              <option key={k} value={k}>
                {IMPORT_KIND[k]}
              </option>
            ))}
          </Select>
          <a href={`/templates/${kind}.csv`} download className="inline-flex items-center gap-1 text-sm text-primary hover:underline">
            <FileDown className="h-4 w-4" /> Шаблон CSV: {IMPORT_KIND[kind].toLowerCase()}
          </a>
        </div>
        <div
          role="button"
          tabIndex={0}
          aria-label="Выбрать файл или перетащить его сюда"
          onClick={() => input.current?.click()}
          onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && input.current?.click()}
          onDragOver={(e) => {
            e.preventDefault();
            setDrag(true);
          }}
          onDragLeave={() => setDrag(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDrag(false);
            const f = e.dataTransfer.files[0];
            if (f) send(f);
          }}
          className={`flex cursor-pointer flex-col items-center gap-2 rounded-lg border-2 border-dashed p-6 text-center text-sm transition-colors ${
            drag ? "border-primary bg-accent" : "border-input hover:bg-accent/50"
          }`}
        >
          <Upload className="h-6 w-6 text-muted-foreground" />
          {busy ? "Проверяем файл…" : "Перетащите файл сюда или нажмите, чтобы выбрать"}
          <input
            ref={input}
            type="file"
            accept=".csv,text/csv"
            className="hidden"
            onChange={(e) => e.target.files?.[0] && send(e.target.files[0])}
          />
        </div>
        {error && <Alert variant="destructive">{error}</Alert>}
      </CardContent>
    </Card>
  );
}
