#!/usr/bin/env python3
"""One rate-limited source-collection step; never publish downloaded material."""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import timezone
from email.utils import parsedate_to_datetime
import fcntl
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import subprocess
import time
import unicodedata
import xml.etree.ElementTree as ET
from urllib.error import HTTPError
from urllib.parse import urljoin, urlsplit
from urllib.request import build_opener, HTTPRedirectHandler, Request
from urllib.robotparser import RobotFileParser

from import_candana import CACHE, MANIFEST, PAGES, ROOT, extract, granted_notice


STATE = CACHE / "queue.json"
USER_AGENT = "FreeBuddhismSourceCollector/1.0 (+https://freebuddhism.org/)"
HOSTS = {"www.mindreleased.com", "static1.squarespace.com"}
INTERVAL = 120
MAX_BYTES = 64 * 1024 * 1024
FORMATS = {".pdf", ".txt", ".docx", ".epub", ".odt", ".rtf"}


def checked_url(value: str) -> str:
    parts = urlsplit(value)
    if (parts.scheme != "https" or parts.hostname not in HOSTS or parts.username
            or parts.password or parts.port not in {None, 443} or "\\" in value):
        raise ValueError("Source URL is outside the approved HTTPS hosts")
    return value.split("#", 1)[0]


def discovery_url(value: str) -> str:
    parts = urlsplit(value)
    if (parts.scheme == "http" and parts.hostname in HOSTS and not parts.username
            and not parts.password and parts.port in {None, 80}):
        value = parts._replace(scheme="https", netloc=parts.hostname).geturl()
    return checked_url(value)


class SourceLinks(HTMLParser):
    def __init__(self, base):
        super().__init__()
        self.base = base
        self.urls = set()

    def handle_starttag(self, tag, attrs):
        if tag != "a":
            return
        value = dict(attrs).get("href", "")
        try:
            if Path(urlsplit(value).path).suffix.casefold() not in FORMATS:
                return
            self.urls.add(discovery_url(urljoin(self.base, value)))
        except ValueError:
            pass


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def request_once(url: str) -> tuple[int, dict, bytes]:
    """Redirects are saved for a future tick, not followed in a request burst."""
    request = Request(checked_url(url), headers={"User-Agent": USER_AGENT, "Accept": "*/*"})
    try:
        response = build_opener(NoRedirect()).open(request, timeout=35)
    except HTTPError as error:
        response = error
    with response:
        status = response.status
        headers = dict(response.headers)
        length = response.headers.get("Content-Length")
        if length and int(length) > MAX_BYTES:
            raise ValueError("Source exceeds the reviewed 64 MiB per-file bound")
        body = response.read(MAX_BYTES + 1) if status == 200 else b""
        if len(body) > MAX_BYTES:
            raise ValueError("Source exceeds the reviewed 64 MiB per-file bound")
        return status, headers, body


def save(state: dict, path: Path = STATE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".pending")
    temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def retry_seconds(value: str | None, now: float) -> float:
    if not value:
        return 0
    if re.fullmatch(r"\d+", value.strip()):
        return float(value.strip())
    try:
        date = parsedate_to_datetime(value)
        if date.tzinfo is None:
            date = date.replace(tzinfo=timezone.utc)
        return max(0, date.timestamp() - now)
    except (ValueError, TypeError, OverflowError):
        return 0


def add_jobs(state: dict, urls) -> None:
    known = {job["url"] for job in state["jobs"]}
    for url in sorted(urls):
        try:
            url = discovery_url(url)
        except ValueError:
            continue
        if url not in known:
            state["jobs"].append({"url": url, "current_url": url, "state": "PENDING", "attempts": 0, "redirects": 0})
            known.add(url)
    if len(known) > 1000:
        state["halt_reason"] = "More than 1,000 source URLs discovered; review the collection scope"


