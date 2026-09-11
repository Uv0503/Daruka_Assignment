"""Acquire only the configured allowlisted sources for offline curation.

This command is deliberately separate from runtime retrieval.  It records the
exact bytes, redirect target, content type, retrieval time and SHA-256 needed
to review a card against an actual passage.  It does not crawl links, nor does
it mark a card reviewed merely because a download succeeded.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


MAX_BYTES = 25_000_000


def _suffix(content_type: str, url: str) -> str:
    if "pdf" in content_type or url.lower().endswith(".pdf"):
        return ".pdf"
    return ".html"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", default="app/knowledge/sources.yaml")
    parser.add_argument("--source", action="append", dest="source_ids", help="Source ID to acquire (repeatable); defaults to all manifest sources")
    args = parser.parse_args()

    import httpx
    import yaml

    root = Path(__file__).resolve().parents[1]
    sources = yaml.safe_load((root / args.manifest).read_text())["sources"]
    wanted = set(args.source_ids or [source["source_id"] for source in sources])
    unknown = wanted - {source["source_id"] for source in sources}
    if unknown:
        raise SystemExit(f"unknown source IDs: {', '.join(sorted(unknown))}")
    raw_dir = root / "data" / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    output = root / "data" / "processed" / "acquisition_metadata.json"
    # A targeted refresh must not erase provenance collected for other
    # allowlisted sources.  Preserve old records until that source is actually
    # refreshed; this is important when a source is temporarily inaccessible.
    existing: dict[str, dict[str, object]] = {}
    if output.exists():
        try:
            existing = {item["source_id"]: item for item in json.loads(output.read_text()) if item.get("source_id")}
        except (OSError, TypeError, ValueError):
            raise SystemExit(f"unreadable acquisition metadata: {output}")
    refreshed: dict[str, dict[str, object]] = {}
    transport = httpx.HTTPTransport(retries=2)
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; BiodiversityEvidenceBot/1.0; local research acquisition)",
        "Accept": "application/pdf,text/html;q=0.9",
    }
    with httpx.Client(timeout=httpx.Timeout(45.0), follow_redirects=True, trust_env=False, transport=transport, headers=headers) as client:
        for source in sources:
            if source["source_id"] not in wanted:
                continue
            source_id = source["source_id"]
            try:
                response = client.get(source["url"])
                response.raise_for_status()
                if len(response.content) > MAX_BYTES:
                    raise ValueError(f"response exceeds {MAX_BYTES} byte acquisition limit")
                content_type = response.headers.get("content-type", "").lower()
                if "text/html" not in content_type and "application/pdf" not in content_type:
                    raise ValueError(f"unexpected content type: {content_type or 'missing'}")
                local_path = raw_dir / f"{source_id}{_suffix(content_type, str(response.url))}"
                local_path.write_bytes(response.content)
                refreshed[source_id] = {
                    "source_id": source_id,
                    "requested_url": source["url"],
                    "final_url": str(response.url),
                    "status_code": response.status_code,
                    "content_type": content_type,
                    "content_length": len(response.content),
                    "transport_retries": 2,
                    "user_agent_profile": "transparent_browser_compatible_v1",
                    "retrieved_at": datetime.now(UTC).isoformat(),
                    "content_sha256": hashlib.sha256(response.content).hexdigest(),
                    "local_path": str(local_path.relative_to(root)),
                    "error": None,
                }
            except Exception as exc:  # noqa: BLE001 - acquisition failures are recorded as evidence gaps
                refreshed[source_id] = {
                    "source_id": source_id,
                    "requested_url": source["url"],
                    "retrieved_at": datetime.now(UTC).isoformat(),
                    "error": f"{type(exc).__name__}: {exc}",
                }
    metadata = [refreshed.get(source["source_id"], existing.get(source["source_id"], {"source_id": source["source_id"], "requested_url": source["url"], "error": "not acquired"})) for source in sources]
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(metadata, indent=2) + "\n")
    print(json.dumps({"acquired": sum(item.get("error") is None for item in metadata), "failed": sum(item.get("error") is not None for item in metadata), "metadata": str(output.relative_to(root))}))
    return 0 if not any(item.get("error") for item in metadata) else 1


if __name__ == "__main__":
    raise SystemExit(main())
