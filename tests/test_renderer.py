import json
from pathlib import Path

from openclaw_feishu_cron_kit.presentation_presets import load_template_presentations, materialize_template_registry
from openclaw_feishu_cron_kit.renderer import build_generic_card, build_summary_post, build_summary_text


_TEMPLATES_FILE = Path(__file__).resolve().parents[1] / "runtime" / "feishu-templates.local.json"
_PRESENTATIONS = load_template_presentations(_TEMPLATES_FILE)


def _get_presentation(name: str) -> dict:
    p = _PRESENTATIONS.get(name)
    if not p:
        raise KeyError(f"Template presentation '{name}' not found in {_TEMPLATES_FILE}")
    return p


def test_build_summary_post_wraps_post_payload_for_feishu_reply_api() -> None:
    payload = build_summary_post(
        "固定话题",
        {
            "notice": "本轮已完成",
            "bullets": ["第一条", "第二条"],
            "footer": "详情见上一条完整卡片。",
            "mention_open_ids": ["ou_demo"],
        },
    )

    assert "post" in payload
    assert "zh_cn" in payload["post"]
    assert payload["post"]["zh_cn"]["title"] == "固定话题 · 最新摘要"

    content = payload["post"]["zh_cn"]["content"]
    assert content[0][0] == {"tag": "at", "user_id": "ou_demo"}
    assert content[0][-1] == {"tag": "text", "text": "本轮已完成"}
    assert content[1] == [{"tag": "text", "text": "【摘要】"}]
    assert content[2] == [{"tag": "text", "text": "- 第一条"}]
    assert content[3] == [{"tag": "text", "text": "- 第二条"}]
    assert content[4] == [{"tag": "text", "text": "详情见上一条完整卡片。"}]


def test_build_summary_text_formats_fallback_reply() -> None:
    payload = build_summary_text(
        {
            "notice": "本轮已完成",
            "bullets": ["第一条", "第二条"],
            "footer": "详情见上一条完整卡片。",
            "mention_open_ids": ["ou_demo"],
        }
    )

    assert payload == {
        "text": '<at user_id="ou_demo"></at>\n本轮已完成\n【摘要】\n- 第一条\n- 第二条\n详情见上一条完整卡片。'
    }


def test_build_generic_card_renders_presentation_blocks_for_daily_knowledge() -> None:
    template_config = {
        "description": "每日知识整理",
        "header_template": "blue",
        "presentation": _get_presentation("daily-knowledge"),
    }
    data = {
        "title": "每日知识整理任务完成",
        "summary": "✅ 完成！已整理昨天工作记录。",
        "report_date": "2026-03-17",
        "organized_at": "2026-03-18 02:00",
        "timestamp": "2026-03-18 02:00",
        "important_events": ["事件 A", "事件 B"],
        "execution_steps": [
            {"name": "读取昨天记忆", "status": "ok", "file": "memory/2026-03-17.md", "detail": "提炼关键洞察"}
        ],
        "completed_tasks": ["完成任务 A"],
        "new_topics": ["新主题 A（SCORE 23/25）"],
        "insights": ["洞察 A"],
        "lessons": ["教训 A"],
        "updated_files": [{"path": "/tmp/demo.md", "note": "补充整理结果"}],
    }

    card = build_generic_card("daily-knowledge", template_config, data)

    assert card["schema"] == "2.0"
    assert card["header"]["title"]["content"] == "每日知识整理任务完成"
    body_elements = card["body"]["elements"]
    assert body_elements[0]["text"]["content"] == "✅ 完成！已整理昨天工作记录。"
    assert body_elements[1]["text"]["content"] == "2026-03-17 | 2026-03-18 02:00"

    panels = [element for element in body_elements if element.get("tag") == "collapsible_panel"]
    assert len(panels) >= 5
    assert panels[0]["header"]["title"]["content"] == "**<font color='#333333'>✅ 执行步骤（1）</font>**"
    assert "读取昨天记忆" in panels[0]["elements"][0]["content"]
    assert any("💡 关键洞察" in panel["header"]["title"]["content"] for panel in panels)
    assert any("洞察 A" in element["content"] for panel in panels for element in panel["elements"])


