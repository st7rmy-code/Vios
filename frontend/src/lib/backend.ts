/** Только для серверного кода Next: адрес FastAPI и имя cookie с токеном. */
export const BACKEND_URL = process.env.SVERKA_BACKEND_URL ?? "http://localhost:8000";
export const TOKEN_COOKIE = "sverka_token";
