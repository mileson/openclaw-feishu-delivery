[简体中文](README.md) | [**English**](README.en.md)

# OpenClaw Feishu Delivery

> A delivery foundation that helps OpenClaw send reports, inspections, publishing results, and monitoring summaries into fixed Feishu threads with retries.

## What This Repository Is

This repository packages a production-proven Feishu delivery workflow into a reusable open-source project. It is designed for OpenClaw-style multi-agent systems, but it can also be used by plain cron jobs or normal agent conversations.

It focuses on four practical goals:

- Send structured messages through templates
- Keep the same class of reports inside the same fixed Feishu thread
- Automatically append a summary reply after the full card
- Retry failed deliveries instead of waiting for the next scheduled run

```ascii
What you get
────────────────────────────────
Agent / scheduled job / conversation
  -> send a template message
  -> route into a fixed Feishu thread
  -> append a summary reply
  -> enqueue retry on transient failure
  -> retry after 5 minutes
  -> retry again after 30 minutes
  -> mark as failed only after the final attempt
```

## Core Capabilities

- `template`, `text`, and `retry-pending` modes
- Feishu group message, fixed-thread reply, and direct message support
- Stable thread binding through `binding_key_template`
- Summary reply in the same thread
- Retry queue and retry audit logs
- `jobs.json` validation to prevent wrong `job_id` from creating the wrong thread
- Multi-agent, multi-account configuration
- Sanitized examples based on real production task categories

## Production-Oriented Examples

The template and job names in this repository are intentionally kept close to real production usage rather than demo-style naming.

```ascii
blogger
  -> AI Hotspot Scan
  -> Deep Topic Research
  -> Weekly Jike Planning
  -> Jike Automated Content Creation
  -> Jike Reply Monitoring
  -> Twitter/X Social Monitoring

main
  -> Daily Diary
  -> Daily Knowledge Digest

engineer
  -> System Status Inspection

evolution
  -> Skill Discovery
  -> Skill Trial Report
  -> Skill Distribution
```

Two things were kept from production:

- Real business node naming and routing logic
- Fixed-thread, summary-reply, and retry behavior

Two things were removed:

- Real `chat_id`, `open_id`, secrets, and production paths
- Internal environment coupling that should not be open-sourced

## Project Structure

```ascii
openclaw-feishu-delivery
├─ src/openclaw_feishu_cron_kit/
│  ├─ core.py
│  ├─ renderer.py
│  └─ storage.py
├─ scripts/
│  ├─ send_message.py
│  └─ process_retry_queue.py
├─ examples/
│  ├─ feishu-templates.example.json
│  ├─ jobs.example.json
│  ├─ accounts.example.json
│  └─ payloads/
├─ state/
├─ logs/
├─ .env.example
├─ pyproject.toml
├─ README.md
└─ README.en.md
```

## How It Works

```ascii
Successful path
────────────────────────────────
cron / agent / conversation
  -> scripts/send_message.py --mode template
  -> load template config
  -> validate job_id
  -> resolve route + thread
  -> send full card
  -> if topic channel
       -> append summary reply


Failure path
────────────────────────────────
first attempt
  -> retryable failure
       -> write state/feishu-retry-queue.json
       -> retry after 5 minutes
       -> retry again after 30 minutes
       -> mark failed after the last attempt

non-retryable failure
  -> fail immediately
  -> do not enter retry queue
```

## Prompt for Xiaolongxia OpenClaw

If you want Xiaolongxia OpenClaw to install and wire this tool for you, copy the prompt below and send it directly to your OpenClaw agent:

```text
Please read https://github.com/mileson/openclaw-feishu-delivery , especially README, examples/feishu-templates.example.json, examples/jobs.example.json, examples/accounts.example.json, and the files under examples/payloads/. First summarize how this Feishu fixed-thread delivery system works, including how templates determine routes, how job_id and binding_key determine fixed threads, how full cards and summary replies are layered, how retries work, and why the same person may have different open_id values across different agent apps.

Then inspect the current OpenClaw system and report how many agents exist, who they are, what each one is responsible for, and which agents should be connected to this Feishu delivery foundation. Based on the actual agents in the system, generate an agent-by-agent integration draft that explains which templates should be used, which group each template should go to, whether it should use a fixed thread, what the thread title should be, whether the summary reply should mention someone, and whether retry should be enabled.

Next, install openclaw-feishu-delivery on the current OpenClaw server. Clone it into /root/.openclaw/vendor/openclaw-feishu-delivery, create a virtual environment, install dependencies, and copy examples into candidate production config files under config/. Do not overwrite existing production configuration. Generate candidate config files first.

After that, create templates / jobs / accounts mapping drafts for each agent that should be connected. Then run verification: at least one scheduled-task delivery path and one normal conversation delivery path. Verify fixed-thread delivery, summary reply behavior, retry queue behavior, and whether mentions work under the current agent-specific open_id scope. If anything fails, classify the issue as configuration error, wrong job_id, wrong open_id scope, or retry not connected, and provide an actionable repair plan.

During the whole process, first output your understanding summary, current agent inventory, installation result, diff list, candidate configuration table, and verification result. Do not overwrite old config and do not enable production scheduled jobs until I confirm.
```

