"use client";

import { Check, Copy } from "lucide-react";
import { useState } from "react";

/** Хэш или seed с кнопкой копирования. */
export function CopyValue({ value, short }: { value: string | null | undefined; short?: boolean }) {
  const [done, setDone] = useState(false);
  if (!value) return <span className="text-muted-foreground">—</span>;
  return (
    <span className="inline-flex max-w-full items-start gap-1.5">
      <code className="break-all font-mono text-xs">{short ? `${value.slice(0, 16)}…` : value}</code>
      <button
        type="button"
        className="no-print shrink-0 rounded p-0.5 text-muted-foreground hover:text-foreground"
        aria-label="Скопировать"
        title="Скопировать"
        onClick={async () => {
          try {
            await navigator.clipboard.writeText(value);
            setDone(true);
            setTimeout(() => setDone(false), 1500);
          } catch {
            /* буфер обмена недоступен */
          }
        }}
      >
        {done ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
      </button>
    </span>
  );
}
