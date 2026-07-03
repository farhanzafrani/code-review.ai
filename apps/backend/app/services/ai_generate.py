"""On-demand generation: unit tests and documentation for a PR's diff.

Distinct from ai_review.py's automatic review — these run synchronously,
triggered by a user action on the dashboard, not by the webhook pipeline.
"""

import json

from openai import OpenAI

from app.core.config import settings

_client: OpenAI | None = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=settings.openai_api_key)
    return _client


GENERATED_FILE_SCHEMA = {
    "type": "object",
    "properties": {
        "filename": {
            "type": "string",
            "description": "Suggested path for this generated file, relative to the repo root.",
        },
        "content": {"type": "string"},
    },
    "required": ["filename", "content"],
    "additionalProperties": False,
}

GENERATION_RESULT_SCHEMA = {
    "type": "object",
    "properties": {
        "notes": {
            "type": "string",
            "description": "1-3 sentences on what was generated and any caveats "
            "(e.g. untestable code, missing context).",
        },
        "files": {"type": "array", "items": GENERATED_FILE_SCHEMA},
    },
    "required": ["notes", "files"],
    "additionalProperties": False,
}

TEST_SYSTEM_PROMPT = """\
You are a senior software engineer writing unit tests for a pull request.
You will be given a unified diff. Write unit tests that cover the new or
changed behavior in the diff, using the testing conventions and framework
implied by the diff's language and file paths (e.g. pytest for Python,
Jest/Vitest for TypeScript). Only test code actually shown in the diff —
do not invent unrelated functionality. If the diff has nothing meaningfully
testable (e.g. pure config/docs changes), return an empty files list and
say so in notes.
"""

DOCS_SYSTEM_PROMPT = """\
You are a senior software engineer documenting a pull request. You will be
given a unified diff. Produce updated docstrings/comments for new or
changed functions and classes, plus a short markdown snippet suitable for
a README or CHANGELOG describing the change. Only document code actually
shown in the diff. If nothing in the diff warrants documentation, return an
empty files list and say so in notes.
"""


def _run(system_prompt: str, diff: str, pr_title: str) -> dict:
    response = _get_client().chat.completions.create(
        model=settings.openai_model,
        messages=[
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": f"PR title: {pr_title}\n\nDiff:\n```diff\n{diff}\n```",
            },
        ],
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "generation_result",
                "schema": GENERATION_RESULT_SCHEMA,
                "strict": True,
            },
        },
    )
    return json.loads(response.choices[0].message.content)


def generate_tests(diff: str, pr_title: str) -> dict:
    return _run(TEST_SYSTEM_PROMPT, diff, pr_title)


def generate_docs(diff: str, pr_title: str) -> dict:
    return _run(DOCS_SYSTEM_PROMPT, diff, pr_title)
