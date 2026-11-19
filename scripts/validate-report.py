#!/usr/bin/env python3
"""Validate and commit research digests with recoverable local state.

Python 3.10+, standard library only. From the repository root:
  python scripts/validate-report.py begin
  python scripts/validate-report.py check --draft drafts/<ID>
  python scripts/validate-report.py finalize --draft drafts/<ID>
  python scripts/validate-report.py validate
  python scripts/validate-report.py recover
"""

import argparse
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sys
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
import uuid


TZ = timezone(timedelta(hours=8))
SECTIONS = {
    "research": "具身学术研究",
    "open_source": "开源项目与数据集",
    "industry": "AI 行业重要动态",
}
INITIAL = dict(schema_version=1, timezone="Asia/Shanghai", covered_until=None,
               completed_at=None, last_report_id=None, reports=[])
EMPTY_INDEX = dict(schema_version=1, items=[])


class Invalid(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise Invalid(message)


def now():
    return datetime.now(TZ).isoformat(timespec="seconds")


def stamp(value):
    require(isinstance(value, str), "timestamp must be a string")
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    require(dt.tzinfo is not None, f"timestamp needs timezone: {value}")
    return dt


def encode(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def digest(data):
    return hashlib.sha256(data).hexdigest()


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def atomic(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    with temp.open("wb") as out:
        out.write(data)
        out.flush()
        os.fsync(out.fileno())
    os.replace(temp, path)


def immutable(path, data):
    if path.exists():
        require(path.read_bytes() == data, f"refusing to overwrite history: {path}")
    else:
        atomic(path, data)


def safe_id(value):
    require(isinstance(value, str) and re.fullmatch(r"[a-z0-9][a-z0-9-]{0,100}", value),
            f"invalid identifier: {value}")
    return value


def canonical_url(value):
    require(isinstance(value, str), "URL must be a string")
    u = urlsplit(value)
    require(u.scheme in {"https", "http"} and u.hostname and not u.username,
            f"invalid source URL: {value}")
    host = u.netloc.lower()
    path = u.path.rstrip("/")
    if u.hostname.lower() in {"arxiv.org", "www.arxiv.org", "export.arxiv.org"}:
        match = re.fullmatch(r"/(abs|pdf|html)/(\d{4}\.\d{4,5})(v\d+)?(?:\.pdf)?", path)
        if match:
            return "https://arxiv.org/abs/" + match[2]
    query = [(k, v) for k, v in parse_qsl(u.query) if not k.startswith("utm_")
             and k not in {"source", "ref", "fbclid", "gclid"}]
    return urlunsplit((u.scheme.lower(), host, path, urlencode(sorted(query)), ""))


def key(item):
    return item["work_id"], item["event_id"]


def validate_manifest(m, body):
    require(m["schema_version"] == 1, "unsupported manifest schema")
    safe_id(m["report_id"])
    w = m["window"]
    start, end, search_start = (stamp(w[k]) for k in ("start", "end", "search_start"))
    require(search_start <= start < end, "invalid coverage window")
    require(end <= stamp(now()), "coverage ends in the future")
    require(set(m["sections"]) == set(SECTIONS), "all three sections are required")
    require(isinstance(m["items"], list), "items must be a list")
    for section, heading in SECTIONS.items():
        require(m["sections"][section]["status"] == "complete", f"incomplete search: {section}")
        require(m["sections"][section]["note"].strip(), f"missing coverage note: {section}")
        require(body.count("## " + heading) == 1, f"missing/duplicate section: {heading}")
        require(any(s["section"] == section and s["status"] == "ok" for s in m["search_log"]),
                f"no successful search recorded: {section}")
    for s in m["search_log"]:
        require(s["section"] in SECTIONS and s["status"] in {"ok", "failed"}, "invalid search record")
        require(s["query"].strip() and s["note"].strip(), "search query and note required")
        require(stamp(s["searched_at"]) <= stamp(now()), "search time is in the future")
        for url in s["urls"]:
            canonical_url(url)
    for candidate in m["excluded"]:
        require(candidate["title"].strip() and candidate["reason"].strip(), "excluded candidate needs reason")
        canonical_url(candidate["url"])
    require(w["start"] in body and w["end"] in body, "report must show exact coverage window")
    markers = re.findall(r"<!-- item:([a-z0-9-]+) -->", body)
    require(len(markers) == len(set(markers)), "duplicate item marker")
    require(set(markers) == {item["id"] for item in m["items"]}, "report/manifest items differ")
    seen, ids, urls_to_work = set(), set(), {}
    for item in m["items"]:
        item_id = safe_id(item["id"])
        require(item_id not in ids, "duplicate item id")
        ids.add(item_id)
        require(re.fullmatch(r"(arxiv|github|org):[a-z0-9][a-z0-9./_-]*", item["work_id"]), "invalid work_id")
        require(item["event_id"].strip() and item["title"].strip() and item["change_summary"].strip(),
                "event, title and change_summary required")
        require(key(item) not in seen, f"duplicate event: {key(item)}")
        seen.add(key(item))
        section = item["section"]
        require(section in SECTIONS, "invalid item section")
        marker = "<!-- item:" + item_id + " -->"
        offset = body.index(marker)
        headings = [(body.index("## " + title), slug) for slug, title in SECTIONS.items()]
        require(max((p, slug) for p, slug in headings if p < offset)[1] == section,
                f"item in wrong section: {item_id}")
        item_body = re.split(r"<!-- item:|\n## ", body[offset + len(marker):], maxsplit=1)[0]
        require(len(item_body.strip()) >= 80, f"item lacks readable analysis: {item_id}")
        published = item["published_at"]
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", published):
            p = datetime.combine(date.fromisoformat(published), datetime.min.time(), TZ)
            # Date-only sources cannot establish the precise side of a time boundary.
            require(p <= end, f"future-dated item: {item_id}")
            before = p + timedelta(days=1) <= start
        else:
            p = stamp(published)
            require(p <= end, f"item beyond coverage end: {item_id}")
            before = p < start
        require(type(item["late_discovery"]) is bool, "late_discovery must be boolean")
        require(not before or item["late_discovery"], f"old item needs late_discovery: {item_id}")
        require(not item["late_discovery"] or item["late_reason"].strip(), "late discovery needs a reason")
        require(item["sources"], f"no sources: {item_id}")
        source_urls = set()
        for source in item["sources"]:
            url = canonical_url(source["url"])
            source_urls.add(url)
            require(source["kind"] == "primary", "reported facts need primary sources")
            require(source["evidence_level"] in {"full_text", "repository", "official_announcement", "abstract", "data_card"},
                    "invalid evidence level")
            require(stamp(source["accessed_at"]) <= stamp(now()), "future access time")
            require(source["claims"] and all(c["claim"].strip() and c["locator"].strip() for c in source["claims"]),
                    "source claims require locators")
            links = re.findall(r"\]\((https?://[^\s)]+)\)", item_body)
            require(url in {canonical_url(link) for link in links}, f"source absent from item body: {source['url']}")
            old_work = urls_to_work.setdefault(url, item["work_id"])
            require(old_work == item["work_id"], f"same source assigned to different works: {url}")
        require(canonical_url(item["date_source"]) in source_urls, "date_source must be an inspected source")
    return m


def build_state(root, report_ids, overrides=None):
    """Derive the entire committed index from immutable reports, in checkpoint order."""
    overrides = overrides or {}
    require(len(report_ids) == len(set(report_ids)), "duplicate report in checkpoint")
    index, previous, seen, aliases = [], None, set(), {}
    for rid in report_ids:
        safe_id(rid)
        if rid in overrides:
            m, body = overrides[rid]
        else:
            m = read(root / "reports" / (rid + ".json"))
            body = (root / "reports" / (rid + ".md")).read_text(encoding="utf-8")
        validate_manifest(m, body)
        require(m["report_id"] == rid, "report id/path mismatch")
        require(m["report_sha256"] == digest(body.encode("utf-8")), f"report hash mismatch: {rid}")
        require(stamp(m["completed_at"]) >= stamp(m["window"]["end"]), "completion precedes cutoff")
        require(stamp(m["completed_at"]) <= stamp(now()), "completion in the future")
        if previous:
            require(stamp(m["window"]["start"]) == stamp(previous["window"]["end"]), "coverage gap/overlap")
        for item in m["items"]:
            require(key(item) not in seen, f"already reported event: {key(item)}")
            seen.add(key(item))
            for s in item["sources"]:
                url = canonical_url(s["url"])
                require(aliases.setdefault(url, item["work_id"]) == item["work_id"], "work identity changed across reports")
            index.append({**item, "report_id": rid})
        previous = m
    cp = {**INITIAL, "reports": list(report_ids)}
    if previous:
        cp.update(covered_until=previous["window"]["end"], completed_at=previous["completed_at"],
                  last_report_id=previous["report_id"])
    return cp, {"schema_version": 1, "items": index}


def validate(root, allow_active=True):
    require(not (root / "state/pending.json").exists(), "unfinished commit: run recover")
    if not allow_active:
        require(not (root / "state/active-run.json").exists(), "research already active; resume or abort it")
    cp = read(root / "state/checkpoint.json")
    index = read(root / "state/collected-items.json")
    expected_cp, expected_index = build_state(root, cp["reports"])
    require(cp == expected_cp, "checkpoint does not match report history")
    require(index == expected_index, "collected-items does not match report history")
    for path in (root / "reports").glob("*"):
        if path.suffix in {".json", ".md"}:
            require(path.stem in cp["reports"], f"uncommitted report: {path}; inspect before proceeding")
    return cp, index


@contextmanager
def command_lock(root):
    path = root / "state/.command.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("x", encoding="utf-8") as out:
            out.write(json.dumps({"pid": os.getpid(), "started_at": now()}))
    except FileExistsError as exc:
        raise Invalid("state command locked; verify the owning process before manual recovery") from exc
    try:
        yield
    finally:
        path.unlink()


def begin(root, until=None):
    cp, _ = validate(root, allow_active=False)
    cfg = read(root / "config/sources.yaml")
    end = stamp(until or now()).astimezone(TZ)
    start = stamp(cp["covered_until"]) if cp["covered_until"] else end - timedelta(days=cfg["initial_lookback_days"])
    require(start < end <= stamp(now()), "cutoff must be later than previous coverage and not in future")
    search_start = start - timedelta(days=cfg["overlap_days"]) if cp["reports"] else start
    rid = end.strftime("%Y-%m-%d-%H%M%S") + "-" + uuid.uuid4().hex[:6]
    active = {"report_id": rid, "started_at": now(),
              "base_checkpoint_sha256": digest((root / "state/checkpoint.json").read_bytes()),
              "window": {"start": start.isoformat(), "end": end.isoformat(), "search_start": search_start.isoformat()}}
    atomic(root / "state/active-run.json", encode(active))
    draft = root / "drafts" / rid
    draft.mkdir(parents=True, exist_ok=False)
    manifest = {"schema_version": 1, **active,
                "sections": {k: {"status": "pending", "note": ""} for k in SECTIONS},
                "search_log": [], "items": [], "excluded": []}
    atomic(draft / "manifest.json", encode(manifest))
    return {"report_id": rid, "draft": str(draft), "window": active["window"]}


def candidate(root, draft):
    cp, _ = validate(root)
    active = read(root / "state/active-run.json")
    m = read(draft / "manifest.json")
    body = (draft / "report.md").read_text(encoding="utf-8")
    for field in ("report_id", "window", "base_checkpoint_sha256", "started_at"):
        require(m[field] == active[field], f"draft changed reserved field: {field}")
    require(m["base_checkpoint_sha256"] == digest((root / "state/checkpoint.json").read_bytes()),
            "checkpoint changed during research")
    require(m["report_id"] not in cp["reports"], "report already committed")
    require(stamp(m["started_at"]) <= stamp(now()), "run start in future")
    m = {**m, "completed_at": now(), "report_sha256": digest(body.encode("utf-8"))}
    next_cp, next_index = build_state(root, cp["reports"] + [m["report_id"]], {m["report_id"]: (m, body)})
    require(not (root / "reports" / (m["report_id"] + ".md")).exists(), "report path already exists")
    return {"manifest": m, "body": body, "checkpoint": next_cp, "index": next_index,
            "base_checkpoint_sha256": m["base_checkpoint_sha256"]}


def replay(root, tx):
    m, body, cp, index = (tx[k] for k in ("manifest", "body", "checkpoint", "index"))
    rid = safe_id(m["report_id"])
    actual_hash = digest((root / "state/checkpoint.json").read_bytes())
    require(actual_hash in {tx["base_checkpoint_sha256"], digest(encode(cp))}, "cannot replay over a different checkpoint")
    require(cp["reports"][-1] == rid, "pending report is not last in checkpoint")
    expected_cp, expected_index = build_state(root, cp["reports"], {rid: (m, body)})
    require(cp == expected_cp and index == expected_index, "pending transaction inconsistent")
    immutable(root / "reports" / (rid + ".md"), body.encode("utf-8"))
    immutable(root / "reports" / (rid + ".json"), encode(m))
    atomic(root / "state/collected-items.json", encode(index))
    # The checkpoint is the commit boundary. A journal makes earlier writes replayable.
    atomic(root / "state/checkpoint.json", encode(cp))
    (root / "state/active-run.json").unlink(missing_ok=True)
    (root / "state/pending.json").unlink()
    return rid


def finalize(root, draft):
    tx = candidate(root, draft)
    atomic(root / "state/pending.json", encode(tx))
    return replay(root, tx)


def recover(root):
    pending = root / "state/pending.json"
    if not pending.exists():
        validate(root)
        return "no pending transaction"
    return replay(root, read(pending))


def abort(root, reason):
    require(reason and reason.strip(), "abort needs a reason")
    require(not (root / "state/pending.json").exists(), "commit started: recover instead of abort")
    active = read(root / "state/active-run.json")
    failure = {**active, "aborted_at": now(), "reason": reason}
    immutable(root / "state/failures" / (safe_id(active["report_id"]) + ".json"), encode(failure))
    (root / "state/active-run.json").unlink()
    return active["report_id"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["begin", "check", "finalize", "validate", "recover", "abort"], nargs="?", default="validate")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--draft", type=Path)
    parser.add_argument("--until", help="ISO 8601 cutoff with timezone; defaults to Beijing now")
    parser.add_argument("--reason")
    args = parser.parse_args()
    root = args.root.resolve()
    try:
        with command_lock(root):
            if args.command == "begin":
                result = begin(root, args.until)
            elif args.command in {"check", "finalize"}:
                require(args.draft is not None, "--draft is required")
                draft = args.draft if args.draft.is_absolute() else root / args.draft
                result = finalize(root, draft) if args.command == "finalize" else candidate(root, draft)["manifest"]["report_id"]
            elif args.command == "recover":
                result = recover(root)
            elif args.command == "abort":
                result = abort(root, args.reason)
            else:
                cp, index = validate(root)
                result = {"reports": len(cp["reports"]), "items": len(index["items"]), "covered_until": cp["covered_until"]}
        print(json.dumps({"ok": True, "result": result}, ensure_ascii=False, indent=2))
        return 0
    except (Invalid, OSError, ValueError, KeyError, TypeError, AttributeError, IndexError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
