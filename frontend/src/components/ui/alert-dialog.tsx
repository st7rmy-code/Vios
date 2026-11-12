"use client";

import * as A from "@radix-ui/react-alert-dialog";
import * as React from "react";

import { buttonVariants } from "@/components/ui/button";

/** Подтверждение необратимого шага (shadcn AlertDialog). */
export function ConfirmDialog({
  trigger,
  title,
  description,
  confirm,
  onConfirm,
}: {
  trigger: React.ReactNode;
  title: string;
  description: React.ReactNode;
  confirm: string;
  onConfirm: () => void;
}) {
  return (
    <A.Root>
      <A.Trigger asChild>{trigger}</A.Trigger>
      <A.Portal>
        <A.Overlay className="fixed inset-0 z-40 bg-black/40" />
        <A.Content className="fixed left-1/2 top-1/2 z-50 w-[calc(100%-2rem)] max-w-md -translate-x-1/2 -translate-y-1/2 space-y-4 rounded-lg border bg-background p-6 shadow-lg">
          <A.Title className="text-lg font-semibold">{title}</A.Title>
          <A.Description asChild>
            <div className="text-sm text-muted-foreground">{description}</div>
          </A.Description>
          <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
            <A.Cancel className={buttonVariants({ variant: "outline" })}>Отмена</A.Cancel>
            <A.Action className={buttonVariants()} onClick={onConfirm}>
              {confirm}
            </A.Action>
          </div>
        </A.Content>
      </A.Portal>
    </A.Root>
  );
}
