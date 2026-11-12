"use client";

import { usePathname, useRouter } from "next/navigation";
import { createContext, useCallback, useContext, useEffect, useState } from "react";

import { api, setRequestBusiness, type Schemas, type User } from "@/lib/api/client";

type Session = {
  user: User | null;
  loading: boolean;
  logout: () => void;
  /** Бизнес, с которым работает экран: свой у owner/executor, выбранный у admin. */
  businessId: string | null;
  businessName: string | null;
  businesses: Schemas["BusinessOut"][];
  selectBusiness: (id: string) => void;
};
const Ctx = createContext<Session>({
  user: null,
  loading: true,
  logout: () => {},
  businessId: null,
  businessName: null,
  businesses: [],
  selectBusiness: () => {},
});
const KEY = "sverka.business";

export function SessionProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [businesses, setBusinesses] = useState<Schemas["BusinessOut"][]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const router = useRouter();
  const path = usePathname();

  useEffect(() => {
    api.GET("/api/v1/auth/me").then(async ({ data }) => {
      if (!data) {
        router.replace(`/login?next=${encodeURIComponent(path)}`);
        return;
      }
      if (data.role === "admin") {
        const list = (await api.GET("/api/v1/businesses")).data ?? [];
        setBusinesses(list);
        let saved: string | null = null;
        try {
          saved = localStorage.getItem(KEY);
        } catch {
          /* приватный режим */
        }
        const id = list.find((b) => b.id === saved)?.id ?? list[0]?.id ?? null;
        setRequestBusiness(id);
        setSelected(id);
      }
      setUser(data);
      setLoading(false);
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [router]);

  const selectBusiness = useCallback((id: string) => {
    try {
      localStorage.setItem(KEY, id);
    } catch {
      /* приватный режим */
    }
    setRequestBusiness(id);
    setSelected(id);
  }, []);

  const logout = useCallback(async () => {
    await fetch("/session", { method: "DELETE" });
    router.replace("/login");
  }, [router]);

  const businessId = user?.role === "admin" ? selected : (user?.business_id ?? null);
  const businessName =
    user?.role === "admin" ? (businesses.find((b) => b.id === selected)?.name ?? null) : (user?.business_name ?? null);

  return (
    <Ctx.Provider value={{ user, loading, logout, businessId, businessName, businesses, selectBusiness }}>
      {children}
    </Ctx.Provider>
  );
}

export const useSession = () => useContext(Ctx);
export const isManager = (u: User | null) => u?.role === "owner" || u?.role === "admin";
export const ROLE_LABEL: Record<User["role"], string> = {
  admin: "Администратор",
  owner: "Собственник",
  executor: "Исполнитель",
};
