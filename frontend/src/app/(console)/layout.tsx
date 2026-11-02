import { ConsoleShell } from "@/components/console-shell";

export const instant = { unstable_disableValidation: true };

export default function ConsoleLayout({ children }: { children: React.ReactNode }) {
  return <ConsoleShell>{children}</ConsoleShell>;
}
