"use client";

import { CircleAlert, CircleCheck, Info } from "lucide-react";
import { createContext, useCallback, useContext, useMemo, useRef, useState } from "react";

export type ToastTone = "success" | "error" | "info";
type ShowToast = (message: string, tone?: ToastTone) => void;

const ToastContext = createContext<ShowToast>(() => {});

export function useToast() {
  return useContext(ToastContext);
}

const TONE = {
  success: { icon: CircleCheck, iconClass: "text-emerald-400", duration: 2400 },
  error: { icon: CircleAlert, iconClass: "text-rose-400", duration: 6000 },
  info: { icon: Info, iconClass: "text-sky-400", duration: 3200 },
} as const;

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<{ message: string; tone: ToastTone; key: number } | null>(null);
  const seq = useRef(0);

  const show = useCallback<ShowToast>((message, tone = "success") => {
    seq.current += 1;
    const key = seq.current;
    setState({ message, tone, key });
    window.setTimeout(() => {
      setState((current) => (current?.key === key ? null : current));
    }, TONE[tone].duration);
  }, []);

  const value = useMemo(() => show, [show]);
  const tone = state?.tone ?? "success";
  const Icon = TONE[tone].icon;
  const isError = tone === "error";

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div
        role={isError ? "alert" : "status"}
        aria-live={isError ? "assertive" : "polite"}
        className={`pointer-events-none fixed bottom-8 left-1/2 z-[100] flex max-w-[min(90vw,42rem)] -translate-x-1/2 items-start gap-2 rounded-lg px-4 py-2.5 text-left text-xs leading-relaxed font-medium text-white shadow-xl transition ${
          isError ? "bg-rose-950 ring-1 ring-rose-500/40" : "bg-zinc-900"
        } ${state ? "translate-y-0 opacity-100" : "translate-y-3 opacity-0"}`}
      >
        <Icon className={`mt-px size-3.5 shrink-0 ${TONE[tone].iconClass}`} aria-hidden="true" />
        <span>{state?.message ?? "操作成功"}</span>
      </div>
    </ToastContext.Provider>
  );
}
