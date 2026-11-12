/** Форматирование для русского интерфейса. Деньги приходят из API в копейках (целые). */

const rub = new Intl.NumberFormat("ru-RU", { style: "currency", currency: "RUB", maximumFractionDigits: 0 });
const rubExact = new Intl.NumberFormat("ru-RU", { style: "currency", currency: "RUB", minimumFractionDigits: 2 });
const int = new Intl.NumberFormat("ru-RU");
const pct = new Intl.NumberFormat("ru-RU", { style: "percent", minimumFractionDigits: 1, maximumFractionDigits: 1 });
const dateFmt = new Intl.DateTimeFormat("ru-RU", { day: "numeric", month: "long", year: "numeric" });
const dateTimeFmt = new Intl.DateTimeFormat("ru-RU", { dateStyle: "medium", timeStyle: "short" });

/** 1234567 коп. → «12 346 ₽» */
export const kopecksToRub = (k: number | null | undefined) => (k == null ? "—" : rub.format(k / 100));
export const kopecksToRubExact = (k: number | null | undefined) => (k == null ? "—" : rubExact.format(k / 100));
/** «20000.00» (строка рублей из протокола) → «20 000 ₽» */
export const rubString = (s: string | number | null | undefined) => (s == null ? "—" : rub.format(Number(s)));
export const num = (n: number | null | undefined) => (n == null ? "—" : int.format(n));
export const percent = (x: number | null | undefined) => (x == null || Number.isNaN(x) ? "—" : pct.format(x));
/** Процентные пункты: 0.06 → «+6,0 п.п.» */
export const pp = (x: number | null | undefined) =>
  x == null || Number.isNaN(x) ? "—" : `${x > 0 ? "+" : ""}${(x * 100).toFixed(1).replace(".", ",")} п.п.`;
export const date = (s: string | null | undefined) => (s ? dateFmt.format(new Date(s)) : "—");
export const dateTime = (s: string | null | undefined) => (s ? dateTimeFmt.format(new Date(s)) : "—");
export const bytes = (n: number) =>
  n < 1024 ? `${n} Б` : n < 1024 ** 2 ? `${(n / 1024).toFixed(1)} КБ` : `${(n / 1024 ** 2).toFixed(1)} МБ`;
