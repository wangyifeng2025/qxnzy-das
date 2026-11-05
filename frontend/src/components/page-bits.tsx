export function PageIntro({
  title,
  badge,
  badgeClass = "border border-zinc-200 bg-white text-zinc-500",
  description,
  actions,
}: {
  title: string;
  badge?: string;
  badgeClass?: string;
  description: string;
  actions?: React.ReactNode;
}) {
  return (
    <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
      <div>
        <div className="flex items-center gap-2">
          <h1 className="text-[22px] font-semibold tracking-tight text-zinc-900">{title}</h1>
          {badge ? <span className={`rounded-full px-2 py-0.5 text-[10px] font-medium ${badgeClass}`}>{badge}</span> : null}
        </div>
        <p className="mt-1 text-xs text-zinc-500">{description}</p>
      </div>
      {actions ? <div className="flex flex-wrap items-center gap-2">{actions}</div> : null}
    </div>
  );
}

export function KpiCard({
  label,
  value,
  note,
  extra,
}: {
  label: string;
  value: string;
  note: string;
  extra?: React.ReactNode;
}) {
  return (
    <div className="rounded-lg border border-zinc-200 bg-white p-4 shadow-sm">
      <p className="text-[11px] font-medium text-zinc-500">{label}</p>
      <p className="mt-2 text-[26px] leading-none font-semibold tracking-tight">{value}</p>
      <div className="mt-3 flex items-center justify-between gap-2 text-[10px] text-zinc-400">
        <span>{note}</span>
        {extra}
      </div>
    </div>
  );
}

export function Panel({
  title,
  description,
  action,
  children,
  className = "",
}: {
  title: string;
  description?: string;
  action?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <section className={`overflow-hidden rounded-lg border border-zinc-200 bg-white shadow-sm ${className}`}>
      <div className="flex items-center justify-between gap-3 border-b border-zinc-100 px-4 py-3.5">
        <div>
          <h2 className="text-sm font-semibold text-zinc-900">{title}</h2>
          {description ? <p className="mt-0.5 text-[10px] text-zinc-400">{description}</p> : null}
        </div>
        {action}
      </div>
      {children}
    </section>
  );
}

export function StatusPill({ children, tone }: { children: React.ReactNode; tone: "ok" | "run" | "warn" | "bad" | "muted" }) {
  const toneClass = {
    ok: "bg-emerald-50 text-emerald-700",
    run: "bg-sky-50 text-sky-700",
    warn: "bg-amber-50 text-amber-700",
    bad: "bg-rose-50 text-rose-700",
    muted: "bg-zinc-100 text-zinc-600",
  }[tone];
  return (
    <span className={`inline-flex shrink-0 whitespace-nowrap rounded-full px-2 py-0.5 text-[10px] font-medium ${toneClass}`}>
      {children}
    </span>
  );
}

export const primaryButton =
  "inline-flex h-9 items-center gap-2 rounded-md bg-zinc-900 px-3.5 text-xs font-medium text-white shadow-sm transition hover:bg-zinc-800 disabled:cursor-not-allowed disabled:opacity-45 disabled:hover:bg-zinc-900";
export const ghostButton =
  "inline-flex h-9 items-center gap-2 rounded-md border border-zinc-200 bg-white px-3 text-xs font-medium text-zinc-700 transition hover:bg-zinc-50 disabled:cursor-not-allowed disabled:opacity-45 disabled:hover:bg-white";
export const fieldClass =
  "h-9 w-full rounded-md border border-zinc-200 bg-white px-3 text-[12px] text-zinc-800 outline-none transition focus:border-zinc-400 focus:ring-2 focus:ring-zinc-100";

/** 进度条：用于批量写入等耗时操作，value / max 为已完成与总量。 */
export function ProgressBar({
  value,
  max,
  className = "",
  label,
}: {
  value: number;
  max: number;
  className?: string;
  label?: string;
}) {
  const safeMax = max > 0 ? max : 1;
  const percent = Math.min(100, Math.max(0, Math.round((value / safeMax) * 100)));
  return (
    <div
      role="progressbar"
      aria-valuemin={0}
      aria-valuemax={safeMax}
      aria-valuenow={Math.min(value, safeMax)}
      aria-valuetext={label ?? `${percent}%`}
      className={`h-1.5 w-full overflow-hidden rounded-full bg-zinc-200 ${className}`}
    >
      <div className="h-full rounded-full bg-zinc-900 transition-[width] duration-300 ease-out" style={{ width: `${percent}%` }} />
    </div>
  );
}