def test_build_generic_card_renders_dynamic_collapsible_panels_for_best_practices() -> None:
    template_config = {
        "description": "最佳实践",
        "header_template": "blue",
        "presentation": _get_presentation("openclaw-best-practices") if "openclaw-best-practices" in _PRESENTATIONS else _get_presentation("daily-knowledge"),
    }
    if "openclaw-best-practices" not in _PRESENTATIONS:
        return

    data = {
        "title": "OpenClaw 每日最佳实践推送",
        "timestamp": "2026-03-18 10:00",
        "active_agents": ["blogger", "product"],
        "total_scenarios": 5,
        "recommendations": [
            {"agent": "blogger", "scenarios": [{"name": "热点整理", "score": 92, "description": "自动整理", "benefit": "提升效率", "source": "memory"}]},
            {"agent": "product", "scenarios": [{"name": "竞品跟踪", "score": 88, "description": "持续跟踪", "benefit": "减少漏看", "source": "cron"}]},
        ],
        "universal_scenarios": [{"name": "日报归档", "description": "统一沉淀", "benefit": "便于复盘"}],
        "weekly_stats": {"agents_covered": 6, "scenarios_sent": 18, "avg_score": 87, "coverage_rate": "75%"},
    }

    card = build_generic_card("openclaw-best-practices", template_config, data)

    assert card["schema"] == "2.0"
    panels = [element for element in card["body"]["elements"] if element.get("tag") == "collapsible_panel"]
    assert panels[0]["header"]["title"]["content"] == "**<font color='#333333'>🤖 blogger（1 个推荐）</font>**"
    assert panels[0]["expanded"] is True
    assert "热点整理" in panels[0]["elements"][0]["content"]
    assert any("🌐 通用场景" in panel["header"]["title"]["content"] for panel in panels)
    assert any("📈 本周统计" in panel["header"]["title"]["content"] for panel in panels)


def test_build_generic_card_renders_daily_task_sections_from_project_template() -> None:
    template_config = {
        "description": "今日任务清单",
        "header_template": "blue",
        "presentation": _get_presentation("daily-diary") if "daily-task" not in _PRESENTATIONS else _get_presentation("daily-task"),
    }
    if "daily-task" not in _PRESENTATIONS:
        return

    data = {
        "title": "超级峰今日任务",
        "summary": "今天共有 3 个重点任务。",
        "date": "3月18日",
        "weekday": "周三",
        "timestamp": "2026-03-18 08:00",
        "p0_tasks": [{"task": "修复模板链路", "note": "先完成链路迁移", "url": "https://example.com/p0"}],
        "p1_tasks": [{"task": "整理发布说明", "note": "更新 README", "url": ""}],
    }

    card = build_generic_card("daily-task", template_config, data)

    assert card["config"]["wide_screen_mode"] is True
    assert card["header"]["title"]["content"] == "超级峰今日任务"
    elements = card["elements"]
    markdown_blocks = [
        element["text"]["content"]
        for element in elements
        if element.get("tag") == "div" and element.get("text", {}).get("tag") == "lark_md"
    ]
    assert all(element.get("tag") != "collapsible_panel" for element in elements)
    assert markdown_blocks[0] == "✅ **今日任务速览**\n今天共有 3 个重点任务。"
    assert markdown_blocks[1] == "**执行信息**\n- **日期**：3月18日\n- **星期**：周三\n- **时间**：2026-03-18 08:00"
    assert "**🔥 P0 任务（1）**" in markdown_blocks
    assert "• 修复模板链路\n先完成链路迁移\nhttps://example.com/p0" in markdown_blocks
    assert "**🧩 P1 任务（1）**" in markdown_blocks
    assert "• 整理发布说明\n更新 README" in markdown_blocks
    assert elements[-1]["text"]["content"] == "💡 有新任务？直接告诉小峰「添加任务：xxx」"


