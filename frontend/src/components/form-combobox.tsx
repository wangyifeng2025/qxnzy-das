"use client";

import { useState } from "react";

import {
  Combobox,
  ComboboxContent,
  ComboboxEmpty,
  ComboboxInput,
  ComboboxItem,
  ComboboxList,
} from "@/components/ui/combobox";

export type FormComboboxOption = {
  value: string;
  label: string;
};

type FormComboboxProps = {
  options: FormComboboxOption[];
  value?: string;
  defaultValue?: string;
  onValueChange?: (value: string) => void;
  name?: string;
  placeholder?: string;
  disabled?: boolean;
  id?: string;
};

export function FormCombobox({
  options,
  value,
  defaultValue = "",
  onValueChange,
  name,
  placeholder = "请选择",
  disabled = false,
  id,
}: FormComboboxProps) {
  const [uncontrolled, setUncontrolled] = useState(defaultValue);
  const selected = value ?? uncontrolled;
  const selectedItem = options.find((item) => item.value === selected) ?? null;

  return (
    <>
      {name ? <input type="hidden" name={name} value={selected} /> : null}
      <Combobox
        items={options}
        value={selectedItem}
        onValueChange={(next) => {
          const text = next?.value ?? "";
          if (value === undefined) setUncontrolled(text);
          onValueChange?.(text);
        }}
        disabled={disabled}
        isItemEqualToValue={(left, right) => left.value === right.value}
      >
        <ComboboxInput
          id={id}
          placeholder={placeholder}
          disabled={disabled}
          showClear={false}
          className="h-9 w-full rounded-md border-zinc-200 bg-white text-[12px] text-zinc-800 shadow-none has-[[data-slot=input-group-control]:focus-visible]:border-zinc-400 has-[[data-slot=input-group-control]:focus-visible]:ring-2 has-[[data-slot=input-group-control]:focus-visible]:ring-zinc-200/80 [&_svg]:text-zinc-400"
        />
        <ComboboxContent className="z-[80] min-w-(--anchor-width) rounded-md border border-zinc-200 bg-white text-zinc-800 shadow-sm ring-0">
          <ComboboxEmpty className="text-[12px] text-zinc-400">没有匹配项</ComboboxEmpty>
          <ComboboxList>
            {(item: FormComboboxOption) => (
              <ComboboxItem
                key={item.value || item.label}
                value={item}
                className="rounded-sm py-1.5 text-[12px] text-zinc-700 data-highlighted:bg-zinc-100 data-highlighted:text-zinc-900 not-data-[variant=destructive]:data-highlighted:**:text-zinc-500"
              >
                {item.label}
              </ComboboxItem>
            )}
          </ComboboxList>
        </ComboboxContent>
      </Combobox>
    </>
  );
}