## Requirements

You will need:

- Python 3.10+
- A Feishu app with `app_id` and `app_secret`
- A target `chat_id`
- `open_id` values for anyone you want to mention in summary replies

## Multi-Agent Advice

This repository is especially useful in a multi-agent environment.

```ascii
Recommended mapping
────────────────────────────────
blogger agent
  -> blogger Feishu app
  -> blogger-specific chat_id / open_id scope

main agent
  -> main Feishu app
  -> main-specific chat_id / open_id scope

engineer agent
  -> engineer Feishu app

evolution agent
  -> evolution Feishu app
```

Important rule:

```ascii
The same human recipient
  under different Feishu apps
    -> may have different open_id values
```

Do not assume the same `open_id` can be reused across every agent app.

## Quick Start

### 1. Install dependencies

```bash
cd openclaw-feishu-delivery
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

### 2. Configure credentials

```bash
cp .env.example .env
```

Then fill in:

```env
FEISHU_APP_ID=your_real_app_id
FEISHU_APP_SECRET=your_real_app_secret
```

You can also use:

- [examples/accounts.example.json](examples/accounts.example.json)

### 3. Configure templates

Edit:

- [examples/feishu-templates.example.json](examples/feishu-templates.example.json)

At minimum:

```json
{
  "target": {
    "id": "oc_your_chat_id_here",
    "type": "chat_id"
  },
  "thread": {
    "binding_key_template": "blogger:ai-hotspot",
    "title_template": "【AI 热点扫描】",
    "summary_reply": {
      "mention_open_ids": ["ou_your_open_id_here"]
    }
  }
}
```

### 4. Configure jobs

Edit:

- [examples/jobs.example.json](examples/jobs.example.json)

Use stable `job_id` values.

```ascii
Wrong
  -> random job_id each time
  -> wrong thread creation

Correct
  -> one stable job_id per business task
```

### 5. Prepare payloads

Examples:

- [examples/payloads/ai-hotspot.example.json](examples/payloads/ai-hotspot.example.json)
- [examples/payloads/daily-diary.example.json](examples/payloads/daily-diary.example.json)
- [examples/payloads/twitter-monitor.example.json](examples/payloads/twitter-monitor.example.json)
- [examples/payloads/system-status.example.json](examples/payloads/system-status.example.json)
- [examples/payloads/skill-trial.example.json](examples/payloads/skill-trial.example.json)
- [examples/payloads/jike-publish.example.json](examples/payloads/jike-publish.example.json)

## Send Your First Template Message

```bash
python3 scripts/send_message.py \
  --mode template \
  --agent-id blogger \
  --job-id blogger-ai-hotspot-hourly \
  --jobs-file examples/jobs.example.json \
  --templates-file examples/feishu-templates.example.json \
  --template ai-hotspot \
  --data "$(cat examples/payloads/ai-hotspot.example.json)"
```

Typical success output:

```ascii
📨 Route resolved: channel=topic target=chat_id:oc_xxx
🧵 Fixed thread: key=blogger:ai-hotspot title=【AI 热点扫描】
✅ Thread message sent
✅ Thread summary reply sent
```

## Retry Worker

Manual run:

```bash
python3 scripts/send_message.py --mode retry-pending
```

Or:

```bash
python3 scripts/process_retry_queue.py
```

Cron example:

```cron
*/5 * * * * cd /path/to/openclaw-feishu-delivery && /usr/bin/python3 scripts/process_retry_queue.py >> logs/retry-worker.log 2>&1
```

## Runtime Files

```ascii
state/
  feishu-thread-bindings.json
  feishu-retry-queue.json

logs/
  feishu-send-audit.jsonl
  feishu-thread-audit.jsonl
  feishu-retry-audit.jsonl
```

## Security Notes

This repository is sanitized:

- No real `chat_id`
- No real `open_id`
- No real `app_secret`
- No production-only absolute paths

Replace all placeholders with your own values before use.

## License

MIT
