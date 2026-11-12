"use client";

import * as D from "@radix-ui/react-dialog";
import { X } from "lucide-react";
import * as React from "react";

import { cn } from "@/lib/utils";

/** Боковая панель (shadcn Sheet) на Radix Dialog. */
export function Sheet({
  open,
  onOpenChange,
  title,
  children,
  className,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  title: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <D.Root open={open} onOpenChange={onOpenChange}>
      <D.Portal>
        <D.Overlay className="fixed inset-0 z-40 bg-black/40" />
        <D.Content
          className={cn(
            "fixed inset-y-0 right-0 z-50 flex w-full max-w-2xl flex-col gap-4 overflow-y-auto border-l bg-background p-4 shadow-lg sm:p-6",
            className,
          )}
          aria-describedby={undefined}
        >
          <div className="flex items-start justify-between gap-3">
            <D.Title className="text-lg font-semibold">{title}</D.Title>
            <D.Close className="rounded-sm p-1 opacity-70 hover:opacity-100" aria-label="Закрыть">
              <X className="h-5 w-5" />
            </D.Close>
          </div>
          {children}
        </D.Content>
      </D.Portal>
    </D.Root>
  );
}
