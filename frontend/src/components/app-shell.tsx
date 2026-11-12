"use client";

import { LogOut } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { Button } from "@/components/ui/button";
import { ROLE_LABEL, isManager, useSession } from "@/lib/session";
import { cn } from "@/lib/utils";

export function AppShell({ children }: { children: React.ReactNode }) {
  const { user, loading, logout } = useSession();
  const path = usePathname();
  const links = [
    { href: "/cabinet", label: "Кабинет" },
    ...(isManager(user) ? [{ href: "/experiments/new", label: "Новый эксперимент" }, { href: "/journal", label: "Журнал" }] : []),
  ];

  return (
    <div className="min-h-screen">
      <header className="no-print sticky top-0 z-10 border-b bg-background/95 backdrop-blur">
        <div className="container flex h-14 items-center gap-3">
          <Link href="/cabinet" className="font-semibold">
            Сверка
          </Link>
          <nav className="flex min-w-0 flex-1 gap-1 overflow-x-auto">
            {links.map((l) => (
              <Link
                key={l.href}
                href={l.href}
                className={cn(
                  "whitespace-nowrap rounded-md px-2.5 py-1.5 text-sm text-muted-foreground hover:bg-accent hover:text-foreground",
                  path === l.href && "bg-accent text-foreground",
                )}
              >
                {l.label}
              </Link>
            ))}
          </nav>
          {user && (
            <span className="hidden text-sm text-muted-foreground sm:inline">
              {user.login} · {ROLE_LABEL[user.role]}
            </span>
          )}
          <Button variant="ghost" size="icon" onClick={logout} aria-label="Выйти" title="Выйти">
            <LogOut className="h-4 w-4" />
          </Button>
        </div>
      </header>
      <main className="container py-6">{loading ? <p className="text-muted-foreground">Загрузка…</p> : children}</main>
    </div>
  );
}
