"use client";

import { useState } from "react";

import { KpiCard, PageIntro, Panel, StatusPill } from "@/components/page-bits";
import { useToast } from "@/components/toast";

const apis: string[][] = [];

const applications: string[][] = [];

const tabs = ["接口目录", "权限申请", "调用监控"] as const;

export default function OpenApiPage() {
  const toast = useToast();
  const [tab, setTab] = useState<(typeof tabs)[number]>("接口目录");
  const [auth, setAuth] = useState("全部");
  const visible = apis.filter((item) => auth === "全部" || item[2] === auth);

  return (
    <div className="mx-auto max-w-400 p-5 xl:p-6">
      <PageIntro
        title="对外数据接口"
        badge="Open API v1"
        description="按 12 张数据表开放标准查询接口，业务系统通过授权接口拉取所需数据。"
        actions={
          <button type="button" className="inline-flex h-9 items-center rounded-md bg-zinc-900 px-3.5 text-xs font-medium text-white" onClick={() => setTab("权限申请")}>
            申请数据权限
          </button>
        }
      />
      <div className="grid grid-cols-2 gap-3 xl:grid-cols-4">
        <KpiCard label="开放接口" value="0" note="尚未开放" />
        <KpiCard label="今日调用量" value="0" note="尚无调用" />
        <KpiCard label="接口成功率" value="—" note="尚无调用" />
        <KpiCard label="已授权系统" value="0" note="暂无授权" />
      </div>
      <div className="mt-4 flex gap-1">
        {tabs.map((item) => (
          <button key={item} type="button" onClick={() => setTab(item)} className={`rounded-md px-3 py-1.5 text-[12px] ${tab === item ? "bg-zinc-900 text-white" : "bg-white text-zinc-600 ring-1 ring-zinc-200"}`}>
            {item}
            {item === "权限申请" ? " · 2" : ""}
          </button>
        ))}
      </div>

      {tab === "接口目录" ? (
        <Panel className="mt-4" title="接口目录" description="默认返回 JSON · 单次最多 500 条" action={
          <select className="h-8 rounded-md border border-zinc-200 px-2 text-[12px]" value={auth} onChange={(event) => setAuth(event.target.value)}>
            <option>全部</option>
            <option>API Key + 签名</option>
            <option>OAuth 2.0</option>
          </select>
        }>
          <div className="overflow-x-auto">
            <table className="w-full min-w-190 text-left text-[12px]">
              <thead className="bg-zinc-50 text-[11px] text-zinc-500">
                <tr>
                  {["接口 / 数据表", "请求路径", "授权方式", "今日调用", "平均延迟", "操作"].map((head) => (
                    <th key={head} className="px-4 py-2.5 font-medium">{head}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {visible.map((row) => (
                  <tr key={row[1]} className="border-t border-zinc-100">
                    <td className="px-4 py-2.5 font-medium">{row[0]}</td>
                    <td className="px-4 py-2.5 font-mono text-[11px] text-zinc-500">GET {row[1]}</td>
                    <td className="px-4 py-2.5">{row[2]}</td>
                    <td className="px-4 py-2.5">{row[3]}</td>
                    <td className="px-4 py-2.5">{row[4]}</td>
                    <td className="px-4 py-2.5">
                      <button type="button" className="text-[11px] font-medium" onClick={() => toast(`已复制 ${row[1]}`)}>复制</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Panel>
      ) : null}

      {tab === "权限申请" ? (
        <Panel className="mt-4" title="数据权限申请记录" description="业务系统需按数据表申请权限">
          <ul className="divide-y divide-zinc-100">
            {applications.map((row) => (
              <li key={row[0]} className="flex flex-wrap items-center gap-3 px-4 py-3 text-[12px]">
                <div className="min-w-0 flex-1">
                  <p className="font-medium">{row[0]}</p>
                  <p className="mt-0.5 text-[11px] text-zinc-400">{row[1]} · {row[2]}</p>
                </div>
                <StatusPill tone={row[3] === "已通过" ? "ok" : row[3] === "已驳回" ? "bad" : "warn"}>{row[3]}</StatusPill>
                {row[3] === "待审批" ? (
                  <button type="button" className="text-[11px] font-medium" onClick={() => toast(`已通过 ${row[0]} 的数据权限申请`)}>审批</button>
                ) : null}
              </li>
            ))}
          </ul>
        </Panel>
      ) : null}

      {tab === "调用监控" ? (
        <div className="mt-4 grid gap-4 lg:grid-cols-2">
          <Panel title="消费系统排行" description="今日">
            <ul className="divide-y divide-zinc-100 text-[12px]">
              {[["智慧校园门户", "5,820"], ["学生一站式服务平台", "4,386"], ["科研管理系统", "3,102"], ["教学质量监控平台", "2,648"], ["招生数据看板", "1,486"]].map(([name, count]) => (
                <li key={name} className="flex justify-between px-4 py-3"><span>{name}</span><span className="text-zinc-500">{count}</span></li>
              ))}
            </ul>
          </Panel>
          <Panel title="最近请求异常" description="成功率 99.87%">
            <ul className="divide-y divide-zinc-100 text-[12px]">
              {[["429", "/open/v1/students", "学生一站式服务平台 · QPS 超限"], ["401", "/open/v1/teacher-papers", "科研管理系统 · 签名已过期"], ["429", "/open/v1/teaching", "教学质量监控平台 · QPS 超限"]].map((row) => (
                <li key={row[1] + row[0]} className="px-4 py-3">
                  <p className="font-medium">{row[0]} {row[1]}</p>
                  <p className="mt-0.5 text-[11px] text-zinc-400">{row[2]}</p>
                </li>
              ))}
            </ul>
          </Panel>
        </div>
      ) : null}
    </div>
  );
}
