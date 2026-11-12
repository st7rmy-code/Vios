"use client";

import { useRouter } from "next/navigation";
import { createContext, useCallback, useContext, useEffect, useState } from "react";

import { api, tokenStore, type User } from "@/lib/api/client";

type Session = { user: User | null; loading: boolean; logout: () => void };
const Ctx = createContext<Session>({ user: null, loading: true, logout: () => {} });

export function SessionProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const router = useRouter();

  useEffect(() => {
    if (!tokenStore.get()) {
      setLoading(false);
      router.replace("/login");
      return;
    }
    api.GET("/api/v1/auth/me").then(({ data }) => {
      setUser(data ?? null);
      setLoading(false);
      if (!data) router.replace("/login");
    });
  }, [router]);

  const logout = useCallback(() => {
    tokenStore.set(null);
    router.replace("/login");
  }, [router]);

  return <Ctx.Provider value={{ user, loading, logout }}>{children}</Ctx.Provider>;
}

export const useSession = () => useContext(Ctx);
export const isManager = (u: User | null) => u?.role === "owner" || u?.role === "admin";
export const ROLE_LABEL: Record<User["role"], string> = {
  admin: "Администратор",
  owner: "Собственник",
  executor: "Исполнитель",
};
