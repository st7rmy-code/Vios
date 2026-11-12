"use client";

import { ChevronDown, ChevronRight, ShieldCheck, ShieldX } from "lucide-react";
import Link from "next/link";
import { Fragment, useCallback, useEffect, useState } from "react";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { api, type Schemas } from "@/lib/api/client";
import { dateTime, num } from "@/lib/format";
import { AUDIT_ACTION, ENTITY_TYPE } from "@/lib/labels";

const PAGE = 50;
const GROUPS: { value: string; label: string }[] = [
  { value: "", label: "Все события" },
  { value: "experiment.", label: "Эксперименты" },
  { value: "result.", label: "Результаты" },
  { value: "import.", label: "Импорт" },
  { value: "assignments.", label: "Выгрузки групп" },
  { value: "consent.", label: "Согласия" },
  { value: "user.", label: "Команда" },
  { value: "auth.", label: "Входы" },
];

export default function AuditPage() {
  const [rows, setRows] = useState<Schemas["AuditOut"][]>([]);
  const [more, setMore] = useState(true);
  const [action, setAction] = useState("");
  const [entityId, setEntityId] = useState("");
  const [open, setOpen] = useState<number | null>(null);
  const [chain, setChain] = useState<Schemas["ChainOut"] | null>(null);
  const [checking, setChecking] = useState(false);

  const load = useCallback(
    async (before?: number) => {
      const { data } = await api.GET("/api/v1/audit", {
        params: { query: { limit: PAGE, before_seq: before, action: action || undefined, entity_id: entityId.trim() || undefined } },
      });
      const page = data ?? [];
      setRows((r) => (before ? [...r, ...page] : page));
      setMore(page.length === PAGE);
    },
    [action, entityId],
  );

  useEffect(() => {
    load();
  }, [load]);

  async function verify() {
    setChecking(true);
    const { data } = await api.GET("/api/v1/audit/verify");
    setChain(data ?? null);
    setChecking(false);
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">Журнал</h1>
          <p className="text-sm text-muted-foreground">Записи только добавляются. Каждая содержит хэш предыдущей, поэтому подмену видно.</p>
        </div>
        <Button onClick={verify} disabled={checking}>
          {checking ? "Проверяем…" : "Проверить цепочку"}
        </Button>
      </div>

      {chain &&
        (chain.ok ? (
          <Alert variant="success" className="flex items-center gap-2">
            <ShieldCheck className="h-5 w-5" /> Цепочка цела, проверено {num(chain.checked)} записей.
          </Alert>
        ) : (
          <Alert variant="destructive" className="flex items-center gap-2">
            <ShieldX className="h-5 w-5" /> Цепочка нарушена на записи № {chain.broken_at_seq}: {chain.reason}.
          </Alert>
        ))}

      <div className="flex flex-wrap gap-2">
        <Select aria-label="Тип события" className="w-auto" value={action} onChange={(e) => setAction(e.target.value)}>
          {GROUPS.map((g) => (
            <option key={g.value} value={g.value}>
              {g.label}
            </option>
          ))}
        </Select>
        <Input
          aria-label="ID объекта"
          placeholder="ID объекта"
          className="w-full max-w-xs"
          value={entityId}
          onChange={(e) => setEntityId(e.target.value)}
        />
      </div>

      <Card>
        <CardContent className="pt-2 sm:pt-2">
          <Table>
            <THead>
              <TR>
                <TH className="w-6" />
                <TH>№</TH>
                <TH>Время</TH>
                <TH className="hidden sm:table-cell">Кто</TH>
                <TH>Событие</TH>
                <TH className="hidden md:table-cell">Объект</TH>
                <TH className="hidden lg:table-cell">Хэш</TH>
              </TR>
            </THead>
            <TBody>
              {rows.map((r) => (
                <Fragment key={r.seq}>
                  <TR className="cursor-pointer" onClick={() => setOpen(open === r.seq ? null : r.seq)}>
                    <TD>{open === r.seq ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}</TD>
                    <TD className="tabular-nums">{r.seq}</TD>
                    <TD className="whitespace-nowrap">{dateTime(r.occurred_at)}</TD>
                    <TD className="hidden sm:table-cell">{r.actor_login ?? "система"}</TD>
                    <TD>{AUDIT_ACTION[r.action] ?? r.action}</TD>
                    <TD className="hidden md:table-cell">
                      <EntityLink type={r.entity_type} id={r.entity_id} />
                    </TD>
                    <TD className="hidden font-mono text-xs text-muted-foreground lg:table-cell">{r.hash.slice(0, 12)}…</TD>
                  </TR>
                  {open === r.seq && (
                    <TR className="hover:bg-transparent">
                      <TD colSpan={7} className="bg-muted/40">
                        <div className="space-y-2 text-xs">
                          <p className="sm:hidden">Кто: {r.actor_login ?? "система"}</p>
                          <p className="md:hidden">
                            Объект: <EntityLink type={r.entity_type} id={r.entity_id} />
                          </p>
                          <pre className="max-h-72 overflow-auto whitespace-pre-wrap break-all rounded bg-background p-2 font-mono">
                            {JSON.stringify(r.payload, null, 2)}
                          </pre>
                          <p className="break-all font-mono">prev_hash {r.prev_hash}</p>
                          <p className="break-all font-mono">hash {r.hash}</p>
                        </div>
                      </TD>
                    </TR>
                  )}
                </Fragment>
              ))}
            </TBody>
          </Table>
          {rows.length === 0 && <p className="py-4 text-sm text-muted-foreground">Записей нет.</p>}
          {more && rows.length > 0 && (
            <Button variant="outline" className="mt-4" onClick={() => load(rows[rows.length - 1].seq)}>
              Показать ещё
            </Button>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function EntityLink({ type, id }: { type: string; id: string | null }) {
  const label = `${ENTITY_TYPE[type] ?? type}${id ? ` ${id.slice(0, 8)}` : ""}`;
  if (type === "experiment" && id)
    return (
      <Link href={`/experiments/${id}`} className="text-primary hover:underline" onClick={(e) => e.stopPropagation()}>
        {label}
      </Link>
    );
  return <span>{label}</span>;
}
