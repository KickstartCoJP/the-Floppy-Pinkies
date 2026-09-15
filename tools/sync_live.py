"""Publish the already-filtered ライブスケジュール view and its real flyer media."""
from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
SPREADSHEET_ID = "19ei-JBGdxqwWzOO0kILDXPO3obnvgxlY34AELLqh-cs"
SHEET = "ライブスケジュール"
RANGE = "A:D"
SOURCE_URL = (
    f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/gviz/tq"
    "?tqx=out:csv&sheet=%E3%83%A9%E3%82%A4%E3%83%96%E3%82%B9%E3%82%B1%E3%82%B8%E3%83%A5%E3%83%BC%E3%83%AB"
    "&range=A%3AD"
)
LIVE_OUTPUT = ROOT / "data" / "live.json"
MEDIA_OUTPUT = ROOT / "data" / "media.json"
FLYER_DIR = ROOT / "img" / "flyer"
FLYER_RE = re.compile(r"^flyer_(\d{8})\.(jpe?g|png|webp|gif)$", re.IGNORECASE)
DRIVE_ID_RE = re.compile(r"drive\.google\.com/file/d/([^/]+)")


def curl(url: str) -> bytes:
    result = subprocess.run(
        ["curl", "--fail", "--location", "--silent", "--show-error", "--max-time", "30", url],
        check=True,
        capture_output=True,
    )
    return result.stdout


def fetch_csv() -> str:
    return curl(SOURCE_URL).decode("utf-8-sig")


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
        events.append(
            {
                "date": normalize_date(row[0]),
                "venue": row[1].strip(),
                "detail": row[2].strip(),
                "flyerUrl": row[3].strip(),
            }
        )
    if not events:
        raise ValueError("source returned zero live rows; refusing to erase cache")
    return events


def downloadable_url(url: str) -> str:
    match = DRIVE_ID_RE.search(url)
    if not match:
        return url
    return f"https://drive.usercontent.google.com/download?id={match.group(1)}&export=download&confirm=t"


def image_extension(data: bytes) -> str:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if data.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if data.startswith((b"GIF87a", b"GIF89a")):
        return "gif"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    raise ValueError("flyer download is not a supported image")


def mirror_future_flyers(events: list[dict[str, str]], today: str | None = None) -> dict[str, str]:
    today = today or datetime.now(ZoneInfo("Asia/Tokyo")).date().isoformat()
    mirrored: dict[str, str] = {}
    FLYER_DIR.mkdir(parents=True, exist_ok=True)
    for event in events:
        if not event["flyerUrl"] or event["date"] < today:
            continue
        data = curl(downloadable_url(event["flyerUrl"]))
        extension = image_extension(data)
        destination = FLYER_DIR / f"flyer_{event['date'].replace('-', '')}.{extension}"
        if not destination.exists() or destination.read_bytes() != data:
            destination.write_bytes(data)
        mirrored[event["date"]] = destination.relative_to(ROOT).as_posix()
    return mirrored


def media_payload(
    events: list[dict[str, str]], current_paths: dict[str, str] | None = None
) -> dict[str, object]:
    current_dates = {event["date"] for event in events if event["flyerUrl"]}
    use_explicit_paths = current_paths is not None
    current_paths = current_paths or {}
    media: list[dict[str, object]] = []
    for path in sorted(FLYER_DIR.iterdir(), key=lambda item: item.name):
        match = FLYER_RE.match(path.name)
        if not match or not path.is_file():
            continue
        content = path.read_bytes()
        image_extension(content)
        raw_date = match.group(1)
        date = f"{raw_date[:4]}-{raw_date[4:6]}-{raw_date[6:]}"
        purposes = ["archive"]
        asset_path = path.relative_to(ROOT).as_posix()
        if current_paths.get(date) == asset_path or (not use_explicit_paths and date in current_dates):
            purposes.append("current_event_match")
        media.append(
            {
                "date": date,
                "path": asset_path,
                "purposes": purposes,
                "sha256": hashlib.sha256(content).hexdigest(),
            }
        )
    return {
        "source": {
            "assetRoot": "img/flyer",
            "selection": "real date-named flyer assets; current match requires same published event date",
        },
        "media": media,
    }


def write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    raw = fetch_csv()
    events = read_events(raw)
    source_sha = hashlib.sha256(raw.encode()).hexdigest()
    generated_at = datetime.now(timezone.utc).isoformat()
    if LIVE_OUTPUT.exists():
        previous = json.loads(LIVE_OUTPUT.read_text(encoding="utf-8"))
        if previous.get("source", {}).get("sourceSha256") == source_sha:
            generated_at = previous["source"]["generatedAt"]
    live_payload = {
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
    mirrored = mirror_future_flyers(events)
    write_json(LIVE_OUTPUT, live_payload)
    media = media_payload(events, mirrored)
    write_json(MEDIA_OUTPUT, media)
    print(
        json.dumps(
            {"events": len(events), "media": len(media["media"]), "mirrored": list(mirrored.values())},
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
