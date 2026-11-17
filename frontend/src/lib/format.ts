/** Форматирование для русского интерфейса. Деньги приходят из API в копейках (целые). */

const rub = new Intl.NumberFormat("ru-RU", { style: "currency", currency: "RUB", maximumFractionDigits: 0 });
const rubExact = new Intl.NumberFormat("ru-RU", { style: "currency", currency: "RUB", minimumFractionDigits: 2 });
const int = new Intl.NumberFormat("ru-RU");
const pct = new Intl.NumberFormat("ru-RU", { style: "percent", minimumFractionDigits: 1, maximumFractionDigits: 1 });
const dateFmt = new Intl.DateTimeFormat("ru-RU", { day: "2-digit", month: "2-digit", year: "numeric" });
const dateTimeFmt = new Intl.DateTimeFormat("ru-RU", {
  day: "2-digit",
  month: "2-digit",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
});

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
/** «2026-11-12» или ISO-время → «12.11.2026». Дата без времени не сдвигается часовым поясом. */
export const date = (s: string | null | undefined) =>
  s ? (/^\d{4}-\d{2}-\d{2}$/.test(s) ? s.split("-").reverse().join(".") : dateFmt.format(new Date(s))) : "—";
/** Прибавить дни к «ГГГГ-ММ-ДД». */
export const addDays = (iso: string, days: number) => {
  const d = new Date(`${iso}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
};
/** Сегодня в формате «ГГГГ-ММ-ДД» по часам браузера. */
export const todayIso = () => {
  const d = new Date();
  return new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 10);
};
/** Диапазон процентных пунктов без знака точки: «3,1–8,9 п.п.» */
export const ppRange = (lo: number | null | undefined, hi: number | null | undefined) =>
  lo == null || hi == null ? "—" : `${fmt1(lo * 100)}–${fmt1(hi * 100)} п.п.`;
const fmt1 = (x: number) => x.toFixed(1).replace(".", ",").replace("-", "−");
export const dateTime = (s: string | null | undefined) => (s ? dateTimeFmt.format(new Date(s)) : "—");
export const bytes = (n: number) =>
  n < 1024 ? `${n} Б` : n < 1024 ** 2 ? `${(n / 1024).toFixed(1)} КБ` : `${(n / 1024 ** 2).toFixed(1)} МБ`;
