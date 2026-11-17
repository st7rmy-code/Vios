import { NextResponse, type NextRequest } from "next/server";

/** Без cookie сессии страницы приложения открывают вход с ?next=. */
export function middleware(req: NextRequest) {
  if (!req.cookies.get("sverka_token")) {
    const url = req.nextUrl.clone();
    url.pathname = "/login";
    url.search = `?next=${encodeURIComponent(req.nextUrl.pathname + req.nextUrl.search)}`;
    return NextResponse.redirect(url);
  }
  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!login|session|api|_next|templates|favicon).*)"],
};
