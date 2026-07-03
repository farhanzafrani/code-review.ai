"""The core AI review call: takes a PR diff, returns structured findings."""

import json

from openai import OpenAI

from app.core.config import settings

SYSTEM_PROMPT = """\
You are a meticulous senior software engineer doing a pull request code review.
You will be given a unified diff. Review ONLY the changes shown — do not
invent context you can't see. Report two distinct kinds of findings:

1. "bugs" — correctness issues, logic errors, and clear defects introduced by
   this diff. Do not nitpick style, formatting, or naming unless it causes an
   actual bug.
2. "security_issues" — security vulnerabilities introduced or present in the
   changed code: injection (SQL/command/etc.), hardcoded secrets or
   credentials, broken authn/authz, insecure crypto, unsafe deserialization,
   SSRF, path traversal, vulnerable dependency usage, or insecure
   configuration. Do not duplicate the same finding in both lists — if
   something is fundamentally a security issue, report it only under
   security_issues.

If you find nothing in a category, return an empty list for it rather than
inventing issues.
"""

FINDING_PROPERTIES = {
    "file": {
        "type": "string",
        "description": "File path from the diff this finding applies to.",
    },
    "severity": {
        "type": "string",
        "enum": ["low", "medium", "high", "critical"],
    },
    "description": {
        "type": "string",
        "description": "What the issue is and why it's a problem.",
    },
}

REVIEW_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {
            "type": "string",
            "description": "2-4 sentence plain-English summary of what this PR "
            "changes and the overall review verdict.",
        },
        "bugs": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    **FINDING_PROPERTIES,
                    "suggestion": {
                        "type": "string",
                        "description": "A concrete suggested fix.",
                    },
                },
                "required": ["file", "severity", "description", "suggestion"],
                "additionalProperties": False,
            },
        },
        "security_issues": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    **FINDING_PROPERTIES,
                    "category": {
                        "type": "string",
                        "enum": [
                            "injection",
                            "secrets",
                            "auth",
                            "crypto",
                            "insecure_config",
                            "dependency",
                            "other",
                        ],
                    },
                    "recommendation": {
                        "type": "string",
                        "description": "A concrete remediation.",
                    },
                },
                "required": [
                    "file",
                    "severity",
                    "category",
                    "description",
                    "recommendation",
                ],
                "additionalProperties": False,
            },
        },
    },
    "required": ["summary", "bugs", "security_issues"],
    "additionalProperties": False,
}

_client: OpenAI | None = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=settings.openai_api_key)
    return _client


def _format_context(context_chunks: list[dict]) -> str:
    parts = [
        f"# {chunk['file']} (from line {chunk['start_line']})\n{chunk['text']}"
        for chunk in context_chunks
    ]
    return (
        "Relevant existing code from this repository, for context only — "
        "review the diff, not this:\n\n" + "\n\n".join(parts)
    )


def run_ai_review(diff: str, pr_title: str, context_chunks: list[dict] | None = None) -> dict:
    """Call the LLM with the diff and return a dict matching REVIEW_JSON_SCHEMA.

    context_chunks (from RAG retrieval) are optional extra repo context beyond
    the diff itself — e.g. the function a changed call site actually invokes.
    """
    user_content = f"PR title: {pr_title}\n\nDiff:\n```diff\n{diff}\n```"
    if context_chunks:
        user_content += "\n\n" + _format_context(context_chunks)

    response = _get_client().chat.completions.create(
        model=settings.openai_model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "code_review",
                "schema": REVIEW_JSON_SCHEMA,
                "strict": True,
            },
        },
    )
    return json.loads(response.choices[0].message.content)


_SEVERITY_EMOJI = {"low": "🔵", "medium": "🟡", "high": "🟠", "critical": "🔴"}


def format_review_comment(result: dict, truncated: bool = False) -> str:
    lines = ["## 🤖 AI Code Review", "", result["summary"], ""]

    bugs = result.get("bugs", [])
    if bugs:
        lines.append(f"### Bugs ({len(bugs)})")
        lines.append("")
        for bug in bugs:
            emoji = _SEVERITY_EMOJI.get(bug["severity"], "⚪")
            lines.append(f"- {emoji} **{bug['severity'].upper()}** · `{bug['file']}`")
            lines.append(f"  {bug['description']}")
            lines.append(f"  _Suggested fix:_ {bug['suggestion']}")
            lines.append("")
    else:
        lines.append("No bugs found in this diff.")
        lines.append("")

    security_issues = result.get("security_issues", [])
    if security_issues:
        lines.append(f"### 🔒 Security ({len(security_issues)})")
        lines.append("")
        for issue in security_issues:
            emoji = _SEVERITY_EMOJI.get(issue["severity"], "⚪")
            lines.append(
                f"- {emoji} **{issue['severity'].upper()}** · `{issue['file']}` · {issue['category']}"
            )
            lines.append(f"  {issue['description']}")
            lines.append(f"  _Recommendation:_ {issue['recommendation']}")
            lines.append("")

    if truncated:
        lines.append(
            f"> ⚠️ This diff was truncated to {settings.max_diff_chars:,} characters "
            "before review — some changes may not have been analyzed."
        )
        lines.append("")

    lines.append(
        "<sub>Automated review generated by CodeReviewAI. Verify findings before relying on them.</sub>"
    )
    return "\n".join(lines)
