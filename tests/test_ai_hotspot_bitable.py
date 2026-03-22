from __future__ import annotations

from openclaw_feishu_cron_kit.ai_hotspot_bitable import build_topic_uid, derive_topic_phrase, select_upsert_target
from openclaw_feishu_cron_kit.template_normalizers import normalize_template_data


def test_normalize_ai_hotspot_payload_hides_success_claim_when_bitable_not_confirmed() -> None:
    payload = normalize_template_data(
        "ai-hotspot",
        {
            "title": "AI 热点扫描",
            "archive_target_path": "https://chaojifeng.feishu.cn/base/demo",
            "items": [
                {
                    "title": "Claude Code Channels发布",
                    "score": 25,
                    "platforms": ["即刻", "公众号"],
                    "core_points": "支持 Telegram/Discord 异步协作",
                    "x_confirm_status": "降级确认（site:x.com / site:twitter.com）",
                }
            ],
            "thread_summary": {
                "notice": "AI 热点扫描已完成",
                "bullets": ["新增高分选题：1 个", "已写入飞书多维表格"],
            },
            "execution_meta": {"bitable_write_status": "failed"},
        },
    )

    assert payload["summary"] == "本轮已整理 1 条候选项。"
    assert payload["items"][0]["platform"] == "即刻、公众号"
    assert "X确认状态：降级确认（site:x.com / site:twitter.com）" in payload["items"][0]["description"]
    assert "已写入飞书多维表格" not in payload["thread_summary"]["bullets"]
    assert payload["thread_summary"]["bullets"][-1] == "Bitable 写入未确认成功"
    assert payload["archive_note"] == "目标表（本轮未确认写入成功）：https://chaojifeng.feishu.cn/base/demo"


def test_normalize_ai_hotspot_payload_adds_success_bullet_only_for_confirmed_writes() -> None:
    payload = normalize_template_data(
        "ai-hotspot",
        {
            "title": "AI 热点扫描",
            "archive_target_path": "https://chaojifeng.feishu.cn/base/demo",
            "items": [{"title": "Mamba 3发布", "score": 22, "platform": "知乎/B站", "description": "推理效率革命"}],
            "thread_summary": {"notice": "AI 热点扫描已完成", "bullets": ["新增高分选题：1 个"]},
            "execution_meta": {
                "bitable_write_status": "success",
                "bitable_records_created": 1,
                "bitable_records_updated": 2,
            },
        },
    )

    assert payload["items"][0]["platform"] == "知乎、B站"
    assert payload["thread_summary"]["bullets"][-1] == "已写入飞书多维表格（新增 1 条，更新 2 条）"
    assert payload["archive_note"] == "归档目标表：https://chaojifeng.feishu.cn/base/demo"


def test_select_upsert_target_prefers_same_day_existing_record() -> None:
    canonical_uid = build_topic_uid("Claude Code Channels发布", "2026-03-20", "blogger")
    records = [
        {
            "record_id": "rec_old",
            "created_time": 100,
            "fields": {"topic_uid": [{"text": "legacy-slug", "type": "text"}], "发现时间": 1773993600000},
        },
        {
            "record_id": "rec_new",
            "created_time": 200,
            "fields": {"topic_uid": [{"text": "legacy-slug-2", "type": "text"}], "发现时间": 1773993600000},
        },
    ]

    selected, duplicates = select_upsert_target(records, "2026-03-20", canonical_uid)

    assert selected is not None
    assert selected["record_id"] == "rec_old"
    assert duplicates == 1


def test_build_topic_uid_uses_normalized_topic_phrase() -> None:
    assert derive_topic_phrase("Anthropic Claude Code Channels发布：Telegram/Discord多平台支持") == "claude code channels telegram"
    assert build_topic_uid("Anthropic Claude Code Channels发布：Telegram/Discord多平台支持", "2026-03-20", "blogger") == "sha1-claude-code-channels-telegram-2026-03-20-blogger"
