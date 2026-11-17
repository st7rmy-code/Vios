import createClient, { type Middleware } from "openapi-fetch";

import type { components, paths } from "./schema";

export type Schemas = components["schemas"];
export type User = Schemas["MeOut"];
export type Experiment = Schemas["ExperimentOut"];
export type ImportFile = Schemas["ImportOut"];
export type Protocol = Schemas["Protocol"];
export type ApiErr = { detail?: unknown; code?: string };

/** Выбранный администратором бизнес: подставляется в запросы как business_id. */
let currentBusiness: string | null = null;
export const setRequestBusiness = (id: string | null) => {
  currentBusiness = id;
};

const middleware: Middleware = {
  onRequest({ request }) {
    if (!currentBusiness || request.method !== "GET") return request;
    const url = new URL(request.url);
    if (url.pathname.match(/^\/api\/v1\/(imports|experiments|audit|consents|data\/summary|users)$/) && !url.searchParams.has("business_id")) {
      url.searchParams.set("business_id", currentBusiness);
      return new Request(url, request);
    }
    return request;
  },
  onResponse({ response }) {
    if (response.status === 401 && typeof window !== "undefined" && !location.pathname.startsWith("/login")) {
      location.href = `/login?next=${encodeURIComponent(location.pathname + location.search)}`;
    }
    return response;
  },
};

/** Типизированный клиент из backend/openapi.json (npm run gen:api). Токен в httpOnly cookie, его добавляет прокси Next. */
export const api = createClient<paths>({ baseUrl: typeof window === "undefined" ? "http://localhost" : "" });
api.use(middleware);

export const businessParam = () => (currentBusiness ? { business_id: currentBusiness } : {});

/** Текст ошибки API ({detail, code}) для пользователя. */
export function errorText(err: unknown): string {
  if (!err) return "Неизвестная ошибка";
  const d = (err as ApiErr).detail;
  if (typeof d === "string") return d;
  if (Array.isArray(d)) return d.map((x) => (x as { msg?: string }).msg ?? "").join("; ");
  return "Ошибка запроса";
}
export const errorCode = (err: unknown) => (err as ApiErr | undefined)?.code;
