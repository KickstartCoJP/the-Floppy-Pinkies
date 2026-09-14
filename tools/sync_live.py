"""Publish the already-filtered ライブスケジュール view as public JSON transport."""
from __future__ import annotations

import csv
import hashlib
import io
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPREADSHEET_ID = "19ei-JBGdxqwWzOO0kILDXPO3obnvgxlY34AELLqh-cs"
SHEET = "ライブスケジュール"
RANGE = "A:D"
SOURCE_URL = (
    f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/gviz/tq"
    "?tqx=out:csv&sheet=%E3%83%A9%E3%82%A4%E3%83%96%E3%82%B9%E3%82%B1%E3%82%B8%E3%83%A5%E3%83%BC%E3%83%AB"
    "&range=A%3AD"
)
OUTPUT = ROOT / "data" / "live.json"


def fetch_csv() -> str:
    result = subprocess.run(
        ["curl", "--fail", "--location", "--silent", "--show-error", "--max-time", "30", SOURCE_URL],
        check=True,
        capture_output=True,
    )
    return result.stdout.decode("utf-8-sig")


def normalize_date(value: str) -> str:
    parts = value.strip().replace("-", "/").split("/")
    if len(parts) != 3:
        raise ValueError(f"invalid date: {value!r}")
    return f"{int(parts[0]):04d}-{int(parts[1]):02d}-{int(parts[2]):02d}"


def read_events(raw: str) -> list[dict[str, str]]:
    rows = list(csv.reader(io.StringIO(raw, newline="")))
    if not rows or rows[0][:4] != ["日付", "会場", "詳細", "フライヤー"]:
        raise ValueError("unexpected headers; refusing to publish")
    events: list[dict[str, str]] = []
    for row in rows[1:]:
        row = (row + ["", "", "", ""])[:4]
        if not row[0].strip() and not row[1].strip():
            continue
        if not row[0].strip() or not row[1].strip():
            raise ValueError(f"incomplete live row: {row!r}")
        events.append({
            "date": normalize_date(row[0]),
            "venue": row[1].strip(),
            "detail": row[2].strip(),
            "flyerUrl": row[3].strip(),
        })
    if not events:
        raise ValueError("source returned zero live rows; refusing to erase cache")
    return events


def main() -> None:
    raw = fetch_csv()
    events = read_events(raw)
    source_sha = hashlib.sha256(raw.encode()).hexdigest()
    generated_at = datetime.now(timezone.utc).isoformat()
    if OUTPUT.exists():
        previous = json.loads(OUTPUT.read_text(encoding="utf-8"))
        if previous.get("source", {}).get("sourceSha256") == source_sha:
            generated_at = previous["source"]["generatedAt"]
    payload = {
        "source": {
            "spreadsheetId": SPREADSHEET_ID,
            "sheet": SHEET,
            "range": RANGE,
            "transport": "Google Visualization CSV -> GitHub raw JSON",
            "filterOwner": "spreadsheet",
            "generatedAt": generated_at,
            "sourceSha256": source_sha,
        },
        "events": events,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"events": len(events), "venues": [x["venue"] for x in events]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
