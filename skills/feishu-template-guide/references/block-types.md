# Block Types Reference

所有 `presentation.blocks` 支持的 block 类型及其 JSON 结构。

## divider

水平分割线。

```json
{ "type": "divider" }
```

## plain_text

纯文本，支持 `{field}` 占位符。

```json
{ "type": "plain_text", "template": "{summary}" }
```

支持嵌套路径：`{stats.checked_jobs}`、`{host.disk.used_percent}`。

## markdown

Markdown 文本，支持加粗、链接、代码等。

```json
{ "type": "markdown", "template": "**{title}**\n{summary}" }
```

## facts

键值对列表，适合展示元数据。

```json
{
  "type": "facts",
  "title": "执行信息",
  "items": [
    { "label": "时间", "path": "timestamp" },
    { "label": "健康分", "template": "{health_score}%" },
    { "label": "磁盘", "path": "host.disk.used_percent" }
  ]
}
```

每个 item：
- `label` — 左侧标签
- `path` — 直接从 data 取值（支持嵌套路径）
- `template` — 模板字符串（与 path 二选一）

## list

简单列表，每项为字符串。

```json
{
  "type": "list",
  "title": "建议动作",
  "path": "actions",
  "item_template": "{item}",
  "max_items": 8,
  "empty_text": "暂无。",
  "show_title": true
}
```

- `path` — data 中的数组字段名
- `item_template` — 每项的渲染模板，`{item}` 表示数组元素本身
- `max_items` — 最大显示条数
- `empty_text` — 数组为空时的提示
- `show_title` — 是否显示标题（默认 true）

## record_list

结构化列表，每项为 dict，支持多行展示。

```json
{
  "type": "record_list",
  "title": "候选项",
  "path": "items",
  "title_template": "{emoji} **{title}**",
  "lines": [
    "评分：{score}",
    "{description}",
    "平台：{platform}"
  ],
  "max_items": 8,
  "empty_text": "暂无候选项。",
  "ordered": false,
  "show_title": true
}
```

- `title_template` — 每条记录的标题行
- `lines` — 每条记录的详情行（数组），也可用 `detail_templates` 作为别名
- `ordered` — 是否显示序号

### 嵌套子列表

```json
{
  "type": "record_list",
  "path": "recommendations",
  "title_template": "🤖 {agent}（{scenarios_count} 个场景）",
  "lines": [],
  "children_field": "scenarios",
  "child_title_template": "• {name}（{score}分）",
  "child_lines": ["{description}", "收益：{benefit}"],
  "max_children": 5
}
```

## table

表格，飞书卡片限制**每张卡片最多 4 个 table**。

```json
{
  "type": "table",
  "path": "jobs",
  "columns": [
    { "name": "name", "display_name": "名称", "data_type": "text" },
    { "name": "status", "display_name": "状态", "data_type": "options" },
    { "name": "count", "display_name": "数量", "data_type": "number" }
  ],
  "page_size": 10,
  "empty_text": "暂无数据"
}
```

- `path` — 行数据数组路径
- `columns[].data_type` — `text`、`number`、`options`、`date`、`lark_md`、`markdown`
- 超过 4 个 table 时，改用 `record_list` 替代

## note

备注块，通常放在卡片底部。

```json
{ "type": "note", "template": "{archive_note}" }
```

## collapsible_panel

折叠面板（需要 `schema: "2.0"`）。

```json
{
  "type": "collapsible_panel",
  "title": "📌 完成任务（{completed_tasks_count}）",
  "expanded": false,
  "style": "default",
  "empty_text": "暂无内容",
  "blocks": [
    {
      "type": "list",
      "path": "completed_tasks",
      "item_template": "{item}",
      "max_items": 8,
      "show_title": false
    }
  ]
}
```

- `expanded` — 默认是否展开
- `style` — 对应 `presentation.styles.panels` 中的样式名
- `blocks` — 面板内的子 block 列表
- 不支持嵌套（面板内不能再放面板）

### styles 配置示例

```json
{
  "styles": {
    "panels": {
      "default": {
        "title_color": "#333333",
        "header_background_color": "grey",
        "border_color": "grey",
        "corner_radius": "5px",
        "padding": "8px 8px 8px 8px",
        "icon_token": "down-small-ccm_outlined",
        "icon_color": "#9AA0A6",
        "icon_size": "16px 16px",
        "icon_position": "right",
        "icon_expanded_angle": -180
      },
      "danger": {
        "title_color": "#CF1322"
      }
    }
  }
}
```

## collapsible_record_panels

按数据记录动态生成多个折叠面板（需要 `schema: "2.0"`）。

```json
{
  "type": "collapsible_record_panels",
  "path": "agent_sections",
  "panel_title_template": "🤖 {agent}（{status} | 任务 {task_count}）",
  "lines": [
    "状态：{status}",
    "任务数：{task_count}"
  ],
  "expanded_first": true,
  "expanded_all": false,
  "style": "default",
  "max_items": 6,
  "blocks": [
    {
      "type": "record_list",
      "path": "highlights",
      "title_template": "• **{title}**",
      "lines": ["{desc}"],
      "max_items": 4,
      "show_title": false
    }
  ]
}
```

- `path` — 记录数组路径
- `panel_title_template` — 每个面板的标题
- `expanded_first` — 只展开第一个
- `blocks` — 每个面板内部的 block（作用域为当前记录）

## 占位符语法

所有 `template`、`title_template`、`lines` 中的 `{field}` 会从 payload data 中取值：

- `{title}` — 顶层字段
- `{stats.checked_jobs}` — 嵌套路径
- `{item}` — 在 list block 中表示当前数组元素
- `{count}` 后缀 — 自动计算数组长度，如 data 中有 `items` 数组，`{items_count}` 自动可用
