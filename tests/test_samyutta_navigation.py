# SPDX-License-Identifier: 0BSD
"""Focused source-integrity, immutable-cache and SN interval placement checks."""

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools/buddhist_canon_pipeline"))
import samyutta_navigation as sn


class SamyuttaNavigationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = sn.load_samyutta_navigation()
        cls.reference_bytes = sn.REFERENCE.read_bytes()
        reference = json.loads(cls.reference_bytes)
        cls.reference_ids = {row["id"] for row in reference["units"] if row["collection"] == sn.COLLECTION}
        cls.terminal_parents = {
            child: uid for uid, node in cls.data["nodes"].items()
            for child in node["children"] if child not in cls.data["nodes"]
        }

    def test_exact_reference_coverage_and_pinned_hash(self):
        self.assertEqual(hashlib.sha256(self.reference_bytes).hexdigest(),
                         "7db5ea44168eb261e854897d0460e11b9ac832bf141d4dffc702614d118dec7f")
        self.assertEqual(len(self.terminal_parents), 1819)
        self.assertEqual(set(self.terminal_parents), self.reference_ids)
        self.assertEqual(sum("-" in uid for uid in self.terminal_parents), 134)
        self.assertEqual(len(self.data["nodes"]), 300)
        self.assertEqual(len(self.data["books"]), 5)

    def test_renderer_contract_exact_names_routes_and_depth_first_order(self):
        nodes = sn.thematic_navigation_nodes()
        self.assertEqual(len(nodes), 300)
        self.assertEqual([node["order"] for node in nodes.values()], list(range(300)))
        for key, node in nodes.items():
            with self.subTest(key=key):
                uid = node["source_uid"]
                source = self.data["nodes"][uid]
                self.assertEqual(key, "samyutta-nikaya/" + uid)
                self.assertEqual(node["id"], key)
                self.assertEqual(node["kind"], source["kind"])
                self.assertIs(node["thematic"], True)
                self.assertEqual(node["description"], source["names"]["en"])
                self.assertTrue(node["description"])
                self.assertNotIn(" (", node["tree_title"])
                for field in ("title", "label", "tree_title"):
                    self.assertIn(source["names"]["pli"], node[field])
                    self.assertIn(source["names"]["en"], node[field])
                self.assertEqual(node["route"], "sutta/samyutta-nikaya/sections/" + uid + "/index.html")
                parent = source["parent"]
                self.assertEqual(node["parent"], sn.COLLECTION if parent == "sn" else sn.COLLECTION + "/" + parent)
                if parent != "sn":
                    self.assertLess(nodes[node["parent"]]["order"], node["order"])
        expected_order = []

        def walk(uid):
            expected_order.append("samyutta-nikaya/" + uid)
            for child in self.data["nodes"][uid]["children"]:
                if child in self.data["nodes"]:
                    walk(child)

        for book in self.data["books"]:
            walk(book)
        self.assertEqual(list(nodes), expected_order)
        self.assertEqual(nodes["samyutta-nikaya/sn47"]["title"],
                         "SN 47 — Satipaṭṭhānasaṁyutta (Linked Discourses on Mindfulness Meditation)")
        self.assertEqual(nodes["samyutta-nikaya/sn47"]["tree_title"],
                         "SN 47 — Satipaṭṭhānasaṁyutta — Linked Discourses on Mindfulness Meditation")

    def test_mindfulness_acceptance_leaf_and_parent_chain(self):
        nodes = sn.thematic_navigation_nodes()
        leaf = sn.samyutta_collection("SN 47.41")
        self.assertEqual(leaf, "samyutta-nikaya/sn47-amatavagga")
        self.assertEqual(nodes[leaf]["title"], "Amatavagga (The Chapter on Freedom From Death)")
        path = []
        while leaf != sn.COLLECTION:
            path.append(leaf)
            leaf = nodes[leaf]["parent"]
        self.assertEqual(list(reversed(path)), [
            "samyutta-nikaya/sn-mahavaggasamyutta",
            "samyutta-nikaya/sn47",
            "samyutta-nikaya/sn47-amatavagga",
        ])

    def test_every_source_terminal_maps_to_its_exact_explicit_parent(self):
        for uid, parent in self.terminal_parents.items():
            with self.subTest(uid=uid):
                self.assertEqual(sn.samyutta_collection("SN " + uid[2:]), "samyutta-nikaya/" + parent)

    def test_group_endpoints_and_subranges_join_without_rewriting_source_ids(self):
        for uid, parent in self.terminal_parents.items():
            if "-" not in uid:
                continue
            section, interval = uid[2:].split(".")
            first, last = map(int, interval.split("-"))
            for number in {first, (first + last) // 2, last}:
                with self.subTest(uid=uid, number=number):
                    self.assertEqual(sn.samyutta_collection(f"SN {section}.{number}"),
                                     "samyutta-nikaya/" + parent)
        for first in range(93, 214, 11):
            self.assertEqual(sn.samyutta_collection(f"SN 12.{first}-{first + 10}"),
                             "samyutta-nikaya/sn12-sikkhasuttadipeyyalaekadasaka")
        self.assertEqual(self.data["nodes"]["sn12-sikkhasuttadipeyyalaekadasaka"]["children"],
                         ["sn12.93-213"])

    def test_cross_chapter_ranges_use_lowest_common_ancestor(self):
        for identifier, ancestor in (
            ("SN 47.40-41", "sn47"),
            ("SN 47.1-50", "sn47"),
            ("SN 12.83-103", "sn12-antarapeyyala"),
            ("SN 22.1-20", "sn22-mulapannasaka"),
            ("SN 35.1-20", "sn35-pathamapannasaka"),
        ):
            with self.subTest(identifier=identifier):
                self.assertEqual(sn.samyutta_collection(identifier), "samyutta-nikaya/" + ancestor)

    def test_whole_samyuttas_and_book_ranges_use_source_ancestors(self):
        for identifier, expected in (
            ("SN 47", "sn47"), ("SN 30", "sn30"),
            ("SN 1-11", "sn-sagathavaggasamyutta"),
            ("SN 12-21", "sn-nidanavaggasamyutta"),
            ("SN 22-34", "sn-khandhavaggasamyutta"),
            ("SN 35-44", "sn-salayatanavaggasamyutta"),
            ("SN 45-56", "sn-mahavaggasamyutta"),
        ):
            with self.subTest(identifier=identifier):
                self.assertEqual(sn.samyutta_collection(identifier), "samyutta-nikaya/" + expected)
        self.assertEqual(sn.samyutta_collection("SN 1-56"), sn.COLLECTION)

    def test_source_boundaries_are_not_numeric_decades(self):
        # These source groups cross decimal tens and keep their own membership.
        self.assertEqual(sn.samyutta_collection("SN 12.92"), "samyutta-nikaya/sn12-satthusuttadi")
        self.assertEqual(sn.samyutta_collection("SN 12.93"),
                         "samyutta-nikaya/sn12-sikkhasuttadipeyyalaekadasaka")
        self.assertEqual(sn.samyutta_collection("SN 47.62"), "samyutta-nikaya/sn47-gangapeyyalavagga")
        self.assertEqual(sn.samyutta_collection("SN 47.63"), "samyutta-nikaya/sn47-appamadavagga")

    def test_unmatched_and_partially_matched_valid_ids_remain_at_root(self):
        for identifier in (
            "SN 57", "SN 99.1", "SN 35.249", "SN 12.214",
            "SN 47.105", "SN 47.104-105", "SN 56-57",
            "SN 1-999999999999999999999999999",
            "SN 1.1-999999999999999999999999999",
        ):
            with self.subTest(identifier=identifier):
                self.assertEqual(sn.samyutta_collection(identifier), sn.COLLECTION)

    def test_partial_coverage_with_an_internal_gap_falls_back_to_root(self):
        intervals = {47: ((1, 2, "sn47-ambapalivagga"), (4, 5, "sn47-ambapalivagga"))}
        with patch.object(sn, "_membership_intervals", return_value=intervals):
            self.assertEqual(sn.samyutta_collection("SN 47.1-5"), sn.COLLECTION)

    def test_malformed_non_sn_and_reversed_ids_return_none(self):
        for identifier in (
            "", "AN 47.41", "MN 1", "sn47.41", "sn 47.41", "SN47.41",
            "SN 0", "SN 0.1", "SN 47.0", "SN 47.0-1", "SN 47.41-40",
            "SN 47-46", "SN 47.41.1", "SN 47.41-48.1", "SN -1",
            "SN 47.41 trailing", "SN ４７.４１", "../SN 47.41", None, 47,
            "SN " + "9" * 129,
        ):
            with self.subTest(identifier=identifier):
                self.assertIsNone(sn.samyutta_collection(identifier))
        for identifier in (" SN 047.041 ", "SN\t47.41", "SN 47.41–42"):
            self.assertEqual(sn.samyutta_collection(identifier), "samyutta-nikaya/sn47-amatavagga")

    def test_renderer_dicts_are_independent_and_calls_do_not_reread_files(self):
        first = sn.thematic_navigation_nodes()
        original = deepcopy(first)
        first["samyutta-nikaya/sn47"]["order"] = -1
        first["samyutta-nikaya/sn47"]["title"] = "Caller-local title"
        first.pop("samyutta-nikaya/sn1")
        with patch.object(Path, "read_bytes", side_effect=AssertionError("Unexpected repeated file read")):
            for _ in range(3):
                second = sn.thematic_navigation_nodes()
                self.assertEqual(second, original)
                self.assertIsNot(second["samyutta-nikaya/sn47"], first["samyutta-nikaya/sn47"])
                self.assertEqual(sn.samyutta_collection("SN 47.41"), "samyutta-nikaya/sn47-amatavagga")

    def test_cached_source_is_deeply_immutable(self):
        data = sn._default_data()
        with self.assertRaises(TypeError):
            data["nodes"]["sn47"]["names"]["en"] = "Changed"
        with self.assertRaises(TypeError):
            data["nodes"]["sn47"]["children"][0] = "Changed"

    def test_load_and_validate_are_independent_of_caches_and_caller_mutations(self):
        original = sn.thematic_navigation_nodes()
        cache_before = sn._default_data.cache_info()
        loaded = sn.load_samyutta_navigation()
        unchanged = deepcopy(loaded)
        self.assertIsNone(sn.validate_samyutta_navigation(loaded))
        self.assertEqual(loaded, unchanged)
        loaded["nodes"]["sn47"]["names"]["en"] = "Caller-local name"
        with self.assertRaisesRegex(ValueError, "graph/name pin"):
            sn.validate_samyutta_navigation(loaded)
        self.assertEqual(sn._default_data.cache_info(), cache_before)
        self.assertEqual(sn.thematic_navigation_nodes(), original)
        self.assertEqual(sn.load_samyutta_navigation(), self.data)

    def test_changed_reference_file_hash_is_rejected(self):
        with patch.object(Path, "read_bytes", return_value=self.reference_bytes + b"\n"):
            with self.assertRaisesRegex(ValueError, "reference SHA-256"):
                sn.validate_samyutta_navigation(self.data, reference_path="changed-reference.json")

    def test_custom_load_path_is_read_and_validated_without_cache_changes(self):
        virtual = Path("in-memory-samyutta-navigation.json")
        payload = json.dumps(self.data, ensure_ascii=False).encode()
        read_bytes = Path.read_bytes

        def read(path):
            return payload if path == virtual else read_bytes(path)

        before = sn._default_data.cache_info()
        with patch.object(Path, "read_bytes", autospec=True, side_effect=read):
            self.assertEqual(sn.load_samyutta_navigation(virtual, reference_path=sn.REFERENCE), self.data)
        self.assertEqual(sn._default_data.cache_info(), before)

    def test_duplicate_json_object_keys_are_rejected_before_collapsing(self):
        payload = json.dumps(self.data, ensure_ascii=False).replace('"sn47": {', '"sn47": {}, "sn47": {', 1).encode()
        with patch.object(Path, "read_bytes", return_value=payload):
            with self.assertRaisesRegex(ValueError, "Duplicate JSON key: sn47"):
                sn.load_samyutta_navigation("duplicate-node.json")

    def test_invalid_graphs_and_provenance_are_rejected_without_mutation(self):
        faults = (
            "missing-node", "missing-terminal", "extra-terminal", "duplicate-terminal",
            "duplicate-child", "unknown-parent", "wrong-parent", "parent-cycle", "unreachable",
            "missing-label", "empty-label", "changed-label", "untrimmed-label", "name-key",
            "changed-group", "reversed-group", "changed-order", "wrong-kind", "body-field",
            "source-hash", "private-status", "schema", "book-order",
        )
        for fault in faults:
            broken = deepcopy(self.data)
            nodes = broken["nodes"]
            leaf = nodes["sn47-amatavagga"]
            if fault == "missing-node":
                del nodes["sn47-amatavagga"]
            elif fault == "missing-terminal":
                leaf["children"].pop()
            elif fault == "extra-terminal":
                leaf["children"][-1] = "sn47.999"
            elif fault == "duplicate-terminal":
                nodes["sn47-ambapalivagga"]["children"].append("sn47.41")
            elif fault == "duplicate-child":
                leaf["children"].append("sn47.41")
            elif fault == "unknown-parent":
                leaf["parent"] = "sn-missing"
            elif fault == "wrong-parent":
                leaf["parent"] = "sn46"
            elif fault == "parent-cycle":
                leaf["parent"] = "sn47-amatavagga"
            elif fault == "unreachable":
                nodes["sn47"]["children"].remove("sn47-amatavagga")
            elif fault == "missing-label":
                del leaf["names"]["en"]
            elif fault == "empty-label":
                leaf["names"]["en"] = ""
            elif fault == "changed-label":
                leaf["names"]["en"] = "Invented chapter name"
            elif fault == "untrimmed-label":
                leaf["names"]["pli"] += " "
            elif fault == "name-key":
                leaf["name_key"] = "sn-name:999.sn47"
            elif fault == "changed-group":
                nodes["sn12-sikkhasuttadipeyyalaekadasaka"]["children"] = ["sn12.93-212"]
            elif fault == "reversed-group":
                nodes["sn12-sikkhasuttadipeyyalaekadasaka"]["children"] = ["sn12.213-93"]
            elif fault == "changed-order":
                leaf["children"].reverse()
            elif fault == "wrong-kind":
                leaf["kind"] = "book"
            elif fault == "body-field":
                leaf["body"] = "Unpermitted field"
            elif fault == "source-hash":
                broken["sources"]["structure"]["sha256"] = "0" * 64
            elif fault == "private-status":
                broken["status"] = "private draft"
            elif fault == "schema":
                broken["schema_version"] = True
            elif fault == "book-order":
                broken["books"].reverse()
            unchanged = deepcopy(broken)
            with self.subTest(fault=fault):
                with self.assertRaises(ValueError):
                    sn.validate_samyutta_navigation(broken)
                self.assertEqual(broken, unchanged)

    def test_public_metadata_contains_only_bounded_names_edges_and_provenance(self):
        serialized = json.dumps(self.data, ensure_ascii=False)
        for private_marker in ("/home/", "/tmp/", "private draft", "unverified", "status"):
            self.assertNotIn(private_marker, serialized)
        self.assertEqual(self.data["sources"]["en_names"]["translator"], "Sujato")
        self.assertEqual(self.data["rights"]["names"]["license"], "CC0-1.0")
        for source in self.data["sources"].values():
            self.assertEqual(source["url"], f"{source['repository']}/blob/{source['commit']}/{source['path']}")


if __name__ == "__main__":
    unittest.main()
