"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { readSession, ROLE_HOME } from "@/lib/session";

export default function IndexPage() {
  const router = useRouter();

  useEffect(() => {
    const session = readSession();
    router.replace(session ? ROLE_HOME[session.role] : "/login");
  }, [router]);

  return <div className="grid h-screen place-items-center bg-[#f7f7f8] text-sm text-zinc-400">正在进入系统</div>;
}
