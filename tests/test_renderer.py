from openclaw_feishu_cron_kit.presentation_presets import TEMPLATE_PRESENTATIONS, materialize_template_registry
from openclaw_feishu_cron_kit.renderer import build_generic_card, build_summary_post, build_summary_text


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
        "presentation": TEMPLATE_PRESENTATIONS["daily-knowledge"],
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
        "presentation": TEMPLATE_PRESENTATIONS["openclaw-best-practices"],
    }
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


def test_build_generic_card_renders_daily_task_panels_from_project_template() -> None:
    template_config = {
        "description": "今日任务清单",
        "header_template": "blue",
        "presentation": TEMPLATE_PRESENTATIONS["daily-task"],
    }
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

    assert card["schema"] == "2.0"
    assert card["header"]["title"]["content"] == "超级峰今日任务"
    panels = [element for element in card["body"]["elements"] if element.get("tag") == "collapsible_panel"]
    assert len(panels) == 2
    assert panels[0]["header"]["title"]["content"] == "**<font color='#CF1322'>🔥 P0 任务（1）</font>**"
    assert panels[0]["expanded"] is True
    assert "修复模板链路" in panels[0]["elements"][0]["content"]
    assert panels[1]["header"]["title"]["content"] == "**<font color='#333333'>🧩 P1 任务（1）</font>**"


def test_materialize_template_registry_replaces_renderer_with_blocks() -> None:
    registry = {
        "templates": {
            "daily-knowledge": {
                "description": "每日知识整理",
                "renderer": "daily_knowledge",
                "presentation": {"header_title_template": "📚 每日知识整理 · {report_date}"},
            }
        }
    }

    updated, changes = materialize_template_registry(registry, drop_renderer=True)

    template = updated["templates"]["daily-knowledge"]
    assert changes == [{"template": "daily-knowledge", "blocks": "updated", "metadata": "updated", "transport": "updated", "renderer": "removed"}]
    assert "renderer" not in template
    assert template["presentation"]["header_title_template"] == "📚 每日知识整理 · {report_date}"
    assert template["presentation"]["schema"] == "2.0"
    assert template["presentation"]["structure"] == "collapsible-list"
    assert template["presentation"]["styles"]["panels"]["default"]["title_color"] == "#333333"
    assert template["presentation"]["blocks"][0]["type"] == "plain_text"
    assert template["route"]["transport"] == {"provider": "feishu"}