def seed() -> dict:
    if STATE.exists():
        state = json.loads(STATE.read_text(encoding="utf-8"))
        for job in list(state["jobs"]):
            if (job["state"] == "COLLECTED" and job.get("cache", "").endswith(".html")
                    and not job.get("discovery_parsed")):
                process_discovery(state, job, (ROOT / job["cache"]).read_bytes())
        save(state)
        return state
    state = {"schema_version": 1, "interval_seconds": INTERVAL, "next_request_at": 0,
             "halt_reason": None, "consecutive_failures": 0, "robots": {}, "jobs": [],
             "automatic_publication": False}
    discovered = set()
    for page in PAGES:
        cached = CACHE / (hashlib.sha256(page.encode()).hexdigest() + ".html")
        if cached.is_file():
            parser = SourceLinks(page)
            parser.feed(cached.read_text(encoding="utf-8"))
            discovered.update(parser.urls)
    add_jobs(state, (*PAGES, "https://www.mindreleased.com/sitemap.xml"))
    add_jobs(state, discovered)
    # Prefer native text first, then the outstanding complete books, then PDFs.
    state["jobs"].sort(key=lambda job: (
        0 if Path(urlsplit(job["url"]).path).suffix.lower() in {".txt", ".docx", ".odt", ".rtf", ".epub"}
        else 1 if "/Book-" in job["url"] else 2,
        job["url"],
    ))
    for job in state["jobs"]:
        suffix = ".html" if job["url"] in PAGES else ".pdf"
        path = CACHE / (hashlib.sha256(job["url"].encode()).hexdigest() + suffix)
        if path.is_file():
            job.update(state="COLLECTED", cache=path.relative_to(ROOT).as_posix(),
                       sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    if MANIFEST.is_file():
        for book in json.loads(MANIFEST.read_text(encoding="utf-8"))["books"]:
            matching = next((job for job in state["jobs"] if job["url"] == book["source_url"]), None)
            if matching is not None:
                matching.update(state="COLLECTED", cache=book["local_path"], sha256=book["sha256"],
                                rights="EXPLICIT_FREE_UNALTERED")
    # A previous failed bulk pass is not permission for an immediate retry.
    old_audit = CACHE / "audit.json"
    if old_audit.exists() and any("429" in row.get("error", "") for row in json.loads(old_audit.read_text())["sources"]):
        state["next_request_at"] = time.time() + 15 * 60
        state["last_status"] = "Initial cooldown after the earlier HTTP 429 responses"
    save(state)
    return state


def robots_host(url: str) -> str:
    return urlsplit(url).hostname or ""


def priority(job: dict) -> tuple:
    path = urlsplit(job["url"]).path
    suffix = Path(path).suffix.lower()
    order = (0 if suffix in {".txt", ".docx", ".epub", ".odt", ".rtf", ".xml"}
             else 1 if suffix not in FORMATS else 2 if "/Book-" in path else 3)
    return order, job["url"]


def allowed_by_robots(state: dict, url: str) -> bool:
    record = state["robots"].get(robots_host(url))
    if record is None:
        return False
    parser = RobotFileParser()
    parser.parse(record.get("text", "").splitlines())
    return parser.can_fetch(USER_AGENT, url)


def process_discovery(state: dict, job: dict, body: bytes) -> None:
    parser = SourceLinks(job["url"])
    parser.feed(body.decode("utf-8", errors="replace"))
    add_jobs(state, parser.urls)
    if urlsplit(job["url"]).path.endswith("sitemap.xml"):
        try:
            sitemap = ET.fromstring(body)
            locations = [node.text for entry in sitemap for node in entry
                         if node.tag.rsplit("}", 1)[-1] == "loc" and node.text]
            add_jobs(state, locations)
        except ET.ParseError:
            job["discovery_status"] = "SITEMAP_PARSE_REVIEW"
    job["discovery_parsed"] = True


def stage_text(job: dict) -> None:
    """Produce private raw-text candidates, never approved reader editions."""
    key = hashlib.sha256(job["url"].encode()).hexdigest()
    source = ROOT / job["cache"]
    candidates = {}
    try:
        if source.is_symlink() or hashlib.sha256(source.read_bytes()).hexdigest() != job["sha256"]:
            raise ValueError("Cached PDF no longer matches its recorded bytes")
        outputs = {}
        for name, command in (
            ("poppler", ["pdftotext", "-layout", str(source), "-"]),
            ("mupdf", ["mutool", "draw", "-F", "txt", "-o", "-", str(source)]),
        ):
            raw = subprocess.run(command, check=True, capture_output=True, text=True, timeout=20).stdout
            path = CACHE / f"{key}.{name}.txt"
            path.write_text(raw, encoding="utf-8")
            candidates[name] = path.relative_to(ROOT).as_posix()
            outputs[name] = raw.split("\f")
        def inventory(value):
            return Counter(re.sub(r"\s+", "", unicodedata.normalize("NFKC", value)))
        left, right = outputs["poppler"], outputs["mupdf"]
        mismatches = ([number + 1 for number, pair in enumerate(zip(left, right)) if inventory(pair[0]) != inventory(pair[1])]
                      if len(left) == len(right) else ["PAGE_COUNT_MISMATCH"])
        job.update(text_candidates=candidates, text_status="DRAFT_REVIEW_REQUIRED",
                   character_inventory_mismatch_pages=mismatches)
    except Exception as error:
        job.update(text_candidates=candidates, text_status="EXTRACTION_REVIEW_REQUIRED", text_error=str(error))


def step(state: dict, now: float, requester=request_once, persist=save) -> dict:
    if state.get("halt_reason"):
        return {"status": "HALTED", "reason": state["halt_reason"]}
    waiting = now < state.get("next_request_at", 0)
    if waiting or not any(job["state"] == "PENDING" for job in state["jobs"]):
        cached = next((job for job in state["jobs"] if job["state"] == "COLLECTED"
                       and job.get("cache", "").endswith(".pdf") and not job.get("text_status")), None)
        if cached is not None:
            stage_text(cached)
            persist(state)
            return {"status": "STAGED_TEXT_DRAFT", "url": cached["url"], "next_request_at": state["next_request_at"]}
        if waiting:
            return {"status": "WAIT", "next_request_at": state["next_request_at"]}
    pending = min((job for job in state["jobs"] if job["state"] == "PENDING"), key=priority, default=None)
    if pending is None:
        return {"status": "COMPLETE", "collected": sum(job["state"] == "COLLECTED" for job in state["jobs"])}
    url = pending["current_url"]
    host = robots_host(url)
    robot_request = host not in state["robots"]
    if robot_request:
        url = f"https://{host}/robots.txt"
    elif not allowed_by_robots(state, url):
        pending.update(state="ROBOTS_DISALLOWED")
        persist(state)
        return {"status": "ROBOTS_DISALLOWED", "url": url}
    # Persist pacing before I/O so a crash cannot cause an immediate retry.
    state["next_request_at"] = now + state["interval_seconds"]
    state["last_request_at"] = now
    if not robot_request:
        pending["attempts"] += 1
    persist(state)
    request_started = time.monotonic()
    try:
        status, raw_headers, body = requester(url)
        headers = {key.casefold(): value for key, value in raw_headers.items()}
    except Exception as error:
        status, headers, body = 0, {}, b""
        state["last_error"] = str(error)
    received_now = now + max(0, time.monotonic() - request_started)
    state["next_request_at"] = max(state["next_request_at"], received_now + state["interval_seconds"])
    if status in {401, 403}:
        state["halt_reason"] = f"HTTP {status} at {url}; manual review required, no automatic retry"
    elif status == 429 or status == 0 or status >= 500:
        failures = state["consecutive_failures"] + 1
        state["consecutive_failures"] = failures
        backoff = min(24 * 3600, 900 * 2 ** min(failures - 1, 7))
        state["next_request_at"] = received_now + max(backoff, retry_seconds(headers.get("retry-after"), received_now))
        state["last_status"] = f"Backoff after HTTP {status}"
    elif status in {301, 302, 303, 307, 308}:
        if robot_request:
            state["halt_reason"] = "robots.txt redirected; review before collecting content"
        else:
            try:
                target = checked_url(urljoin(url, headers.get("location", "")))
                if pending["redirects"] >= 5 or target == url:
                    raise ValueError("Redirect loop/bound exceeded")
                pending.update(current_url=target, redirects=pending["redirects"] + 1)
            except ValueError as error:
                state["halt_reason"] = str(error)
    elif robot_request and status in {200, 404, 410}:
        text = body.decode("utf-8", errors="replace") if status == 200 else ""
        state["robots"][host] = {"text": text, "status": status, "observed_at": now}
        parser = RobotFileParser()
        parser.parse(text.splitlines())
        delay = parser.crawl_delay(USER_AGENT) or parser.crawl_delay("*") or 0
        # RobotFileParser ignores fractional Crawl-delay values. Conservatively
        # respect the largest numeric delay in the file rather than going faster.
        declared_delays = re.findall(r"(?im)^\s*Crawl-delay\s*:\s*(\d+(?:\.\d+)?)", text)
        if declared_delays:
            delay = max(delay, *(float(value) for value in declared_delays))
        rate = parser.request_rate(USER_AGENT) or parser.request_rate("*")
        if rate:
            delay = max(delay, rate.seconds / rate.requests)
        state["interval_seconds"] = max(state["interval_seconds"], delay)
        state["next_request_at"] = received_now + state["interval_seconds"]
        state["consecutive_failures"] = 0
    elif status in {404, 410}:
        pending.update(state="MISSING", http_status=status)
        state["consecutive_failures"] = 0
    elif status == 200 and not robot_request:
        extension = Path(urlsplit(pending["url"]).path).suffix.lower()
        extension = extension if extension in FORMATS else ".html"
        if extension == ".pdf" and not body.startswith(b"%PDF-"):
            pending.update(state="INVALID_CONTENT", http_status=status)
        else:
            key = hashlib.sha256(pending["url"].encode()).hexdigest()
            path = CACHE / (key + extension)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(body)
            pending.update(state="COLLECTED", cache=path.relative_to(ROOT).as_posix(),
                           sha256=hashlib.sha256(body).hexdigest(), final_url=url)
            if extension == ".html":
                process_discovery(state, pending, body)
            elif extension == ".pdf":
                try:
                    pending["rights"] = "EXPLICIT_FREE_UNALTERED" if granted_notice(extract(path, 10)) else "NEEDS_PERMISSION_REVIEW"
                except Exception as error:
                    pending.update(rights="EXTRACTION_REVIEW_REQUIRED", extraction_error=str(error))
                stage_text(pending)
        state["consecutive_failures"] = 0
    else:
        state["halt_reason"] = f"Unexpected HTTP {status} at {url}; review required"
    persist(state)
    return {"status": "HALTED" if state.get("halt_reason") else "REQUESTED", "url": url,
            "http_status": status, "next_request_at": state["next_request_at"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("init", "tick", "status"))
    args = parser.parse_args()
    CACHE.mkdir(parents=True, exist_ok=True)
    with (CACHE / "queue.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print(json.dumps({"status": "ALREADY_RUNNING"}))
            return
        state = seed()
        if args.action == "tick":
            result = step(state, time.time())
            print(json.dumps(result))
        else:
            print(json.dumps({"jobs": len(state["jobs"]), "states": dict(Counter(row["state"] for row in state["jobs"])),
                              "staged_text_drafts": sum(bool(row.get("text_candidates")) for row in state["jobs"]),
                              "interval_seconds": state["interval_seconds"], "next_request_at": state["next_request_at"],
                              "halt_reason": state["halt_reason"], "automatic_publication": False}, indent=2))


if __name__ == "__main__":
    main()
