from __future__ import annotations

from copy import deepcopy
from typing import Any


STANDARD_PANEL_STYLES: dict[str, dict[str, Any]] = {
    "default": {
        "title_color": "#333333",
        "header_background_color": "grey",
        "header_vertical_align": "center",
        "icon_token": "down-small-ccm_outlined",
        "icon_color": "#9AA0A6",
        "icon_size": "16px 16px",
        "icon_position": "right",
        "icon_expanded_angle": -180,
        "border_color": "grey",
        "corner_radius": "5px",
        "padding": "8px 8px 8px 8px",
    },
    "danger": {
        "title_color": "#CF1322",
    },
}


def plain_text(template: str) -> dict[str, Any]:
    return {"type": "plain_text", "template": template}


def markdown(template: str) -> dict[str, Any]:
    return {"type": "markdown", "template": template}


def divider() -> dict[str, Any]:
    return {"type": "divider"}


def facts(title: str, items: list[dict[str, Any]]) -> dict[str, Any]:
    return {"type": "facts", "title": title, "items": items}


def list_block(
    title: str,
    path: str,
    *,
    max_items: int | None = None,
    empty_text: str | None = None,
    show_title: bool | None = None,
) -> dict[str, Any]:
    block: dict[str, Any] = {
        "type": "list",
        "title": title,
        "path": path,
        "item_template": "{item}",
    }
    if max_items:
        block["max_items"] = max_items
    if empty_text:
        block["empty_text"] = empty_text
    if show_title is not None:
        block["show_title"] = show_title
    return block


def record_list(
    title: str,
    path: str,
    title_template: str,
    lines: list[str],
    *,
    max_items: int | None = None,
    children_field: str | None = None,
    child_title_template: str | None = None,
    child_lines: list[str] | None = None,
    max_children: int | None = None,
    show_title: bool | None = None,
) -> dict[str, Any]:
    block: dict[str, Any] = {
        "type": "record_list",
        "title": title,
        "path": path,
        "title_template": title_template,
        "lines": lines,
    }
    if max_items:
        block["max_items"] = max_items
    if children_field:
        block["children_field"] = children_field
    if child_title_template:
        block["child_title_template"] = child_title_template
    if child_lines:
        block["child_lines"] = child_lines
    if max_children:
        block["max_children"] = max_children
    if show_title is not None:
        block["show_title"] = show_title
    return block


def note(template: str) -> dict[str, Any]:
    return {"type": "note", "template": template}


def collapsible_panel(
    title: str,
    blocks: list[dict[str, Any]],
    *,
    expanded: bool = False,
    style: str = "default",
    empty_text: str | None = None,
) -> dict[str, Any]:
    panel: dict[str, Any] = {
        "type": "collapsible_panel",
        "title": title,
        "expanded": expanded,
        "style": style,
        "blocks": blocks,
    }
    if empty_text:
        panel["empty_text"] = empty_text
    return panel


