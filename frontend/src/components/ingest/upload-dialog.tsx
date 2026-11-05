"use client";

import { Upload, X } from "lucide-react";

import { primaryButton } from "@/components/page-bits";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import type { DatasetAccess } from "@/lib/session";

export function UploadDialog({
  open,
  onOpenChange,
  datasets,
  datasetCode,
  onDatasetChange,
  prompt,
  onPromptChange,
  freshPlan,
  onFreshPlanChange,
  files,
  onFilesChange,
  canAppend,
  appendToBatch,
  onAppendChange,
  busy,
  onSubmit,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  datasets: DatasetAccess[];
  datasetCode: string;
  onDatasetChange: (code: string) => void;
  prompt: string;
  onPromptChange: (value: string) => void;
  freshPlan: boolean;
  onFreshPlanChange: (value: boolean) => void;
  files: File[];
  onFilesChange: (files: File[]) => void;
  canAppend: boolean;
  appendToBatch: boolean;
  onAppendChange: (value: boolean) => void;
  busy: boolean;
  onSubmit: () => void;
}) {
  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!busy) onOpenChange(next);
      }}
    >
      <DialogContent
        showCloseButton={false}
        overlayClassName="bg-zinc-900/40"
        className="flex w-full max-w-[calc(100%-2rem)] flex-col gap-0 overflow-hidden bg-white p-0 text-zinc-900 ring-zinc-200 sm:max-w-lg"
      >
        <DialogHeader className="shrink-0 flex-row items-start justify-between gap-3 space-y-0 border-b border-zinc-100 px-5 py-3.5">
          <div>
            <DialogTitle className="text-[14px] font-semibold tracking-tight text-zinc-900">新建解析</DialogTitle>
            <DialogDescription className="mt-0.5 text-[11px] text-zinc-500">
              系统只生成候选记录，核对确认后才会写入草稿。
            </DialogDescription>
          </div>
          <button
            type="button"
            className="flex size-7 shrink-0 items-center justify-center rounded-md text-zinc-400 transition hover:bg-zinc-100 hover:text-zinc-600 disabled:opacity-40"
            onClick={() => onOpenChange(false)}
            disabled={busy}
            aria-label="关闭"
          >
            <X className="size-3.5" />
          </button>
        </DialogHeader>
        <div className="space-y-3.5 px-5 py-4 text-[12px]">
          <label className="block">
            <span className="text-zinc-600">导入到哪张数据表</span>
            <select
              className="mt-1 h-9 w-full rounded-md border border-zinc-200 bg-white px-2"
              value={datasetCode}
              onChange={(event) => onDatasetChange(event.target.value)}
            >
              {datasets.length === 0 ? <option value="">没有可填报的数据表</option> : null}
              {datasets.map((item) => (
                <option key={item.code} value={item.code}>
                  {item.name}
                </option>
              ))}
            </select>
          </label>
          <label className="flex min-h-28 cursor-pointer flex-col items-center justify-center gap-1.5 rounded-lg border border-dashed border-zinc-300 px-3 py-4 text-center text-[12px] text-zinc-500 transition hover:border-zinc-400 hover:bg-zinc-50/60 focus-within:border-zinc-500">
            <Upload className="size-5 text-zinc-400" aria-hidden="true" />
            {files.length > 0 ? (
              <span className="break-all text-zinc-800">
                {files.length === 1 ? files[0].name : `已选择 ${files.length} 个文件`}
                {files.length > 1 ? <span className="mt-1 block text-[11px] text-sky-600">将创建批次，逐份解析</span> : null}
                <span className="mt-1 block text-[11px] text-zinc-400">点击可重新选择</span>
              </span>
            ) : (
              <span>
                点击选择文件
                <span className="mt-1 block text-[11px] text-zinc-400">xlsx、xls、csv、docx、pdf，单个最大 20MB，可多选</span>
              </span>
            )}
            <input
              type="file"
              className="sr-only"
              multiple
              accept=".xlsx,.xls,.csv,.docx,.pdf"
              onChange={(event) => onFilesChange(Array.from(event.target.files ?? []))}
            />
          </label>
          <label className="block">
            <span className="text-zinc-600">补充说明</span>
            <span className="ml-1.5 text-[11px] text-zinc-400">可选，用于缩小提取范围或说明判重规则</span>
            <textarea
              className="mt-1 h-20 w-full resize-none rounded-md border border-zinc-200 px-2 py-1.5"
              maxLength={500}
              value={prompt}
              placeholder="例如：只提取本系教师；课程号和专业名称相同的视为重复"
              onChange={(event) => onPromptChange(event.target.value)}
            />
            {prompt.trim() ? (
              <span className="mt-1 block text-[11px] text-amber-600">
                填写补充说明后会调用模型重新识别结构，不使用已记住的结构。
              </span>
            ) : null}
          </label>
          <label className="flex items-start gap-1.5 text-[12px] text-zinc-600">
            <input
              type="checkbox"
              className="mt-0.5"
              checked={freshPlan || Boolean(prompt.trim())}
              disabled={Boolean(prompt.trim())}
              onChange={(event) => onFreshPlanChange(event.target.checked)}
            />
            <span>
              不使用已记住的结构，重新识别
              <span className="block text-[11px] text-zinc-400">同样表头的文件以前确认过结构时，默认直接套用。</span>
            </span>
          </label>
          {canAppend ? (
            <label className="flex items-center gap-1.5 text-[12px] text-zinc-600">
              <input type="checkbox" checked={appendToBatch} onChange={(event) => onAppendChange(event.target.checked)} />
              追加到当前批次，按业务主键合并补充数据
            </label>
          ) : null}
        </div>
        <DialogFooter className="mx-0 mb-0 shrink-0 flex-row justify-end gap-2 border-t border-zinc-100 bg-white px-5 py-3">
          <button
            type="button"
            className="h-9 rounded-md border border-zinc-200 bg-white px-3 text-xs font-medium text-zinc-700 transition hover:bg-zinc-50 disabled:opacity-45"
            disabled={busy}
            onClick={() => onOpenChange(false)}
          >
            取消
          </button>
          <button
            type="button"
            className={primaryButton}
            disabled={busy || files.length === 0 || !datasetCode}
            onClick={onSubmit}
          >
            {busy ? <span className="size-3 animate-spin rounded-full border-2 border-white/40 border-t-white" aria-hidden="true" /> : null}
            {busy ? "正在上传" : "开始解析"}
          </button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
