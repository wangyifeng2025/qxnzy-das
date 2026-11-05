"use client";

import {
  createPaginatedRowModel,
  createSortedRowModel,
  createTableHook,
  rowPaginationFeature,
  rowSelectionFeature,
  rowSortingFeature,
  sortFn_alphanumeric,
  sortFn_datetime,
  sortFn_text,
  tableFeatures,
  type Column,
  type ReactTable,
  type Row,
  type RowData,
} from "@tanstack/react-table";
import { ArrowDown, ArrowUp, ChevronLeft, ChevronRight, ChevronsUpDown } from "lucide-react";
import type { ReactNode } from "react";

import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { cn } from "cn";

/** 列级样式扩展：通过 column meta 控制表头/单元格的宽度与换行。 */
export type TableColumnMeta = {
  headClassName?: string;
  cellClassName?: string;
};

/**
 * 全站表格统一使用的 TanStack Table（v9）特性集合。
 * 排序、行选择、分页三类能力一次注册，各页面按需使用。
 */
export const tableAppFeatures = tableFeatures({
  rowSortingFeature,
  rowSelectionFeature,
  rowPaginationFeature,
  sortedRowModel: createSortedRowModel(),
  paginatedRowModel: createPaginatedRowModel(),
  sortFns: {
    text: sortFn_text,
    alphanumeric: sortFn_alphanumeric,
    datetime: sortFn_datetime,
  },
  columnMeta: {} as TableColumnMeta,
});

export const { createAppColumnHelper, useAppTable } = createTableHook({
  features: tableAppFeatures,
});

/** 展示全部行、不分页时使用的初始分页状态。 */
export const allRowsPagination = { pageIndex: 0, pageSize: Infinity } as const;

export type AppTable<TData extends RowData> = ReactTable<typeof tableAppFeatures, TData>;

type DataTableProps<TData extends RowData> = {
  table: AppTable<TData>;
  empty?: ReactNode;
  /** 传给 <table> 的类名，例如 table-fixed / min-w-* 。 */
  className?: string;
  /** 传给滚动容器的类名，例如 min-h-0 flex-1 overflow-auto 。 */
  containerClassName?: string;
  stickyHeader?: boolean;
  rowClassName?: (row: Row<typeof tableAppFeatures, TData>) => string;
  onRowClick?: (row: Row<typeof tableAppFeatures, TData>) => void;
};

/** 统一渲染表头、数据行与空状态的表格主体。 */
export function DataTable<TData extends RowData>({
  table,
  empty = "暂无数据",
  className,
  containerClassName,
  stickyHeader = false,
  rowClassName,
  onRowClick,
}: DataTableProps<TData>) {
  const headerGroups = table.getHeaderGroups();
  const rows = table.getRowModel().rows;
  const columnCount = headerGroups[0]?.headers.length ?? 1;

  return (
    <Table containerClassName={containerClassName} className={cn("text-left text-[12px]", className)}>
      <TableHeader className={cn("bg-zinc-50", stickyHeader && "sticky top-0 z-10")}>
        {headerGroups.map((headerGroup) => (
          <TableRow key={headerGroup.id} className="border-b border-zinc-200 hover:bg-transparent">
            {headerGroup.headers.map((header) => (
              <TableHead
                key={header.id}
                className={cn(
                  "h-auto px-3 py-2.5 text-[11px] font-medium text-zinc-500",
                  header.column.columnDef.meta?.headClassName,
                )}
              >
                {header.isPlaceholder ? null : <table.FlexRender header={header} />}
              </TableHead>
            ))}
          </TableRow>
        ))}
      </TableHeader>
      <TableBody>
        {rows.length === 0 ? (
          <TableRow className="hover:bg-transparent">
            <TableCell colSpan={columnCount} className="px-4 py-10 text-center text-[12px] text-zinc-400">
              {empty}
            </TableCell>
          </TableRow>
        ) : (
          rows.map((row) => (
            <TableRow
              key={row.id}
              data-state={row.getIsSelected() ? "selected" : undefined}
              className={cn(
                "border-b border-zinc-100 last:border-0",
                onRowClick && "cursor-pointer",
                rowClassName?.(row),
              )}
              onClick={onRowClick ? () => onRowClick(row) : undefined}
            >
              {row.getAllCells().map((cell) => (
                <TableCell
                  key={cell.id}
                  className={cn(
                    "px-3 py-2.5 text-[12px] whitespace-nowrap",
                    cell.column.columnDef.meta?.cellClassName,
                  )}
                >
                  <table.FlexRender cell={cell} />
                </TableCell>
              ))}
            </TableRow>
          ))
        )}
      </TableBody>
    </Table>
  );
}