def collapsible_record_panels(
    path: str,
    panel_title_template: str,
    lines: list[str],
    *,
    max_items: int | None = None,
    children_field: str | None = None,
    child_title_template: str | None = None,
    child_lines: list[str] | None = None,
    max_children: int | None = None,
    expanded_first: bool = False,
    expanded_all: bool = False,
    style: str = "default",
    empty_text: str | None = None,
    blocks: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    panel: dict[str, Any] = {
        "type": "collapsible_record_panels",
        "path": path,
        "panel_title_template": panel_title_template,
        "lines": lines,
        "expanded_first": expanded_first,
        "expanded_all": expanded_all,
        "style": style,
    }
    if max_items:
        panel["max_items"] = max_items
    if children_field:
        panel["children_field"] = children_field
    if child_title_template:
        panel["child_title_template"] = child_title_template
    if child_lines:
        panel["child_lines"] = child_lines
    if max_children:
        panel["max_children"] = max_children
    if empty_text:
        panel["empty_text"] = empty_text
    if blocks:
        panel["blocks"] = blocks
    return panel


def _layout_presentation(
    structure: str,
    blocks: list[dict[str, Any]],
    *,
    schema: str = "1.0",
    styles: dict[str, Any] | None = None,
) -> dict[str, Any]:
    presentation: dict[str, Any] = {
        "schema": schema,
        "structure": structure,
        "blocks": blocks,
    }
    if styles:
        presentation["styles"] = styles
    return presentation


def generic_presentation(blocks: list[dict[str, Any]]) -> dict[str, Any]:
    return _layout_presentation("generic", blocks)


def collapsible_list_presentation(blocks: list[dict[str, Any]]) -> dict[str, Any]:
    return _layout_presentation("collapsible-list", blocks, schema="2.0", styles={"panels": deepcopy(STANDARD_PANEL_STYLES)})


def grouped_panels_presentation(blocks: list[dict[str, Any]]) -> dict[str, Any]:
    return _layout_presentation("grouped-panels", blocks, schema="2.0", styles={"panels": deepcopy(STANDARD_PANEL_STYLES)})


def panel_report_presentation(blocks: list[dict[str, Any]]) -> dict[str, Any]:
    return _layout_presentation("panel-report", blocks, schema="2.0", styles={"panels": deepcopy(STANDARD_PANEL_STYLES)})


def hotspot_presentation() -> dict[str, Any]:
    return generic_presentation([
            markdown("✅ **{title}**\n本轮已整理 {count} 条候选项。"),
            facts("执行信息", [
                {"label": "时间", "path": "timestamp"},
                {"label": "下次检查", "path": "next_check"},
            ]),
            divider(),
            record_list("候选项", "items", "{emoji} **{title}**", [
                "评分：{score}",
                "{description}",
                "平台：{platform}",
            ], max_items=8),
            note("归档文件：{archive_target_path}"),
        ])


def simple_sections_presentation() -> dict[str, Any]:
    return generic_presentation([
            markdown("✅ **{title}**\n{summary}"),
            facts("执行信息", [{"label": "时间", "path": "timestamp"}]),
            divider(),
            record_list("内容分区", "sections", "**{title}**", ["{lines}"]),
            note("归档文件：{archive_target_path}"),
        ])


def system_status_presentation() -> dict[str, Any]:
    return generic_presentation([
            markdown("✅ **{title}**\n整体状态：{overall_status} | 健康分：{health_score}"),
            facts("核心指标", [
                {"label": "时间", "path": "timestamp"},
                {"label": "磁盘", "path": "host.disk.used_percent"},
                {"label": "内存", "path": "host.memory.used_percent"},
                {"label": "Gateway", "path": "gateway.overall"},
                {"label": "Docker 运行中", "path": "docker.running"},
                {"label": "Cron 异常", "path": "cron.abnormal_jobs"},
            ]),
            divider(),
            list_block("重点发现", "top_findings", max_items=6),
            divider(),
            list_block("建议动作", "actions", max_items=6),
        ])


def jike_reply_monitor_presentation() -> dict[str, Any]:
    return generic_presentation([
            markdown("✅ **{title}**\n本轮检查 {checked} 条通知，发现 {new_comments} 条新评论。"),
            facts("执行信息", [
                {"label": "时间", "path": "timestamp"},
                {"label": "已回复", "template": "{replied_count} 条"},
            ]),
            divider(),
            list_block("本轮已回复", "replied", max_items=10, empty_text="本轮无新增回复。"),
        ])


def domain_health_presentation() -> dict[str, Any]:
    return collapsible_list_presentation([
            plain_text("{summary}"),
            plain_text("{timestamp}"),
            divider(),
            collapsible_panel(
                "SSL 状态（{ssl_items_count}）",
                [
                    record_list("", "ssl_items", "<font color='#1890FF'>• **{domain}**</font>", [
                        "状态：{status}",
                        "到期时间：{expires_at}",
                        "剩余天数：{days_left}",
                    ], max_items=10, show_title=False)
                ],
                expanded=True,
            ),
            collapsible_panel(
                "网站可用性（{site_items_count}）",
                [
                    record_list("", "site_items", "<font color='#1890FF'>• **{domain}**</font>", [
                        "状态：{status}",
                        "{detail}",
                    ], max_items=10, show_title=False)
                ],
                expanded=False,
            ),
            divider(),
            plain_text("下次检查：{next_check}"),
        ])


def skill_distribution_presentation() -> dict[str, Any]:
    return generic_presentation([
            markdown("✅ **{title}**\n本次已完成 Skill 分发。"),
            facts("分发结果", [
                {"label": "时间", "path": "timestamp"},
                {"label": "Skill", "path": "skill_name"},
                {"label": "来源 Agent", "path": "source"},
                {"label": "目标 Agent", "path": "target_agent"},
                {"label": "匹配度", "template": "{match_score}%"},
                {"label": "原因", "path": "reason"},
            ]),
        ])


def skill_report_presentation(*, include_trials: bool = False, include_next_steps: bool = False, include_doc_meta: bool = False) -> dict[str, Any]:
    blocks: list[dict[str, Any]] = [
        markdown("✅ **{title}**\n本轮共整理 {skills_count} 个候选 Skill。"),
        facts("统计信息", [
            {"label": "时间", "path": "timestamp"},
            {"label": "已测试", "path": "stats.tested"},
            {"label": "已采纳", "path": "stats.adopted"},
            {"label": "待处理", "path": "stats.pending"},
            {"label": "新发现", "path": "stats.newSkills"},
        ]),
        divider(),
        record_list("候选 Skill", "skills", "**{name}**", [
            "{tagline}",
            "来源：{source}",
            "状态：{status}",
            "Stars：{stars}",
            "仓库：{repo_url}",
        ], children_field="highlights", child_title_template="{item}", max_items=8, max_children=4),
        divider(),
        list_block("建议动作", "recommendations", max_items=6, empty_text="本轮暂无建议动作。"),
    ]
    if include_next_steps:
        blocks.extend([divider(), list_block("下一步", "nextSteps", max_items=6)])
    if include_trials:
        blocks.extend([
            divider(),
            record_list("试用计划", "skills", "**{name}**", [
                "试用状态：{trial_status}",
                "测试目标：{trial_target}",
                "执行方式：{trial_flow}",
                "验收标准：{acceptance}",
                "安装位置：{install_path}",
            ], max_items=8),
        ])
    if include_doc_meta:
        blocks.extend([
            divider(),
            facts("知识库定位", [
                {"label": "文档标题", "path": "doc_title"},
                {"label": "文档链接", "path": "doc_url"},
                {"label": "Wiki 分区", "path": "wiki_section"},
            ]),
        ])
    return generic_presentation(blocks)


def jike_publish_presentation() -> dict[str, Any]:
    return generic_presentation([
            markdown("✅ **{title}**\n已完成即刻发布与记录整理。"),
            facts("发布信息", [
                {"label": "发布时间", "path": "published_at"},
                {"label": "主题", "path": "topic"},
                {"label": "来源", "path": "topic_source"},
                {"label": "评分", "path": "score"},
                {"label": "字数", "path": "word_count"},
                {"label": "图片", "path": "image_status"},
            ]),
            divider(),
            markdown("> {excerpt}"),
            divider(),
            list_block("亮点", "highlights", max_items=6, empty_text="本轮未记录额外亮点。"),
            note("链接：{link}"),
        ])


def daily_diary_presentation() -> dict[str, Any]:
    return grouped_panels_presentation([
        plain_text("{summary}"),
        plain_text("{date} | {timestamp}"),
        plain_text("{coverage_note}"),
        divider(),
        collapsible_record_panels(
            "agent_sections",
            "🤖 {agent}（{status} | 任务 {task_count}）",
            [],
            blocks=[
                record_list("", "highlights", "<font color='#1890FF'>• **{title}**</font>", ["{desc}"], max_items=4, show_title=False),
            ],
            max_items=6,
            expanded_first=True,
        ),
        divider(),
        collapsible_panel(
            "✅ 今日完成（{completed_count}）",
            [list_block("", "completed", max_items=8, show_title=False, empty_text="今天没有记录完成项。")],
            expanded=True,
        ),
        collapsible_panel(
            "🔍 核心发现（{highlights_count}）",
            [list_block("", "highlights", max_items=8, show_title=False, empty_text="今天没有额外发现。")],
            expanded=False,
        ),
        collapsible_panel(
            "⚠️ 问题记录（{issues_count}）",
            [list_block("", "issues", max_items=8, show_title=False, empty_text="今天没有记录问题。")],
            expanded=False,
        ),
        collapsible_panel(
            "⏳ 待跟进（{pending_count}）",
            [list_block("", "pending", max_items=8, show_title=False, empty_text="当前没有待跟进项。")],
            expanded=False,
        ),
        collapsible_panel(
            "🎯 明日计划（{tomorrow_plan_count}）",
            [list_block("", "tomorrow_plan", max_items=8, show_title=False, empty_text="尚未写入明日计划。")],
            expanded=False,
        ),
        collapsible_panel(
            "🚨 异常项（{exceptions_count}）",
            [
                record_list("", "exceptions", "<font color='#CF1322'>• **{agent} / {task}**</font>", [
                    "状态：{status}",
                    "{error}",
                ], max_items=8, show_title=False)
            ],
            expanded=False,
            style="danger",
        ),
        divider(),
        plain_text("日记文件：{diary_file}"),
    ])


def daily_knowledge_presentation() -> dict[str, Any]:
    return collapsible_list_presentation([
        plain_text("{summary}"),
        plain_text("{report_date} | {timestamp}"),
        divider(),
        collapsible_panel(
            "✅ 执行步骤（{execution_steps_count}）",
            [
                record_list("", "execution_steps", "<font color='#1890FF'>• **{name}**</font>", [
                    "文件：`{file}`",
                    "{detail}",
                ], max_items=8, show_title=False)
            ],
            expanded=True,
        ),
        collapsible_panel(
            "📌 完成任务（{completed_tasks_count}）",
            [list_block("", "completed_tasks", max_items=8, show_title=False, empty_text="本轮未记录完成任务。")],
            expanded=False,
        ),
        collapsible_panel(
            "🚨 新增选题（{new_topics_count}）",
            [list_block("", "new_topics", max_items=8, show_title=False, empty_text="本轮没有新增选题。")],
            expanded=False,
        ),
        collapsible_panel(
            "💡 关键洞察（{insights_count}）",
            [list_block("", "insights", max_items=8, show_title=False, empty_text="本轮没有新增洞察。")],
            expanded=False,
        ),
        collapsible_panel(
            "⚠️ 学到教训（{lessons_count}）",
            [list_block("", "lessons", max_items=8, show_title=False, empty_text="本轮没有新增教训。")],
            expanded=False,
            style="danger",
        ),
        collapsible_panel(
            "🗂️ 更新文件（{updated_files_count}）",
            [record_list("", "updated_files", "`{path}`", ["{note}"], max_items=8, show_title=False)],
            expanded=False,
        ),
        divider(),
        plain_text("整理时间：{organized_at}"),
    ])


def best_practices_presentation() -> dict[str, Any]:
    return grouped_panels_presentation([
        plain_text("今日概览：活跃 agent {active_agents_count} 个 | 匹配场景 {total_scenarios} 个 | 推送 {recommendations_count} 个推荐组"),
        plain_text("生成时间：{timestamp}"),
        plain_text("活跃 Agent：{active_agents}"),
        divider(),
        collapsible_record_panels(
            "recommendations",
            "🤖 {agent}（{scenarios_count} 个推荐）",
            [],
            blocks=[
                record_list("", "scenarios", "<font color='#1890FF'>• **{name}** `#{score}`</font>", [
                    "{description}",
                    "收益：{benefit}",
                    "来源：{source}",
                ], max_items=6, show_title=False)
            ],
            max_items=8,
            expanded_first=True,
        ),
        collapsible_panel(
            "🌐 通用场景（{universal_scenarios_count}）",
            [
                record_list("", "universal_scenarios", "<font color='#1890FF'>• **{name}**</font>", [
                    "{description}",
                    "收益：{benefit}",
                ], max_items=8, show_title=False)
            ],
            expanded=False,
        ),
        collapsible_panel(
            "📈 本周统计",
            [
                facts("", [
                    {"label": "覆盖 Agent", "path": "weekly_stats.agents_covered"},
                    {"label": "累计推送", "path": "weekly_stats.scenarios_sent"},
                    {"label": "平均得分", "path": "weekly_stats.avg_score"},
                    {"label": "覆盖率", "path": "weekly_stats.coverage_rate"},
                ])
            ],
            expanded=False,
        ),
        divider(),
        plain_text("执行者：进化官"),
    ])


def self_upgrade_presentation() -> dict[str, Any]:
    return panel_report_presentation([
        plain_text("观察窗口：{scan_window} | 来源 Skill：{source_skill} | 建议数：{total_suggestions}"),
        plain_text("优先级分布：P0 {stats.p0} / P1 {stats.p1} / P2 {stats.p2}"),
        markdown("**本轮摘要**\n{summary}"),
        divider(),
        collapsible_record_panels(
            "suggestions",
            "{priority} · {title}",
            [
                "📝 **建议**：{summary}",
                "🔍 **原因**：{rationale}",
                "📎 **证据**：{evidence}",
                "落点：{target_path} | 动作：{action_type} | 风险：{risk} | 收益：{expected_benefit}",
            ],
            max_items=6,
            expanded_first=True,
        ),
        collapsible_panel(
            "➡️ 下一步（{next_actions_count} 条）",
            [list_block("", "next_actions", max_items=6, show_title=False, empty_text="本轮未提供下一步动作。")],
            expanded=False,
        ),
        divider(),
        plain_text("生成时间：{timestamp} | 来源：{source_skill}"),
    ])


def cron_diagnosis_presentation() -> dict[str, Any]:
    return panel_report_presentation([
        plain_text("诊断窗口：{report_window} | 检查任务：{stats.checked_jobs} | 异常任务：{stats.abnormal_jobs}"),
        plain_text("关键统计：失败 {stats.failed_jobs} / 延迟 {stats.delayed_jobs}"),
        markdown("**本轮结论**\n{summary}"),
        divider(),
        collapsible_panel(
            "📌 主要发现（{major_findings_count}）",
            [
                record_list("", "major_findings", "<font color='#CF1322'>• **[{severity}] {title}**</font>", [
                    "{summary}",
                    "任务：{job_name}",
                ], max_items=6, show_title=False)
            ],
            expanded=True,
            style="danger",
        ),
        collapsible_record_panels(
            "jobs",
            "{name}（{status}）",
            [
                "🤖 **执行 Agent**：{agent}",
                "⏰ **调度**：{schedule}",
                "📍 **状态**：{status}",
                "📝 **摘要**：{summary}",
                "🕒 **最近执行**：{last_run}",
            ],
            blocks=[
                list_block("", "findings", max_items=4, show_title=False),
                list_block("", "suggestions", max_items=3, show_title=False),
            ],
            max_items=6,
            expanded_first=True,
        ),
        collapsible_panel(
            "➡️ 建议动作（{recommendations_count}）",
            [list_block("", "recommendations", max_items=8, show_title=False, empty_text="本轮未生成额外建议。")],
            expanded=False,
        ),
        divider(),
        plain_text("生成时间：{timestamp} | 诊断窗口：{report_window}"),
    ])


def skill_knowledge_presentation() -> dict[str, Any]:
    return generic_presentation([
            markdown("✅ **{title}**\n已完成知识库写入。"),
            facts("知识库定位", [
                {"label": "时间", "path": "timestamp"},
                {"label": "动作", "path": "action"},
                {"label": "分类", "template": "{category_emoji} {category}"},
                {"label": "Wiki 分区", "path": "wiki_section"},
                {"label": "文档标题", "path": "doc_title"},
                {"label": "文档链接", "path": "doc_url"},
            ]),
            divider(),
            record_list("已写入 Skill", "skills_written", "**{name}**", [
                "{tagline}",
                "来源：{source}",
                "Stars：{stars}",
                "仓库：{github_url}",
            ], children_field="highlights", child_title_template="{item}", max_items=8, max_children=4),
        ])


def twitter_monitor_presentation() -> dict[str, Any]:
    return generic_presentation([
            markdown("✅ **{title}**\n{summary}"),
            facts("执行信息", [
                {"label": "时间", "path": "timestamp"},
                {"label": "总推文数", "path": "total_tweets"},
            ]),
            divider(),
            list_block("重点动态", "highlights", max_items=8, empty_text="本轮没有单独提炼 highlights。"),
            divider(),
            record_list("分类汇总", "categories", "**{name}**", [
                "数量：{count}",
                "{summary_cn}",
            ], children_field="items", child_title_template="{headline_cn}", child_lines=[
                "{detail_cn}",
                "账号：{source_accounts}",
            ], max_items=6, max_children=4),
        ])


def producthunt_presentation() -> dict[str, Any]:
    return generic_presentation([
            markdown("✅ **{title}**\nProduct Hunt 榜单已完成扫描。"),
            facts("执行信息", [{"label": "日期", "path": "date"}]),
            divider(),
            record_list("榜单 Top 产品", "products", "**#{rank} {name}**", [
                "{tagline}",
                "点赞：{votes}",
                "评论：{comments}",
                "链接：{url}",
            ], max_items=5),
        ])


def vercel_monitor_presentation() -> dict[str, Any]:
    return generic_presentation([
            markdown("✅ **{title}**\n已完成 Vercel 项目状态检查。"),
            facts("项目状态", [
                {"label": "时间", "path": "timestamp"},
                {"label": "项目", "path": "project_name"},
                {"label": "域名", "path": "domain"},
                {"label": "框架", "path": "framework"},
                {"label": "函数", "path": "functions"},
            ]),
        ])


TEMPLATE_PRESENTATIONS: dict[str, dict[str, Any]] = {
    "ai-hotspot": hotspot_presentation(),
    "topic-research-report": hotspot_presentation(),
    "competitor-trend-report": hotspot_presentation(),
    "weekly-jike-plan-report": hotspot_presentation(),
    "system-status": system_status_presentation(),
    "jike-reply-monitor": jike_reply_monitor_presentation(),
    "domain-health": domain_health_presentation(),
    "skill-distribution": skill_distribution_presentation(),
    "skill-report": skill_report_presentation(),
    "skill-simple-report": skill_report_presentation(include_doc_meta=True),
    "skill-trial-report": skill_report_presentation(include_trials=True),
    "skill-hourly-report": skill_report_presentation(include_next_steps=True),
    "skill-discovery-report": skill_report_presentation(include_next_steps=True),
    "jike-publish-report": jike_publish_presentation(),
    "daily-diary": daily_diary_presentation(),
    "daily-knowledge": daily_knowledge_presentation(),
    "openclaw-best-practices": best_practices_presentation(),
    "self-upgrade-suggestion-report": self_upgrade_presentation(),
    "cron-diagnosis-report": cron_diagnosis_presentation(),
    "skill-knowledge-report": skill_knowledge_presentation(),
    "openclaw-twitter-monitor": twitter_monitor_presentation(),
    "producthunt": producthunt_presentation(),
    "vercel-monitor": vercel_monitor_presentation(),
    "daily-task": simple_sections_presentation(),
}


SCAFFOLD_LAYOUTS: dict[str, dict[str, Any]] = {
    "generic": simple_sections_presentation(),
    "collapsible-list": daily_knowledge_presentation(),
    "grouped-panels": daily_diary_presentation(),
    "panel-report": cron_diagnosis_presentation(),
    "distribution-summary": skill_distribution_presentation(),
    "items-report": hotspot_presentation(),
    "sections-report": simple_sections_presentation(),
    "system-status": system_status_presentation(),
    "knowledge-digest": daily_knowledge_presentation(),
    "daily-diary": daily_diary_presentation(),
    "diagnosis-report": cron_diagnosis_presentation(),
    "distribution-report": skill_distribution_presentation(),
}


def get_scaffold_layout(name: str) -> dict[str, Any]:
    layout = SCAFFOLD_LAYOUTS.get(name)
    if not layout:
        raise ValueError(f"未知 layout: {name}")
    return deepcopy(layout)


def materialize_template_registry(
    registry: dict[str, Any],
    *,
    overwrite_blocks: bool = False,
    drop_renderer: bool = False,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    templates = registry.get("templates", registry)
    if not isinstance(templates, dict):
        raise ValueError("模板注册表必须包含 templates 对象")

    updated = deepcopy(registry)
    target_templates = updated.get("templates", updated)
    changes: list[dict[str, Any]] = []

    for template_name, template_config in list(target_templates.items()):
        if not isinstance(template_config, dict):
            continue
        preset = TEMPLATE_PRESENTATIONS.get(template_name)
        if not preset:
            continue

        presentation = deepcopy(template_config.get("presentation") or {})
        route = deepcopy(template_config.get("route") or {})
        transport = deepcopy(route.get("transport") or {})
        has_blocks = isinstance(presentation.get("blocks"), list) and bool(presentation.get("blocks"))
        missing_metadata = any(key != "blocks" and key not in presentation for key in preset)
        transport_changed = False
        if not transport.get("provider"):
            transport["provider"] = "feishu"
            transport_changed = True
        target_agents = template_config.get("target_agents") or []
        if not transport.get("account") and isinstance(target_agents, list) and len(target_agents) == 1 and target_agents[0]:
            transport["account"] = str(target_agents[0]).strip()
            transport_changed = True

        if has_blocks and not overwrite_blocks and not drop_renderer and not transport_changed and not missing_metadata:
            continue

        change: dict[str, Any] = {"template": template_name}
        if overwrite_blocks or not has_blocks:
            presentation["blocks"] = deepcopy(preset["blocks"])
            change["blocks"] = "updated"
        if missing_metadata:
            change["metadata"] = "updated"
        if transport_changed:
            route["transport"] = transport
            target_templates[template_name]["route"] = route
            change["transport"] = "updated"
        if drop_renderer and "renderer" in template_config:
            target_templates[template_name].pop("renderer", None)
            change["renderer"] = "removed"

        for key, value in preset.items():
            if key == "blocks":
                continue
            presentation.setdefault(key, deepcopy(value))

        if change.keys() != {"template"}:
            target_templates[template_name]["presentation"] = presentation
            changes.append(change)

    return updated, changes