def test_build_generic_card_renders_website_analytics_daily_tables() -> None:
    template_config = {
        "description": "网站产品数据简报",
        "header_template": "blue",
        "presentation": _get_presentation("website-analytics-daily"),
    }
    data = {
        "product_key": "ainativehub",
        "product_name": "AI Native Hub",
        "domain": "https://ainativehub.com",
        "report_date": "2026-03-20",
        "headline": "AI Native Hub 每日数据简报",
        "traffic_source_title": "Google Analytics 4",
        "search_source_title": "Google Search Console / 百度搜索资源平台",
        "quality_source_title": "Google Analytics 4 / Microsoft Clarity",
        "traffic_metrics": [
            {
                "metric_name_display": "活跃用户数（UV）",
                "value_display": "8",
                "change_display": "+60.00%",
                "source_display": "Google Analytics 4",
                "metric_description": "当天访问网站的去重用户数，反映整体流量盘子。",
            }
        ],
        "search_metrics": [
            {
                "metric_name_display": "搜索点击量",
                "value_display": "0",
                "change_display": "无对比数据",
                "source_display": "Google Search Console",
                "metric_description": "用户在自然搜索结果中点击网站的次数。",
            }
        ],
        "quality_metrics": [
            {
                "metric_name_display": "注册转化率",
                "value_display": "3.25%",
                "change_display": "+12.00%",
                "source_display": "Google Analytics 4",
                "metric_description": "注册量除以会话数，反映流量转化效率。",
            }
        ],
        "channel_top_rows": [
            {
                "channel_display": "自然搜索",
                "sessions_display": "12",
                "share_display": "60.00%",
                "engagement_rate_display": "52.40%",
                "source_display": "Google Analytics 4",
                "channel_description": "来自搜索引擎自然结果的访问。",
            }
        ],
        "alerts": [],
        "insights": ["当前最高流量页面是 /，会话数 8。"],
        "source_explanations": [
            "流量规模：当前来自 Google Analytics 4（活跃用户数（UV）、会话数）。",
            "搜索获取：当前来自 Google Search Console（搜索点击量）。",
        ],
        "thread_summary": {"notice": "done", "bullets": ["a"]},
    }

    card = build_generic_card("website-analytics-daily", template_config, data)

    assert card["schema"] == "2.0"
    assert card["config"]["width_mode"] == "fill"
    assert card["header"]["title"]["content"] == "📈 AI Native Hub 数据简报 · 2026-03-20"
    body_elements = card["body"]["elements"]
    assert body_elements[0]["text"]["content"] == "AI Native Hub 每日数据简报"
    assert body_elements[1]["text"]["content"] == "报告日期：2026-03-20 | 域名：https://ainativehub.com"
    assert body_elements[3]["text"]["content"] == "**📊 流量概览（Google Analytics 4）**"

    tables = [element for element in body_elements if element.get("tag") == "table"]
    assert len(tables) >= 4
    assert tables[0]["element_id"] == "traffic_tbl"
    assert tables[0]["columns"][0]["name"] == "metric_name_display"
    assert tables[0]["columns"][3]["name"] == "source_display"
    assert tables[0]["rows"][0]["metric_name_display"] == "活跃用户数（UV）"
    assert tables[1]["element_id"] == "search_tbl"
    assert body_elements[5]["text"]["content"] == "**🔎 搜索获取（Google Search Console / 百度搜索资源平台）**"
    assert tables[1]["rows"][0]["metric_description"] == "用户在自然搜索结果中点击网站的次数。"
    assert tables[2]["element_id"] == "quality_tbl"
    assert body_elements[7]["text"]["content"] == "**🎯 参与与转化（Google Analytics 4 / Microsoft Clarity）**"
    assert tables[2]["rows"][0]["metric_name_display"] == "注册转化率"
    assert tables[3]["element_id"] == "channel_tbl"
    assert tables[3]["rows"][0]["channel_display"] == "自然搜索"
    assert tables[3]["rows"][0]["share_display"] == "60.00%"
    assert tables[3]["rows"][0]["source_display"] == "Google Analytics 4"

    assert any(
        element.get("tag") == "div" and element.get("text", {}).get("content") == "本轮没有新增风险提醒。"
        for element in body_elements
    )
    assert any(
        element.get("tag") == "div" and element.get("text", {}).get("content") == "当前最高流量页面是 /，会话数 8。"
        for element in body_elements
    )
    assert any(
        element.get("tag") == "div" and element.get("text", {}).get("content") == "流量规模：当前来自 Google Analytics 4（活跃用户数（UV）、会话数）。"
        for element in body_elements
    )


def test_build_generic_card_renders_table_empty_state_without_note_tag_for_schema_v2() -> None:
    template_config = {
        "description": "网站产品数据简报",
        "header_template": "blue",
        "presentation": _get_presentation("website-analytics-daily"),
    }
    data = {
        "product_key": "ainativehub",
        "product_name": "AI Native Hub",
        "domain": "https://ainativehub.com",
        "report_date": "2026-03-20",
        "headline": "AI Native Hub 每日数据简报",
        "traffic_source_title": "待补来源",
        "search_source_title": "待补来源",
        "quality_source_title": "待补来源",
        "traffic_metrics": [],
        "search_metrics": [],
        "quality_metrics": [],
        "channel_top_rows": [],
        "alerts": [],
        "insights": [],
        "source_explanations": [],
        "thread_summary": {"notice": "done", "bullets": ["a"]},
    }

    card = build_generic_card("website-analytics-daily", template_config, data)

    body_elements = card["body"]["elements"]
    assert not any(element.get("tag") == "note" for element in body_elements)
    assert any(
        element.get("tag") == "div" and element.get("text", {}).get("content") == "当前没有可展示的渠道表现数据。"
        for element in body_elements
    )


def test_materialize_template_registry_handles_transport_setup() -> None:
    registry = {
        "templates": {
            "daily-knowledge": {
                "description": "每日知识整理",
                "renderer": "daily_knowledge",
                "presentation": {
                    "header_title_template": "📚 每日知识整理 · {report_date}",
                    "schema": "2.0",
                    "structure": "collapsible-list",
                    "blocks": [{"type": "plain_text", "template": "{summary}"}],
                },
            }
        }
    }

    updated, changes = materialize_template_registry(registry, drop_renderer=True)

    template = updated["templates"]["daily-knowledge"]
    assert "renderer" not in template
    assert template["presentation"]["header_title_template"] == "📚 每日知识整理 · {report_date}"
    assert template["presentation"]["schema"] == "2.0"
    assert template["presentation"]["blocks"][0]["type"] == "plain_text"
    assert template["route"]["transport"] == {"provider": "feishu"}
