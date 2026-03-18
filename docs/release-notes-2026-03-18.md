# 2026-03-18 Release Notes

## Summary

This release moves the project closer to a config-first delivery foundation:

- template content is now driven by `presentation.schema + structure + styles + blocks`
- transport/provider is now modeled in config via `route.transport.provider`
- legacy runtime templates can be migrated into config with a materialization script
- new agent delivery tasks can be scaffolded with a single command

## Why This Release Happened

During a production migration, some templates such as `daily-knowledge` degraded into title-only cards.

Root cause:

- runtime templates still carried legacy `renderer` names like `daily_knowledge`
- the open-source repo had already simplified runtime rendering
- those legacy renderer semantics were not materialized into config, so the runtime fell back to generic rendering
- result: only `title + summary + timestamp` stayed visible, while arrays like `execution_steps`, `insights`, and `updated_files` were not expanded

This release fixes that by moving rendering intent into template config itself.

## What Changed

### 1. Config-Driven Rendering

Templates can now define message structure through functional layout families and explicit structure metadata.

Key config fields:

- `presentation.schema`
- `presentation.structure`
- `presentation.styles`
- `presentation.blocks`

Supported block types:

- `plain_text`
- `markdown`
- `facts`
- `list`
- `record_list`
- `collapsible_panel`
- `collapsible_record_panels`
- `divider`
- `note`

Recommended structure families:

- `generic`
- `collapsible-list`
- `grouped-panels`
- `panel-report`

Runtime scripts now read config and assemble cards from those structures and blocks.

### 2. Transport Provider in Config

Templates can now declare the transport/provider explicitly:

```json
"route": {
  "transport": {
    "provider": "feishu",
    "account": "main"
  }
}
```

This separates:

- transport/provider: `feishu`, `telegram`, `discord`
- delivery channel: `direct`, `message`, `topic`

The current implementation still ships with Feishu delivery only, but the config contract is now ready for multi-provider expansion.

### 3. Legacy Renderer Materialization

Use:

```bash
python3 scripts/materialize_template_presentations.py \
  --templates-file runtime/feishu-templates.local.json \
  --write \
  --drop-renderer
```

This converts known legacy templates into explicit structure config.

### 4. One-Command Task Scaffolding

Use:

```bash
python3 scripts/scaffold_agent_task.py --help
```

The scaffold script creates:

- runtime template config
- runtime job spec
- example payload

## Recommended Upgrade Path

```ascii
upgrade existing runtime
  -> pull latest repo
  -> backup runtime/feishu-templates.local.json
  -> run materialize_template_presentations.py
  -> run tests or dry-run send_message.py
  -> verify one message task + one topic task + one topic+summary task
```

## Verification Completed Locally

- `python3 -m py_compile ...` passed
- `python3 -m pytest tests/test_renderer.py tests/test_runtime_and_jobs_sync.py` passed
- `daily-knowledge` now has a regression test that verifies schema 2.0 collapsible panels are rendered from config
- dynamic grouped panels now have coverage through the `openclaw-best-practices` renderer test
