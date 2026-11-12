/** Интервал с нулём: видно, пересекает ли доверительный интервал ноль. */
export function Interval({
  lo,
  hi,
  point,
  format,
}: {
  lo: number | null;
  hi: number | null;
  point: number;
  format: (x: number) => string;
}) {
  if (lo == null || hi == null) return <p className="text-sm text-muted-foreground">Интервал не считался.</p>;
  const span = Math.max(Math.abs(lo), Math.abs(hi), Math.abs(point)) * 1.15 || 1;
  const pos = (x: number) => `${((x + span) / (2 * span)) * 100}%`;
  const color = lo > 0 ? "bg-success" : hi < 0 ? "bg-destructive" : "bg-muted-foreground";
  return (
    <div className="space-y-1">
      <div className="relative h-8" role="img" aria-label={`от ${format(lo)} до ${format(hi)}`}>
        <div className="absolute top-1/2 h-px w-full bg-border" />
        <div className="absolute top-0 h-full w-px bg-foreground/60" style={{ left: "50%" }} />
        <div className={`absolute top-1/2 h-2 -translate-y-1/2 rounded-full ${color}`} style={{ left: pos(lo), width: `calc(${pos(hi)} - ${pos(lo)})` }} />
        <div className="absolute top-1/2 h-4 w-1 -translate-x-1/2 -translate-y-1/2 rounded bg-foreground" style={{ left: pos(point) }} />
      </div>
      <div className="relative h-4 text-xs tabular-nums text-muted-foreground">
        <span className="absolute -translate-x-1/2" style={{ left: "50%" }}>0</span>
      </div>
      <p className="text-xs text-muted-foreground">
        95% интервал: от {format(lo)} до {format(hi)}
      </p>
    </div>
  );
}
