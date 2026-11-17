"use client";

import * as C from "@radix-ui/react-checkbox";
import { Check } from "lucide-react";
import * as React from "react";

export function Checkbox(props: React.ComponentPropsWithoutRef<typeof C.Root>) {
  return (
    <C.Root
      className="peer mt-0.5 h-4 w-4 shrink-0 rounded-sm border border-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring data-[state=checked]:bg-primary data-[state=checked]:text-primary-foreground"
      {...props}
    >
      <C.Indicator className="flex items-center justify-center">
        <Check className="h-3.5 w-3.5" />
      </C.Indicator>
    </C.Root>
  );
}
