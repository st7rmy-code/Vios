"use client";

import { LogOut } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/select";
import { ROLE_LABEL, isManager, useSession } from "@/lib/session";
import { cn } from "@/lib/utils";

export function AppShell({ children }: { children: React.ReactNode }) {
  const { user, loading, logout, businessId, businessName, businesses, selectBusiness } = useSession();
  const path = usePathname();
  const manager = isManager(user);
  const links = [
    ...(manager ? [{ href: "/", label: "Кабинет" }] : []),
    { href: "/experiments", label: "Эксперименты" },
    ...(manager
      ? [
          { href: "/audit", label: "Журнал" },
          { href: "/team", label: "Команда" },
        ]
      : []),
    ...(user?.role === "admin" ? [{ href: "/admin/businesses", label: "Бизнесы" }] : []),
  ];
  const active = (href: string) => (href === "/" ? path === "/" : path.startsWith(href));

  return (
    <div className="min-h-screen">
      <header className="no-print sticky top-0 z-30 border-b bg-background/95 backdrop-blur">
        <div className="container flex min-h-14 flex-wrap items-center gap-x-3 gap-y-1 py-2">
          <Link href={manager ? "/" : "/experiments"} className="font-semibold">
            Сверка
          </Link>
          {user?.role === "admin" ? (
            <Select
              aria-label="Бизнес"
              className="h-8 w-auto max-w-[12rem] py-0 text-sm"
              value={businessId ?? ""}
              onChange={(e) => selectBusiness(e.target.value)}
            >
              {businesses.length === 0 && <option value="">Бизнесов нет</option>}
              {businesses.map((b) => (
                <option key={b.id} value={b.id}>
                  {b.name}
                </option>
              ))}
            </Select>
          ) : (
            businessName && <span className="truncate text-sm text-muted-foreground">{businessName}</span>
          )}
          <div className="ml-auto flex items-center gap-2">
            {user && (
              <span className="hidden text-sm text-muted-foreground sm:inline">
                {user.login} · {ROLE_LABEL[user.role]}
              </span>
            )}
            <Button variant="ghost" size="icon" onClick={logout} aria-label="Выйти" title="Выйти">
              <LogOut className="h-4 w-4" />
            </Button>
          </div>
          <nav className="-mx-1 flex w-full gap-1 overflow-x-auto pb-1 sm:order-none">
            {links.map((l) => (
              <Link
                key={l.href}
                href={l.href}
                className={cn(
                  "whitespace-nowrap rounded-md px-2.5 py-1.5 text-sm text-muted-foreground hover:bg-accent hover:text-foreground",
                  active(l.href) && "bg-accent text-foreground",
                )}
              >
                {l.label}
              </Link>
            ))}
          </nav>
        </div>
      </header>
      <main key={businessId ?? "none"} className="container py-6">
        {loading ? <p className="text-muted-foreground">Загрузка…</p> : children}
      </main>
    </div>
  );
}
