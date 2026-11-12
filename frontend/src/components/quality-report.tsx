import { AlertTriangle, CheckCircle2, ShieldAlert } from "lucide-react";

import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import type { ImportFile } from "@/lib/api/client";
import { bytes, date, kopecksToRubExact, num, percent } from "@/lib/format";
import { IMPORT_KIND } from "@/lib/labels";

type Report = {
  blocking: string[];
  pii_columns: Record<string, string>;
  rows_total: number;
  rows_valid: number;
  rows_invalid: number;
  duplicates: number;
  errors: { line: number; column: string | null; code: string; message: string }[];
  errors_truncated: boolean;
  unknown_columns: string[];
  customers?: number;
  date_min?: string | null;
  date_max?: string | null;
  total_amount_kopecks?: number;
  valid_share?: number;
  same_file_imported_before?: boolean;
  encoding?: string;
};

export function QualityReport({ imp }: { imp: ImportFile }) {
  const r = imp.quality_report as unknown as Report;
  const rejected = imp.status === "rejected";
  const pii = Object.entries(r.pii_columns ?? {});

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        {rejected ? (
          <Badge variant="destructive">Отклонён</Badge>
        ) : r.rows_invalid ? (
          <Badge variant="warning">Принят с замечаниями</Badge>
        ) : (
          <Badge variant="success">Принят</Badge>
        )}
        <span className="text-sm text-muted-foreground">
          {IMPORT_KIND[imp.kind]} · {imp.filename} · {bytes(imp.size_bytes)}
        </span>
      </div>

      {pii.length > 0 && (
        <Alert variant="destructive" className="flex gap-3">
          <ShieldAlert className="mt-0.5 h-5 w-5 shrink-0" />
          <div className="space-y-1">
            <strong>В файле персональные данные клиентов, он не сохранён.</strong>
            <ul className="list-disc pl-5">
              {pii.map(([col, why]) => (
                <li key={col}>
                  «{col}»: {why}
                </li>
              ))}
            </ul>
            <p>Удалите эти колонки и загрузите файл снова. Нужен только идентификатор клиента.</p>
          </div>
        </Alert>
      )}
      {r.blocking.filter((b) => !b.startsWith("Файл содержит персональные")).map((b) => (
        <Alert key={b} variant="destructive" className="flex gap-3">
          <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0" />
          <span>{b}</span>
        </Alert>
      ))}
      {r.same_file_imported_before && (
        <Alert variant="warning">Этот же файл уже загружался раньше: повторные оплаты по номеру не задвоятся.</Alert>
      )}

      {!rejected && (
        <dl className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <Stat label="Строк в файле" value={num(r.rows_total)} />
          <Stat label="Корректных" value={`${num(r.rows_valid)} (${percent(r.valid_share)})`} />
          <Stat label="С ошибками" value={num(r.rows_invalid)} />
          <Stat label="Дубликатов" value={num(r.duplicates)} />
          <Stat label="Клиентов" value={num(r.customers)} />
          <Stat label="Период" value={`${date(r.date_min)} — ${date(r.date_max)}`} />
          {r.total_amount_kopecks != null && <Stat label="Сумма оплат" value={kopecksToRubExact(r.total_amount_kopecks)} />}
          {r.unknown_columns.length > 0 && <Stat label="Лишние колонки" value={r.unknown_columns.join(", ")} />}
        </dl>
      )}

      {!rejected && r.errors.length === 0 && (
        <p className="flex items-center gap-2 text-sm text-success">
          <CheckCircle2 className="h-4 w-4" /> Ошибок в строках нет.
        </p>
      )}
      {r.errors.length > 0 && (
        <div>
          <p className="mb-2 text-sm font-medium">
            Строки с ошибками{r.errors_truncated ? " (первые 100)" : ""}
          </p>
          <Table>
            <THead>
              <TR>
                <TH>Строка</TH>
                <TH>Колонка</TH>
                <TH>Что не так</TH>
              </TR>
            </THead>
            <TBody>
              {r.errors.map((e, i) => (
                <TR key={i}>
                  <TD className="tabular-nums">{e.line}</TD>
                  <TD>{e.column ?? "—"}</TD>
                  <TD>{e.message}</TD>
                </TR>
              ))}
            </TBody>
          </Table>
        </div>
      )}
      <p className="break-all font-mono text-xs text-muted-foreground">SHA-256: {imp.sha256}</p>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border p-3">
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="mt-1 text-sm font-semibold tabular-nums">{value}</dd>
    </div>
  );
}
