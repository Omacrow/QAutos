"""Load the test corpus into a running QAutos through its HTTP API.

Signs in as a demo session (needs DEMO_JWT_SECRET, as the web app does), uploads
every evidence document and questionnaire, waits for processing, applies the
answer key's column mapping where the app asks for one, then reports extraction
accuracy and runs a few searches.

Usage (from apps/api, with the API and worker running):
    uv run python scripts/load_corpus.py [--api http://127.0.0.1:8000] [--corpus DIR]
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import httpx
import jwt

from sqa.auth.clerk import DEMO_ISSUER
from sqa.questionnaires.evaluate import score

DEFAULT_CORPUS = Path(__file__).resolve().parents[4] / "Qautos-test"
SEARCHES = [
    "Is multi-factor authentication required for production access?",
    "How long are security logs kept?",
    "What is the recovery time objective?",
    "Were there exceptions in the SOC 2 report?",
    "Do you use customer data to train machine learning models?",
]


def demo_headers(secret: str) -> dict[str, str]:
    now = int(time.time())
    token = jwt.encode(
        {"iss": DEMO_ISSUER, "sub": "corpus-loader", "iat": now, "exp": now + 3600},
        secret,
        algorithm="HS256",
    )
    return {"Authorization": f"Bearer {token}"}


def wait(client: httpx.Client, path: str, pending: set[str], timeout: float = 600) -> Any:
    deadline = time.monotonic() + timeout
    while True:
        body = client.get(path).raise_for_status().json()
        if body["status"] not in pending or time.monotonic() > deadline:
            return body
        time.sleep(1.5)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api", default="http://127.0.0.1:8000")
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    args = parser.parse_args()
    secret = os.environ.get("DEMO_JWT_SECRET")
    if not secret:
        print("Set DEMO_JWT_SECRET (the API's demo secret).", file=sys.stderr)
        return 1
    client = httpx.Client(base_url=args.api, headers=demo_headers(secret), timeout=300)
    me = client.get("/v1/me").raise_for_status().json()
    print(f"Loading into: {me['org']['name']}\n")

    print("Evidence documents")
    for path in sorted((args.corpus / "evidence").iterdir()):
        response = client.post("/v1/documents", files={"file": (path.name, path.read_bytes())})
        response.raise_for_status()
        doc = response.json()["document"]
        doc = wait(client, f"/v1/documents/{doc['id']}", {"queued", "processing"})
        detail = f"{doc['chunk_count']} passages" if doc["status"] == "ready" else doc["error_code"]
        print(f"  {doc['status']:<8} {path.name}  ({detail})")

    print("\nQuestionnaires (expected / extracted / matched)")
    totals = [0, 0, 0]
    for key_path in sorted((args.corpus / "answer-keys").glob("*.json")):
        answer = json.loads(key_path.read_text(encoding="utf-8"))
        path = args.corpus / "questionnaires" / answer["file"]
        response = client.post("/v1/questionnaires", files={"file": (path.name, path.read_bytes())})
        response.raise_for_status()
        record = response.json()["questionnaire"]
        base = f"/v1/questionnaires/{record['id']}"
        record = wait(client, base, {"queued", "extracting"})
        note = ""
        if record["status"] == "needs_mapping" and answer.get("user_mapping"):
            client.put(f"{base}/mapping", json=answer["user_mapping"]).raise_for_status()
            record = wait(client, base, {"queued", "extracting"})
            note = " (columns chosen as a user would)"
        questions = client.get(f"{base}/questions", params={"limit": 500}).json()["items"]
        result = score(answer["questions"], [q["text"] for q in questions])
        totals = [
            totals[0] + result.expected,
            totals[1] + result.extracted,
            totals[2] + result.matched,
        ]
        print(
            f"  {record['status']:<13} {result.expected:>3} {result.extracted:>3} "
            f"{result.matched:>3}  {path.name}  [{record.get('extractor')}]{note}"
        )
    expected, extracted, matched = totals
    print(f"  precision {matched / max(extracted, 1):.3f}  recall {matched / max(expected, 1):.3f}")

    print("\nSearch")
    for question in SEARCHES:
        found = client.post("/v1/search", json={"query": question, "limit": 3}).json()
        print(f"  Q: {question}")
        for hit in found["results"]:
            where = (
                f"p.{hit['page_start']}"
                if hit["page_start"]
                else f"{hit['sheet']} row {hit['row_start']}"
            )
            print(f"     - {hit['document_filename']} · {where} · {hit['heading'] or ''}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
