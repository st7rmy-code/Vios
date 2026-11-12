"use client";

import { ShieldCheck, ShieldX } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { api, type Schemas } from "@/lib/api/client";
import { dateTime, num } from "@/lib/format";
import { AUDIT_ACTION } from "@/lib/labels";

const PAGE = 50;

export default function JournalPage() {
  const [rows, setRows] = useState<Schemas["AuditOut"][]>([]);
  const [more, setMore] = useState(true);
  const [chain, setChain] = useState<Schemas["ChainOut"] | null>(null);
  const [checking, setChecking] = useState(false);

  const load = useCallback(async (before?: number) => {
    const { data } = await api.GET("/api/v1/audit", { params: { query: { limit: PAGE, before_seq: before } } });
    const page = data ?? [];
    setRows((r) => (before ? [...r, ...page] : page));
    setMore(page.length === PAGE);
  }, []);

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
          <p className="text-sm text-muted-foreground">
            Записи только добавляются. Каждая содержит хэш предыдущей, поэтому подмену видно.
          </p>
        </div>
        <Button onClick={verify} disabled={checking}>
          {checking ? "Проверяем…" : "Проверить цепочку"}
        </Button>
      </div>

      {chain &&
        (chain.ok ? (
          <Alert variant="success" className="flex items-center gap-2">
            <ShieldCheck className="h-5 w-5" /> Цепочка цела: проверено {num(chain.checked)} записей.
          </Alert>
        ) : (
          <Alert variant="destructive" className="flex items-center gap-2">
            <ShieldX className="h-5 w-5" /> Цепочка нарушена на записи №{chain.broken_at_seq}: {chain.reason}.
          </Alert>
        ))}

      <Card>
        <CardHeader>
          <CardTitle>События</CardTitle>
        </CardHeader>
        <CardContent>
          <Table>
            <THead>
              <TR>
                <TH>№</TH>
                <TH>Когда</TH>
                <TH>Событие</TH>
                <TH className="hidden md:table-cell">Объект</TH>
                <TH className="hidden lg:table-cell">Хэш</TH>
              </TR>
            </THead>
            <TBody>
              {rows.map((r) => (
                <TR key={r.seq}>
                  <TD className="tabular-nums">{r.seq}</TD>
                  <TD className="whitespace-nowrap">{dateTime(r.occurred_at)}</TD>
                  <TD>{AUDIT_ACTION[r.action] ?? r.action}</TD>
                  <TD className="hidden font-mono text-xs md:table-cell">
                    {r.entity_type} {r.entity_id?.slice(0, 8)}
                  </TD>
                  <TD className="hidden font-mono text-xs text-muted-foreground lg:table-cell">{r.hash.slice(0, 16)}…</TD>
                </TR>
              ))}
            </TBody>
          </Table>
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