/** 可点击排序的表头文案。 */
export function SortHeader<TData extends RowData, TValue>({
  column,
  children,
  className,
}: {
  column: Column<typeof tableAppFeatures, TData, TValue>;
  children: ReactNode;
  className?: string;
}) {
  if (!column.getCanSort()) return <span className={className}>{children}</span>;
  const sorted = column.getIsSorted();

  return (
    <button
      type="button"
      onClick={column.getToggleSortingHandler()}
      className={cn("group inline-flex items-center gap-1 whitespace-nowrap text-left", className)}
    >
      {children}
      {sorted === "asc" ? (
        <ArrowUp className="size-3 shrink-0 text-zinc-600" aria-hidden="true" />
      ) : sorted === "desc" ? (
        <ArrowDown className="size-3 shrink-0 text-zinc-600" aria-hidden="true" />
      ) : (
        <ChevronsUpDown className="size-3 shrink-0 text-zinc-300 group-hover:text-zinc-400" aria-hidden="true" />
      )}
    </button>
  );
}

function pageWindow(pageIndex: number, pageCount: number) {
  const pages = new Set<number>([0, pageCount - 1]);
  for (let index = pageIndex - 1; index <= pageIndex + 1; index += 1) {
    if (index >= 0 && index < pageCount) pages.add(index);
  }
  return [...pages].sort((left, right) => left - right);
}

/** 分页条：展示区间统计、上一页/下一页与页码。 */
export function TablePagination<TData extends RowData>({
  table,
  unit = "条",
  className,
}: {
  table: AppTable<TData>;
  unit?: string;
  className?: string;
}) {
  const { pageIndex, pageSize } = table.state.pagination;
  const pageCount = Math.max(1, table.getPageCount() || 1);
  const rowCount = table.getRowCount();
  const start = rowCount === 0 ? 0 : pageIndex * pageSize + 1;
  const end = Math.min(rowCount, (pageIndex + 1) * pageSize);
  const pages = pageWindow(pageIndex, pageCount);

  return (
    <div
      className={cn(
        "flex flex-wrap items-center justify-between gap-2 border-t border-zinc-100 px-4 py-3 text-[11px] text-zinc-400",
        className,
      )}
    >
      <p>
        共 {rowCount} {unit}
        {rowCount > 0 ? `，当前第 ${start}-${end} 条` : ""}
      </p>
      <div className="flex items-center gap-1.5">
        <button
          type="button"
          className="flex h-7 w-7 items-center justify-center rounded-md border border-zinc-200 text-zinc-500 transition hover:bg-zinc-50 disabled:opacity-40"
          onClick={() => table.previousPage()}
          disabled={!table.getCanPreviousPage()}
          aria-label="上一页"
        >
          <ChevronLeft className="size-3.5" />
        </button>
        {pages.map((page, index) => (
          <span key={page} className="flex items-center gap-1.5">
            {index > 0 && page - pages[index - 1] > 1 ? <span className="px-0.5 text-zinc-300">…</span> : null}
            <button
              type="button"
              className={cn(
                "flex h-7 min-w-7 items-center justify-center rounded-md px-2 text-[11px] transition",
                page === pageIndex
                  ? "bg-zinc-900 text-white"
                  : "border border-zinc-200 text-zinc-500 hover:bg-zinc-50",
              )}
              onClick={() => table.setPageIndex(page)}
              aria-current={page === pageIndex ? "page" : undefined}
            >
              {page + 1}
            </button>
          </span>
        ))}
        <button
          type="button"
          className="flex h-7 w-7 items-center justify-center rounded-md border border-zinc-200 text-zinc-500 transition hover:bg-zinc-50 disabled:opacity-40"
          onClick={() => table.nextPage()}
          disabled={!table.getCanNextPage()}
          aria-label="下一页"
        >
          <ChevronRight className="size-3.5" />
        </button>
      </div>
    </div>
  );
}
