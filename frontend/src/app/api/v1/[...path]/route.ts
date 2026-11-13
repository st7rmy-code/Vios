import { cookies } from "next/headers";
import type { NextRequest } from "next/server";

import { BACKEND_URL, TOKEN_COOKIE, forbidden, isSameOriginMutation } from "@/lib/backend";

export const dynamic = "force-dynamic";

/**
 * Прокси к FastAPI. Токен лежит в httpOnly cookie, JavaScript страницы его не видит:
 * здесь он превращается в заголовок Authorization.
 */
async function proxy(req: NextRequest, { params }: { params: Promise<{ path: string[] }> }) {
  if (!isSameOriginMutation(req)) return forbidden();
  const { path } = await params;
  // «..» и «.» encodeURIComponent не кодирует: fetch нормализовал бы путь и вышел за /api/v1/
  if (path.some((p) => p === ".." || p === "." || p === "")) {
    return Response.json({ detail: "Не найдено", code: "not_found" }, { status: 404 });
  }
  const url = `${BACKEND_URL}/api/v1/${path.map(encodeURIComponent).join("/")}${req.nextUrl.search}`;
  const headers = new Headers();
  for (const h of ["content-type", "accept"]) {
    const v = req.headers.get(h);
    if (v) headers.set(h, v);
  }
  const token = (await cookies()).get(TOKEN_COOKIE)?.value;
  if (token) headers.set("authorization", `Bearer ${token}`);
  const body = req.method === "GET" || req.method === "HEAD" ? undefined : await req.arrayBuffer();
  const res = await fetch(url, { method: req.method, headers, body, redirect: "manual", cache: "no-store" });
  const out = new Headers();
  for (const h of ["content-type", "content-disposition"]) {
    const v = res.headers.get(h);
    if (v) out.set(h, v);
  }
  return new Response(res.status === 204 ? null : res.body, { status: res.status, headers: out });
}

export { proxy as DELETE, proxy as GET, proxy as PATCH, proxy as POST, proxy as PUT };
