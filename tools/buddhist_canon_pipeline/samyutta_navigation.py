# SPDX-License-Identifier: 0BSD
"""Pinned, text-free Saṃyutta navigation and identifier-only placement.

Public node dictionaries are fresh on each call. The independent load/validate
helpers never populate or modify the internal default-data cache.

Accepted site IDs are SN N, SN N-M (whole saṃyuttas), and SN N.S[-E]
(discourses in one saṃyutta). Integers must be positive; hyphen and en dash
ranges are accepted. Outer whitespace and zero padding are harmless. Malformed
and non-SN IDs return None. Valid but unmatched IDs return "samyutta-nikaya",
so historical numbering outside the pin remains visible at the collection root.
No historical numbering conversion or content equivalence is asserted.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import re
from types import MappingProxyType


ROOT = Path(__file__).resolve().parents[2]
NAVIGATION = ROOT / "metadata/samyutta-navigation.json"
REFERENCE = ROOT / "metadata/sutta-reference-units.json"
COLLECTION = "samyutta-nikaya"
_BILARA_COMMIT = "d26ba0072c9e1f7a238159f583720edacb9f05f9"
_SUTTA_TREE = "4d736429e54946e4eb13c914ee90aa00dfc95690"
_REFERENCE_SHA256 = "7db5ea44168eb261e854897d0460e11b9ac832bf141d4dffc702614d118dec7f"
# Canonical UTF-8 JSON (sorted keys, compact separators, ensure_ascii=False).
# The graph pin covers exact names, name keys, kinds, parents and ordered edges;
# the provenance pin covers all remaining public fields, including source hashes.
# Both derive from the independently source-verified, pinned metadata import.
_GRAPH_SHA256 = "56600713e7ca1323bc36119da03a83894aa649301adfab80250be3a96367383b"
_PROVENANCE_SHA256 = "f2485542db7e4fa32d5360463ed95638ef0f00fa06554789d4645ed150a4756e"
_TERMINAL = re.compile(r"sn([1-9][0-9]*)\.([1-9][0-9]*)(?:-([1-9][0-9]*))?")
_SITE_ID = re.compile(r"SN\s+([0-9]+)(?:\.([0-9]+))?(?:[-–]([0-9]+))?")
_NODE_UID = re.compile(r"sn(?:[1-9][0-9]*(?:-[a-z0-9]+)?|-[a-z0-9]+)")
_NODE_KEYS = {"parent", "kind", "name_key", "names", "children"}


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _unique_object(pairs: list[tuple]) -> dict:
    result = {}
    for key, value in pairs:
        _require(key not in result, "Duplicate JSON key: " + key)
        result[key] = value
    return result


def _read_json(raw: bytes) -> dict:
    return json.loads(raw, object_pairs_hook=_unique_object)


def _digest(value: dict) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _terminal_interval(uid: str) -> tuple[int, int, int]:
    match = _TERMINAL.fullmatch(uid)
    _require(match is not None, "Invalid terminal ID: " + uid)
    section, first, end = match.groups()
    first, last = int(first), int(end or first)
    _require(first <= last, "Reversed terminal interval: " + uid)
    return int(section), first, last


def validate_samyutta_navigation(data: dict, *, reference_path: str | Path | None = None) -> None:
    """Validate a caller-owned graph without changing it or the default cache.

    The reference file must match the pinned complete-file SHA-256, revision,
    tree and exact 1,819 SN IDs. Graph and provenance digests additionally pin
    exact sourced labels, ordered edges and source attribution independently of
    the private preparation evidence. Invalid inputs raise ValueError.
    """
    _require(isinstance(data, dict), "Navigation must be an object")
    _require(type(data.get("schema_version")) is int and data["schema_version"] == 1,
             "Unsupported navigation schema")
    provenance = {key: value for key, value in data.items() if key not in {"books", "nodes"}}
    _require(_digest(provenance) == _PROVENANCE_SHA256, "Navigation provenance pin mismatch")
    reference_bytes = Path(reference_path or REFERENCE).read_bytes()
    _require(hashlib.sha256(reference_bytes).hexdigest() == _REFERENCE_SHA256,
             "Pinned reference SHA-256 mismatch")
    reference = _read_json(reference_bytes)
    _require(reference.get("commit") == _BILARA_COMMIT and reference.get("sutta_tree") == _SUTTA_TREE,
             "Pinned reference revision/tree mismatch")
    _require(data["reference"]["sha256"] == _REFERENCE_SHA256, "Navigation reference pin mismatch")
    reference_ids = [unit["id"] for unit in reference["units"] if unit["collection"] == COLLECTION]
    _require(len(reference_ids) == len(set(reference_ids)) == 1819,
             "Expected exactly 1819 unique SN reference IDs")

    nodes, books = data.get("nodes"), data.get("books")
    _require(isinstance(nodes, dict) and len(nodes) == 300, "Expected exactly 300 structural nodes")
    _require(isinstance(books, list) and len(books) == 5
             and all(isinstance(uid, str) for uid in books) and len(set(books)) == 5,
             "Expected five distinct source books")
    for uid, node in nodes.items():
        _require(isinstance(uid, str) and _NODE_UID.fullmatch(uid) is not None,
                 "Invalid structural node ID: " + str(uid))
        _require(isinstance(node, dict) and set(node) == _NODE_KEYS, "Invalid node fields: " + uid)
        parent = node["parent"]
        _require(isinstance(parent, str) and (parent == "sn" or parent in nodes),
                 "Invalid parent: " + uid)
        expected_kind = ("book" if parent == "sn" else "samyutta" if re.fullmatch(r"sn[1-9][0-9]*", uid)
                         else "vagga" if uid.endswith("vagga") else "division")
        _require(node["kind"] == expected_kind, "Invalid node kind: " + uid)
        names = node["names"]
        _require(isinstance(names, dict) and set(names) == {"pli", "en"},
                 "Missing source labels: " + uid)
        _require(all(isinstance(value, str) and value and value.strip() == value for value in names.values()),
                 "Empty or untrimmed source label: " + uid)
        _require(isinstance(node["name_key"], str)
                 and re.fullmatch(r"sn-name:[1-9][0-9]*\." + re.escape(uid), node["name_key"]) is not None,
                 "Invalid source name key: " + uid)
        children = node["children"]
        _require(isinstance(children, list) and children and all(isinstance(child, str) for child in children),
                 "Empty or invalid children: " + uid)
        _require(len(set(children)) == len(children), "Duplicate child: " + uid)

    _require(set(books) == {uid for uid, node in nodes.items() if node["parent"] == "sn"},
             "Book/root membership mismatch")
    _require(Counter(node["kind"] for node in nodes.values())
             == {"book": 5, "samyutta": 56, "vagga": 229, "division": 10},
             "Structural kind counts differ")
    _require({uid for uid, node in nodes.items() if node["kind"] == "samyutta"}
             == {f"sn{number}" for number in range(1, 57)}, "Missing or extra saṃyutta")
    for uid in nodes:
        chain = set()
        current = uid
        while current != "sn":
            _require(current not in chain, "Parent cycle: " + uid)
            chain.add(current)
            current = nodes[current]["parent"]

    reached, terminal_ids, terminal_intervals = set(), [], []
    stack = [(uid, "sn") for uid in reversed(books)]
    while stack:
        uid, parent = stack.pop()
        if uid not in nodes:
            terminal_ids.append(uid)
            terminal_intervals.append(_terminal_interval(uid))
            continue
        _require(uid not in reached, "Duplicate structural membership: " + uid)
        reached.add(uid)
        _require(nodes[uid]["parent"] == parent, "Parent/child disagreement: " + uid)
        stack.extend((child, uid) for child in reversed(nodes[uid]["children"]))
    _require(reached == set(nodes), "Unreachable structural nodes")
    _require(len(terminal_ids) == len(set(terminal_ids)), "Duplicate terminal membership")
    _require(len(terminal_ids) == 1819 and set(terminal_ids) == set(reference_ids),
             "Missing or extra SN reference IDs")
    _require(sum("-" in uid for uid in terminal_ids) == 134, "Grouped reference IDs changed")
    _require(terminal_intervals == sorted(terminal_intervals), "Terminal source order changed")
    for previous, current in zip(terminal_intervals, terminal_intervals[1:]):
        _require(previous[0] != current[0] or previous[2] < current[1],
                 "Overlapping terminal membership")
    _require(_digest({"books": books, "nodes": nodes}) == _GRAPH_SHA256,
             "Exact source graph/name pin mismatch")


def load_samyutta_navigation(
    path: str | Path | None = None, *, reference_path: str | Path | None = None,
) -> dict:
    """Read and validate fresh data; never populate or change the default cache."""
    data = _read_json(Path(path or NAVIGATION).read_bytes())
    validate_samyutta_navigation(data, reference_path=reference_path)
    return data


def _freeze(value):
    if isinstance(value, dict):
        return MappingProxyType({key: _freeze(child) for key, child in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(child) for child in value)
    return value


@lru_cache(maxsize=1)
def _default_data() -> Mapping:
    return _freeze(load_samyutta_navigation())


def _node_id(source_uid: str) -> str:
    return COLLECTION if source_uid == "sn" else COLLECTION + "/" + source_uid


@lru_cache(maxsize=1)
def _thematic_node_templates() -> Mapping:
    data = _default_data()
    result = {}
    stack = list(reversed(data["books"]))
    while stack:
        uid = stack.pop()
        node = data["nodes"][uid]
        pli, english = node["names"]["pli"], node["names"]["en"]
        prefix = f"SN {int(uid[2:])} — " if node["kind"] == "samyutta" else ""
        title = f"{prefix}{pli} ({english})"
        key = _node_id(uid)
        result[key] = {
            "id": key, "title": title, "label": title,
            "tree_title": f"{prefix}{pli} — {english}",
            "route": f"sutta/{COLLECTION}/sections/{uid}/index.html",
            "parent": _node_id(node["parent"]), "order": len(result),
            "description": english, "source_uid": uid, "kind": node["kind"],
            "thematic": True,
        }
        stack.extend(child for child in reversed(node["children"]) if child in data["nodes"])
    return _freeze(result)


def thematic_navigation_nodes() -> dict[str, dict]:
    """Return 300 fresh renderer nodes in source depth-first order.

    Verified source data and renderer templates are cached immutably. Both the
    outer dictionary and every node dictionary are new, so catalog callers may
    change orders or fields independently without triggering more file reads.
    """
    return {key: dict(node) for key, node in _thematic_node_templates().items()}


@lru_cache(maxsize=1)
def _membership_intervals() -> Mapping:
    data = _default_data()
    intervals = {}
    for parent, node in data["nodes"].items():
        for child in node["children"]:
            if child not in data["nodes"]:
                section, first, last = _terminal_interval(child)
                intervals.setdefault(section, []).append((first, last, parent))
    return MappingProxyType({section: tuple(sorted(rows)) for section, rows in intervals.items()})


def _common_ancestor(source_uids: list[str]) -> str:
    nodes = _default_data()["nodes"]
    paths = []
    for uid in dict.fromkeys(source_uids):
        path = [uid]
        while uid != "sn":
            uid = nodes[uid]["parent"]
            path.append(uid)
        paths.append(list(reversed(path)))
    common = "sn"
    for level in zip(*paths):
        if len(set(level)) != 1:
            break
        common = level[0]
    return _node_id(common)


def samyutta_collection(canonical_id: str) -> str | None:
    """Place a site ID using explicit terminal intervals, with visible fallback.

    A discourse range must be wholly covered, including both ends and every
    intervening number. Partial matches fall back to the root. Whole-saṃyutta
    ranges use their source saṃyutta nodes' lowest common ancestor. No input
    interval is expanded into individual IDs, even for very large unknown IDs.
    """
    if not isinstance(canonical_id, str) or len(canonical_id) > 128:
        return None
    match = _SITE_ID.fullmatch(canonical_id.strip())
    if match is None:
        return None
    section, discourse, end = match.groups()
    section = int(section)
    first = int(discourse) if discourse is not None else section
    last = int(end) if end is not None else first
    if section < 1 or first < 1 or last < first:
        return None
    if discourse is None:
        # Bound the join to the 56 explicit source nodes, not the input range.
        members = [f"sn{number}" for number in range(1, 57) if first <= number <= last]
        if len(members) != last - first + 1:
            return COLLECTION
        return _common_ancestor(members)

    cursor, parents = first, []
    for start, stop, parent in _membership_intervals().get(section, ()):
        if stop < cursor:
            continue
        if start > cursor:
            break
        parents.append(parent)
        cursor = stop + 1
        if cursor > last:
            return _common_ancestor(parents)
    return COLLECTION
