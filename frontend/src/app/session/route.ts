import { cookies } from "next/headers";

import { BACKEND_URL, TOKEN_COOKIE } from "@/lib/backend";

export const dynamic = "force-dynamic";

/** Вход: логин и пароль уходят в FastAPI, токен кладём в httpOnly cookie. */
export async function POST(req: Request) {
  const { login, password } = (await req.json()) as { login?: string; password?: string };
  const res = await fetch(`${BACKEND_URL}/api/v1/auth/token`, {
    method: "POST",
    headers: { "content-type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({ username: login ?? "", password: password ?? "", grant_type: "password" }),
    cache: "no-store",
  });
  const data = await res.json().catch(() => ({ detail: "Сервер недоступен" }));
  if (!res.ok) return Response.json(data, { status: res.status });
  (await cookies()).set(TOKEN_COOKIE, data.access_token, {
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production" && process.env.SVERKA_INSECURE_COOKIE !== "1",
    path: "/",
    maxAge: 60 * 60 * 12,
  });
  return Response.json({ ok: true });
}

/** Выход: удаляем cookie. */
export async function DELETE() {
  (await cookies()).delete(TOKEN_COOKIE);
  return new Response(null, { status: 204 });
}
