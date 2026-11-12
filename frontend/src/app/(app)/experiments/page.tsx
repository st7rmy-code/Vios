"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { api, type Experiment } from "@/lib/api/client";
import { addDays, date } from "@/lib/format";
import { EXPERIMENT_STATUS } from "@/lib/labels";
import { isManager, useSession } from "@/lib/session";

export default function ExperimentsPage() {
  const { user } = useSession();
  const [list, setList] = useState<Experiment[] | null>(null);
  useEffect(() => {
    api.GET("/api/v1/experiments").then(({ data }) => setList(data ?? []));
  }, []);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">Эксперименты</h1>
          {!isManager(user) && <p className="text-sm text-muted-foreground">Откройте эксперимент, чтобы увидеть, с кем работать.</p>}
        </div>
        {isManager(user) && (
          <Button asChild>
            <Link href="/experiments/new">Новый эксперимент</Link>
          </Button>
        )}
      </div>
      {list === null ? (
        <p className="text-muted-foreground">Загрузка…</p>
      ) : list.length === 0 ? (
        <p className="text-muted-foreground">Экспериментов пока нет.</p>
      ) : (
        <div className="grid gap-3 md:grid-cols-2">
          {list.map((e) => {
            const p = e.protocol as { as_of: string; window_days: number; action: string };
            const st = EXPERIMENT_STATUS[e.status];
            return (
              <Link key={e.id} href={`/experiments/${e.id}`}>
                <Card className="h-full transition-colors hover:bg-accent/40">
                  <CardContent className="space-y-2 pt-4 sm:pt-5">
                    <div className="flex items-start justify-between gap-2">
                      <h2 className="font-semibold">{e.title}</h2>
                      <Badge variant={st.variant}>{st.label}</Badge>
                    </div>
                    <p className="line-clamp-2 text-sm text-muted-foreground">{p.action}</p>
                    <p className="text-xs text-muted-foreground">
                      Срез {date(p.as_of)}, замер до {date(addDays(p.as_of, p.window_days))}
                    </p>
                  </CardContent>
                </Card>
              </Link>
            );
          })}
        </div>
      )}
    </div>
  );
}
