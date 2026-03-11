from __future__ import annotations

import argparse
import json
import os
import re
import sys
from typing import Any

import requests


def github_request(method: str, url: str, token: str, **kwargs: Any) -> requests.Response:
    headers = kwargs.pop("headers", {})
    headers.update(
        {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
        }
    )
    response = requests.request(method, url, headers=headers, timeout=60, **kwargs)
    response.raise_for_status()
    return response


def fetch_pr_context(repo: str, pr_number: int, token: str) -> dict[str, Any]:
    base = f"https://api.github.com/repos/{repo}"
    pr = github_request("GET", f"{base}/pulls/{pr_number}", token).json()
    files = github_request("GET", f"{base}/pulls/{pr_number}/files?per_page=100", token).json()
    diff = github_request(
        "GET",
        f"{base}/pulls/{pr_number}",
        token,
        headers={"Accept": "application/vnd.github.v3.diff"},
    ).text
    return {"pr": pr, "files": files, "diff": diff}


def normalize_base_url(raw_value: str) -> str:
    base = raw_value.rstrip("/")
    if base.endswith("/v1"):
        return f"{base}/responses"
    return f"{base}/v1/responses"


def build_review_prompt(context: dict[str, Any]) -> str:
    pr = context["pr"]
    files = context["files"]
    diff = context["diff"]
    file_summary = "\n".join(
        f"- {item['filename']} (+{item['additions']} / -{item['deletions']})"
        for item in files
    )
    return f"""你是一个严格但务实的 GitHub PR 审查机器人。请只关注真正会阻止合并的问题：功能错误、格式协议错误、明显回归、缺少必要测试、安全风险。不要提出风格偏好或无关紧要的建议。

请审查下面这个 PR，并仅输出 JSON，不要输出其他任何文字。

JSON 格式必须严格如下：
{{
  "decision": "approve" | "request_changes",
  "summary": "一句话总结",
  "findings": [
    {{
      "severity": "high" | "medium" | "low",
      "file": "路径",
      "title": "短标题",
      "detail": "问题详情"
    }}
  ],
  "merge_message": "如果 approve，给贡献者的感谢与合并说明；否则给出空字符串"
}}

审查标准：
1. 如果改动修复了真实协议/格式问题，并且没有引入明显新问题，可以 approve。
2. 如果存在测试缺口，可以作为 low 或 medium finding 提醒，但除非这会明显带来高回归风险，否则不要仅因缺少测试而阻止合并。
3. 只有真正会导致错误、回归或安全问题时，才使用 request_changes。
4. 如果没有阻塞问题，findings 返回空数组。

PR 标题：{pr['title']}
PR 描述：
{pr.get('body') or '(无描述)'}

变更文件：
{file_summary or '(无)'}

Diff：
{diff}
"""


def call_model(base_url: str, api_key: str, model: str, prompt: str) -> dict[str, Any]:
    url = normalize_base_url(base_url)
    payload = {
        "model": model,
        "input": [
            {
                "role": "system",
                "content": [{"type": "input_text", "text": "你是资深 Python / GitHub 代码审查专家，只输出合法 JSON。"}],
            },
            {"role": "user", "content": [{"type": "input_text", "text": prompt}]},
        ],
    }
    response = requests.post(
        url,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=180,
    )
    response.raise_for_status()
    data = response.json()
    content = data.get("output_text") or ""
    if not content:
        for item in data.get("output", []):
            for content_item in item.get("content", []):
                if content_item.get("type") == "output_text":
                    content += content_item.get("text", "")
    return extract_json(content)


def extract_json(raw_text: str) -> dict[str, Any]:
    raw_text = raw_text.strip()
    if raw_text.startswith("```"):
        match = re.search(r"```(?:json)?\s*(\{.*\})\s*```", raw_text, re.S)
        if match:
            raw_text = match.group(1)
    try:
        return json.loads(raw_text)
    except json.JSONDecodeError:
        match = re.search(r"(\{.*\})", raw_text, re.S)
        if not match:
            raise
        return json.loads(match.group(1))


def validate_result(result: dict[str, Any]) -> dict[str, Any]:
    decision = result.get("decision")
    if decision not in {"approve", "request_changes"}:
        raise ValueError(f"模型返回了无效 decision: {decision}")
    findings = result.get("findings")
    if not isinstance(findings, list):
        raise ValueError("模型返回的 findings 必须是数组")
    result["summary"] = str(result.get("summary") or "").strip()
    result["merge_message"] = str(result.get("merge_message") or "").strip()
    return result


def fallback_review(context: dict[str, Any], reason: str) -> dict[str, Any]:
    files = context["files"]
    risky_prefixes = (".github/", "scripts/", "pyproject.toml", "LICENSE")
    changed_files = [item["filename"] for item in files]
    total_changes = sum(int(item.get("changes") or 0) for item in files)
    touched_risky = [path for path in changed_files if path.startswith(risky_prefixes) or path in risky_prefixes]

    if touched_risky or len(changed_files) > 2 or total_changes > 40:
        return {
            "decision": "request_changes",
            "summary": "AI 审查服务暂时不可用，且本次 PR 超出低风险自动放行范围，已要求人工复核。",
            "findings": [
                {
                    "severity": "medium",
                    "file": ", ".join(changed_files) or "unknown",
                    "title": "需要人工复核",
                    "detail": f"AI 审查服务不可用（{reason}），且本次改动文件或变更规模超出低风险自动合并白名单。",
                }
            ],
            "merge_message": "",
        }

    return {
        "decision": "approve",
        "summary": "AI 审查服务暂时不可用，本次 PR 已通过低风险规则审查并允许自动合并。",
        "findings": [
            {
                "severity": "low",
                "file": changed_files[0] if changed_files else "unknown",
                "title": "使用规则审查兜底",
                "detail": f"由于 AI 审查服务不可用（{reason}），本次采用低风险规则兜底审查：变更文件数不超过 2，且总变更不超过 40 行。",
            }
        ],
        "merge_message": "已通过自动审查并完成合并，感谢贡献。当前使用了低风险规则兜底审查，因为外部 AI 审查服务暂时不可用。",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Review a GitHub PR with an OpenAI-compatible model.")
    parser.add_argument("--repo", required=True)
    parser.add_argument("--pr-number", type=int, required=True)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--model", required=True)
    args = parser.parse_args()

    github_token = os.getenv("GITHUB_TOKEN")
    api_key = os.getenv("AICODE_API_KEY")
    if not github_token:
        raise SystemExit("缺少 GITHUB_TOKEN")
    if not api_key:
        raise SystemExit("缺少 AICODE_API_KEY")

    context = fetch_pr_context(args.repo, args.pr_number, github_token)
    prompt = build_review_prompt(context)
    try:
        result = call_model(args.base_url, api_key, args.model, prompt)
    except Exception as exc:  # noqa: BLE001
        result = fallback_review(context, str(exc))
    result = validate_result(result)
    result["pr_number"] = args.pr_number
    result["pr_title"] = context["pr"]["title"]
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
