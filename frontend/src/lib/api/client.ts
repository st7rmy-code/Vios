import createClient, { type Middleware } from "openapi-fetch";

import type { components, paths } from "./schema";

export type Schemas = components["schemas"];
export type User = Schemas["UserOut"];
export type Experiment = Schemas["ExperimentOut"];
export type ImportFile = Schemas["ImportOut"];
export type Protocol = Schemas["Protocol"];

const TOKEN_KEY = "sverka.token";

export const tokenStore = {
  get(): string | null {
    try {
      return typeof window === "undefined" ? null : window.localStorage.getItem(TOKEN_KEY);
    } catch {
      return null;
    }
  },
  set(t: string | null) {
    try {
      if (t) window.localStorage.setItem(TOKEN_KEY, t);
      else window.localStorage.removeItem(TOKEN_KEY);
    } catch {
      /* приватный режим: токен живёт до перезагрузки */
    }
  },
};

const auth: Middleware = {
  onRequest({ request }) {
    const t = tokenStore.get();
    if (t) request.headers.set("Authorization", `Bearer ${t}`);
    return request;
  },
  onResponse({ response }) {
    if (response.status === 401 && typeof window !== "undefined" && !location.pathname.startsWith("/login")) {
      tokenStore.set(null);
      location.href = "/login";
    }
    return response;
  },
};

/** Типизированный клиент, сгенерирован из backend/openapi.json (npm run gen:api). */
export const api = createClient<paths>({ baseUrl: "" });
api.use(auth);

/** Текст ошибки FastAPI для пользователя. */
export function errorText(err: unknown): string {
  if (!err) return "Неизвестная ошибка";
  const d = (err as { detail?: unknown }).detail;
  if (typeof d === "string") return d;
  if (Array.isArray(d)) return d.map((x) => (x as { msg?: string }).msg ?? "").join("; ");
  return "Ошибка запроса";
}
