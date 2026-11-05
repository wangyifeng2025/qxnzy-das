import { Check } from "lucide-react";

export type StepKey = "parse" | "plan" | "review" | "done";

export const STEPS: { key: StepKey; label: string }[] = [
  { key: "parse", label: "解析文件" },
  { key: "plan", label: "核对结构" },
  { key: "review", label: "核对候选" },
  { key: "done", label: "完成" },
];

/**
 * 分步条：current 是任务实际所处的步骤，viewing 是正在查看的步骤。
 * 已经走过的步骤可以点回去查看，还没到的步骤不可点击。
 */
export function StepBar({
  current,
  viewing,
  skipped,
  onSelect,
}: {
  current: StepKey;
  viewing: StepKey;
  skipped: StepKey[];
  onSelect: (step: StepKey) => void;
}) {
  const reached = STEPS.findIndex((step) => step.key === current);
  return (
    <ol className="flex items-center gap-1 text-[12px]">
      {STEPS.map((step, index) => {
        const passed = index < reached;
        const active = step.key === viewing;
        const isSkipped = skipped.includes(step.key);
        const available = index <= reached && !isSkipped;
        return (
          <li key={step.key} className="flex min-w-0 items-center gap-1">
            {index > 0 ? (
              <span className={`h-px w-4 shrink-0 sm:w-8 ${index <= reached ? "bg-zinc-400" : "bg-zinc-200"}`} aria-hidden="true" />
            ) : null}
            <button
              type="button"
              disabled={!available}
              aria-current={active ? "step" : undefined}
              onClick={() => onSelect(step.key)}
              className={`flex min-w-0 items-center gap-1.5 rounded-md px-2 py-1 transition ${
                active
                  ? "bg-zinc-900 text-white"
                  : available
                    ? "text-zinc-700 hover:bg-zinc-100"
                    : "cursor-default text-zinc-300"
              }`}
            >
              <span
                className={`flex size-4 shrink-0 items-center justify-center rounded-full text-[10px] tabular-nums ${
                  active
                    ? "bg-white text-zinc-900"
                    : passed && !isSkipped
                      ? "bg-zinc-800 text-white"
                      : available
                        ? "border border-zinc-400 text-zinc-600"
                        : "border border-zinc-200 text-zinc-300"
                }`}
              >
                {passed && !isSkipped && !active ? <Check className="size-2.5" strokeWidth={3} /> : index + 1}
              </span>
              <span className="truncate">
                {step.label}
                {isSkipped ? <span className="ml-1 text-[10px] text-zinc-400">已跳过</span> : null}
              </span>
            </button>
          </li>
        );
      })}
    </ol>
  );
}
