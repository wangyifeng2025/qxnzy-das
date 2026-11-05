# 任务：为每个工作表生成结构计划

输入是若干工作表画像（sheets）和若干目标数据表（targets）。请判断：

- 哪些工作表是数据表（role=main），分别对应哪个 dataset_code；
- 哪些是字典表、说明页或与目标无关的表（role=reference 或 ignore）；
- 表头在第几行、数据从第几行开始到第几行结束；
- 每一列对应哪个标准字段，或者应忽略；
- 续行分组、横表转置、多表拼接、跨表关联。

## 输出格式

```json
{
  "sheets": [
    {
      "sheet": "工作表名（必须与输入一致）",
      "role": "main",
      "dataset_code": "目标数据表代码",
      "header_rows": [2, 3],
      "data_start": 4,
      "data_end": null,
      "header_pattern": "normal",
      "columns": [
        {"header": "专业名称*", "field": "ZYMC", "transform": "direct", "confidence": 1}
      ],
      "row_mode": "grouped",
      "group_key": ["ZYDM"],
      "multi_value_fields": ["ZYJYXLMC"],
      "dedupe_by": [],
      "reason": "一句话说明判断依据"
    }
  ],
  "merge_sheets": [["1月表", "2月表"]],
  "joins": [],
  "confidence": 0.9
}
```

## 规则

1. `header_rows` 是表头所在行；两行表头写 `[2, 3]`。`data_start` 必须是第一行真实数据。
2. `data_end` 为 `null` 表示到文件末尾，程序会自动去掉空行和“合计/制表”脚注。
3. 数据行下方是合计、说明、签字等内容的，必须用 `data_end` 排除。
4. 续行：一行的业务主键列为空、但补全了上一行的多值列时，用 `row_mode="grouped"`，`group_key` 写业务主键字段，`multi_value_fields` 写需要累加的字段。
5. 横表：第一列是字段名、右侧每列是一条记录时，用 `header_pattern="columnar"`。
6. 多张结构相同的表要合并时，放入 `merge_sheets`，第一张为主表。
7. 一张表里包含多个数据集的行、或需要从参考表补字段时，可以给出 `joins`，格式为 `{"reference_sheet": "...", "main_sheet": "...", "on": ["字段"], "fill": ["字段"]}`。注意跨表关联只能在同一个文件内进行。参考表（role=reference）的 `dataset_code` 填它所补充的主表数据集，列映射也用主表的字段代码。
8. `transform` 只能是 `direct`、`split_date_range`、`split_name_id`、`concat_date`、`repeat_group`、`narrative`。
   - `split_date_range` / `split_name_id` 需要 `fields` 给出两个目标字段；
   - `concat_date` 需要 `headers` 给出多个列，格式为 `{"header": null, "headers": ["年","月","日"], "field": "日期字段"}`；
   - `repeat_group` 需要 `group` 整数，同组列会展开成多条记录；
   - 整列是自由描述、需要模型再抽取时才用 `narrative`。
9. 表头里明确没有对应标准字段的列，保留 `{"header": "...", "transform": "direct"}` 但不要给 `field`。
10. `row_mode` 只能是 `single`（一行一条记录，默认）、`grouped`、`repeat`；`header_pattern` 只能是 `normal` 或 `columnar`。两者不要混用。
11. `dedupe_by` 默认留空（按数据集业务主键判重）。只有用户补充要求明确说明“哪些字段相同视为重复/合并为一条”时，才把这些字段的代码按顺序写进主表的 `dedupe_by`，字段必须属于该数据集。
12. 无法确认结构时，`confidence` 给低分，并在 `reason` 中说明，后端会转人工确认。
