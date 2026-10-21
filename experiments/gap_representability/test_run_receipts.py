"""User-run stdlib checks for evidence transport, not reconstruction tests."""
import csv
import tempfile
import unittest
from pathlib import Path

from review_width_study import dominance, inventory_audit
from run_receipts import contained_path, write_csv, write_inventory, write_json


class ReceiptTests(unittest.TestCase):
    def test_missing_binary_is_distinct_from_changed_receipt(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            write_json(root / "summary.json", {"status": "completed"})
            (root / "fields.npz").write_bytes(b"test fixture, not an actual model")
            write_inventory(root)
            (root / "fields.npz").unlink()
            rows, available = inventory_audit(root)
            self.assertTrue(available)
            self.assertEqual({r["path"]: r["state"] for r in rows},
                             {"fields.npz": "missing", "summary.json": "verified"})
            write_json(root / "summary.json", {"status": "changed"})
            rows, _ = inventory_audit(root)
            self.assertEqual(next(r["state"] for r in rows if r["path"] == "summary.json"), "hash_mismatch")

    def test_path_must_stay_in_run(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            self.assertEqual(contained_path(root, "case/metrics.csv"), root.resolve() / "case/metrics.csv")
            with self.assertRaises(ValueError):
                contained_path(root, "../outside.json")

    def test_csv_preserves_failure_only_columns(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "cases.csv"
            write_csv(path, [{"case": "good", "status": "completed"},
                             {"case": "bad", "status": "failed", "error": "missing evidence"}])
            with path.open(encoding="utf-8", newline="") as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[1]["error"], "missing evidence")
            self.assertFalse(path.with_name("cases.csv.tmp").exists())

    def test_no_inventory_is_unverified(self):
        with tempfile.TemporaryDirectory() as folder:
            rows, available = inventory_audit(Path(folder))
            self.assertEqual(rows, [])
            self.assertFalse(available)

    def test_git_newline_conversion_keeps_text_identity(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            path = root / "metrics.csv"
            path.write_bytes(b"method,value\nnodes_27,1\n")
            write_inventory(root)
            path.write_bytes(b"\xef\xbb\xbfmethod,value\r\nnodes_27,1\r\n")
            rows, _ = inventory_audit(root)
            self.assertEqual(rows[0]["state"], "text_equivalent")

    def test_opening_gap_by_erasing_solid_is_not_dominance(self):
        baseline = dict(gap_occupied_fraction=.8, solid_recall=1.,
                        near_wall_solid_recall=1., gap_path_fraction=.1)
        erased = dict(gap_occupied_fraction=0., solid_recall=0.,
                      near_wall_solid_recall=0., gap_path_fraction=1.)
        good = dict(gap_occupied_fraction=0., solid_recall=1.,
                    near_wall_solid_recall=1., gap_path_fraction=1.)
        self.assertEqual(dominance(erased, baseline), "tradeoff")
        self.assertEqual(dominance(good, baseline), "candidate_dominates_on_recorded_probes")
        self.assertEqual(dominance(good, good), "equal_on_recorded_probes")
        self.assertEqual(dominance({}, good), "unavailable")
        self.assertEqual(dominance({**good, "solid_recall": "nan"}, good), "unavailable")


if __name__ == "__main__":
    unittest.main()
