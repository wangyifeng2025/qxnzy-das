"use client";

import { Suspense } from "react";
import { useSearchParams } from "next/navigation";

import { DatasetFill } from "@/components/dataset-fill";

const DATASET_BY_TABLE: Record<string, string> = {
  staff: "ODS_JZGJBSJ",
  training: "ODS_XXJXSJ",
  award: "ODS_JSHJSJ",
  paper: "ODS_LWZZSJ",
  vertical: "ODS_KYXMJBSJ",
  horizontal: "ODS_HXKTSJ",
  practice: "ODS_JSQYJZSJSJ",
  ip: "ODS_ZSCQSJ",
  major: "ODS_ZYSZSJ",
  course: "ODS_KCJBSJ",
  teaching: "ODS_SKXXSJ",
  student: "ODS_XSJBSJ",
};

function datasetCode(table: string) {
  return DATASET_BY_TABLE[table] ?? (table.startsWith("ODS_") ? table : null);
}

function FillBody() {
  const params = useSearchParams();
  const code = datasetCode(params.get("table") || "staff");
  if (!code) {
    return <div className="p-6 text-sm text-zinc-500">该数据集尚未接入。</div>;
  }
  return <DatasetFill code={code} recordId={params.get("record")} />;
}

export default function FillPage() {
  return (
    <Suspense fallback={<div className="p-6 text-sm text-zinc-400">正在打开填报页</div>}>
      <FillBody />
    </Suspense>
  );
}
