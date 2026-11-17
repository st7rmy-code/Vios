/** Только для серверного кода Next: адрес FastAPI и имя cookie с токеном. */
export const BACKEND_URL = process.env.SVERKA_BACKEND_URL ?? "http://localhost:8000";
export const TOKEN_COOKIE = "sverka_token";

const SAFE_METHODS = new Set(["GET", "HEAD", "OPTIONS"]);

/**
 * Защита от CSRF для cookie-сессии: изменяющий запрос принимаем, только если он пришёл
 * со страницы этого же сайта. SameSite=Lax не спасает от соседнего поддомена.
 */
export function isSameOriginMutation(req: Request): boolean {
  if (SAFE_METHODS.has(req.method)) return true;
  const origin = req.headers.get("origin");
  if (!origin) return req.headers.get("sec-fetch-site") === "same-origin";
  const host = req.headers.get("x-forwarded-host") ?? req.headers.get("host");
  try {
    return new URL(origin).host === host;
  } catch {
    return false;
  }
}

export const forbidden = () =>
  Response.json({ detail: "Запрос с чужого сайта отклонён", code: "csrf_rejected" }, { status: 403 });
