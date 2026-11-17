"use client";

import * as A from "@radix-ui/react-accordion";
import { ChevronDown } from "lucide-react";
import * as React from "react";

export const Accordion = A.Root;

export function AccordionItem({ value, title, children }: { value: string; title: string; children: React.ReactNode }) {
  return (
    <A.Item value={value} className="border-b">
      <A.Header>
        <A.Trigger className="group flex w-full items-center justify-between py-3 text-left text-sm font-medium hover:underline">
          {title}
          <ChevronDown className="h-4 w-4 shrink-0 transition-transform group-data-[state=open]:rotate-180" />
        </A.Trigger>
      </A.Header>
      <A.Content className="pb-4 text-sm">{children}</A.Content>
    </A.Item>
  );
}
