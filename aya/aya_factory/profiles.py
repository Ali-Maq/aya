"""Reviewed capabilities. New requests remain proposals until their tests exist."""

from typing import Any

SQL_REPOSITORY = "Ali-Maq/crusoe-developer-hub"
SQL_DIRECTORY = "examples/cookbooks/repository-analyst"
SOURCE_COMMIT = "6ada4081cf7bdb5cec7dcf066dd29d784f55b232"
SOURCE_PATH = "training/case-studies/agentic_rl_text2sql/sql_tools.py"
SOURCE_SHA = "3d362c60eb258dba706b838092dc41cc892dee00b541c9ff1b924c35bd2e9b64"
SOURCE_URL = f"https://github.com/fw-ai/cookbook/blob/{SOURCE_COMMIT}/{SOURCE_PATH}"
SQL_FEATURE = "Bring Fireworks' tool-calling SQL workflow to Crusoe. Let me ask questions about live GitHub repository data, show the executed SQL and result rows, reject database writes, and return a tested pull request."

PROFILES: dict[str, dict[str, Any]] = {
    "saved-json-export": {
        "id": "saved-json-export",
        "repository": "Ali-Maq/aya-data-recipes",
        "title": "Saved JSON export recipes",
        "feature": "Recover saved JSON export recipes from jq for Open WebUI.",
        "reference": "https://github.com/jqlang/jq/releases/tag/jq-1.8.2",
        "contract_path": "specs/export-recipe.json",
        "contract_sha256": "b2f301300170295fd0a9236105d274ea88580b2beccf9289205c8a4c98763261",
        "allowed_paths": ["recipe.py", "tests/test_agent_recipe.py"],
        "reference_kind": "binary",
        "product_url": "http://localhost:3032",
    },
    "crusoe-repository-analyst": {
        "id": "crusoe-repository-analyst",
        "repository": SQL_REPOSITORY,
        "title": "Fireworks → Crusoe repository analyst",
        "feature": SQL_FEATURE,
        "reference": SOURCE_URL,
        "contract_path": "specs/crusoe-repository-analyst.json",
        "contract_sha256": "7c56492fc8333c3a770e2b692ee8df12652266bd6bb768dec1cde2486b2a5ee6",
        "allowed_paths": [
            f"{SQL_DIRECTORY}/query.py",
            f"{SQL_DIRECTORY}/tests/test_agent_query.py",
            f"{SQL_DIRECTORY}/README.md",
        ],
        "reference_kind": "source-and-runtime",
        "product_url": "http://localhost:3021/app/factory",
    },
}


def catalog() -> list[dict[str, Any]]:
    return [PROFILES["crusoe-repository-analyst"], PROFILES["saved-json-export"]]


def for_repository(repository: str) -> dict[str, Any]:
    for profile in PROFILES.values():
        if profile["repository"] == repository:
            return profile
    raise ValueError("Repository has no reviewed capability yet")
