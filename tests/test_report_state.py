"""State-transition tests; all writes are confined to temporary directories."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/validate-report.py"
SPEC = importlib.util.spec_from_file_location("report_state", SCRIPT)
app = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(app)


class ReportStateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        app.atomic(self.root / "state/checkpoint.json", app.encode(app.INITIAL))
        app.atomic(self.root / "state/collected-items.json", app.encode(app.EMPTY_INDEX))
        app.atomic(self.root / "config/sources.yaml", app.encode({"initial_lookback_days": 7, "overlap_days": 2}))

    def draft(self, cutoff="2026-11-18T09:00:00+08:00", event="v1", empty=False):
        started = app.begin(self.root, cutoff)
        draft = Path(started["draft"])
        m = app.read(draft / "manifest.json")
        m["sections"] = {s: {"status": "complete", "note": "Checked test fixture."} for s in app.SECTIONS}
        m["search_log"] = [{"section": s, "query": "fixture query", "searched_at": app.now(),
                            "status": "ok", "urls": ["https://example.org/paper"], "note": "Inspected fixture."}
                           for s in app.SECTIONS]
        item = {"id": "fixture", "work_id": "org:fixture", "event_id": event, "section": "research",
                "title": "Fixture paper", "published_at": "2026-11-18", "date_source": "https://example.org/paper",
                "change_summary": "New experiment " + event, "late_discovery": False, "late_reason": "",
                "sources": [{"url": "https://example.org/paper", "accessed_at": app.now(), "kind": "primary",
                             "evidence_level": "full_text", "claims": [{"claim": "Fixture fact", "locator": "Table 1"}]}]}
        m["items"] = [] if empty else [item]
        body = f"# Test report\n\n{m['window']['start']} to {m['window']['end']}\n\n"
        body += "## 具身学术研究\n\n"
        if not empty:
            body += "<!-- item:fixture -->\n### Fixture\n\n" + (
                "This synthetic example describes a method, the observed evidence, its limitations, "
                "and a proposed follow-up experiment. [Source](https://example.org/paper)\n\n")
        body += "## 开源项目与数据集\n\nNo qualifying fixture.\n\n## AI 行业重要动态\n\nNo qualifying fixture.\n"
        app.atomic(draft / "manifest.json", app.encode(m))
        app.atomic(draft / "report.md", body.encode("utf-8"))
        return draft

    def mutate(self, draft, fn):
        m = app.read(draft / "manifest.json")
        fn(m)
        app.atomic(draft / "manifest.json", app.encode(m))

    def test_initial_and_commit(self):
        self.assertEqual(app.validate(self.root)[0], app.INITIAL)
        draft = self.draft()
        rid = app.finalize(self.root, draft)
        cp, index = app.validate(self.root)
        self.assertEqual(cp["last_report_id"], rid)
        self.assertEqual(cp["covered_until"], "2026-11-18T09:00:00+08:00")
        self.assertEqual(len(index["items"]), 1)

    def test_repeat_event_rejected_without_advancing_state(self):
        app.finalize(self.root, self.draft())
        before = (self.root / "state/checkpoint.json").read_bytes()
        second = self.draft("2026-11-18T10:00:00+08:00")
        with self.assertRaisesRegex(app.Invalid, "already reported event"):
            app.finalize(self.root, second)
        self.assertEqual(before, (self.root / "state/checkpoint.json").read_bytes())
        app.abort(self.root, "duplicate candidate removed")
        app.validate(self.root)

    def test_new_event_same_work_same_day_allowed(self):
        first = app.finalize(self.root, self.draft())
        body = (self.root / "reports" / (first + ".md")).read_bytes()
        second = self.draft("2026-11-18T10:00:00+08:00", event="code-release")
        manifest = app.read(second / "manifest.json")
        self.assertEqual(manifest["window"]["start"], "2026-11-18T09:00:00+08:00")
        self.assertEqual(manifest["window"]["search_start"], "2026-11-16T09:00:00+08:00")
        app.finalize(self.root, second)
        cp, index = app.validate(self.root)
        self.assertEqual(len(cp["reports"]), 2)
        self.assertEqual(len(index["items"]), 2)
        self.assertEqual(body, (self.root / "reports" / (first + ".md")).read_bytes())

    def test_complete_search_with_no_new_items_is_valid(self):
        app.finalize(self.root, self.draft(empty=True))
        self.assertEqual(app.validate(self.root)[1]["items"], [])

    def test_partial_search_cannot_commit(self):
        draft = self.draft()
        self.mutate(draft, lambda m: m["sections"]["industry"].update(status="partial"))
        with self.assertRaisesRegex(app.Invalid, "incomplete search"):
            app.finalize(self.root, draft)
        self.assertIsNone(app.read(self.root / "state/checkpoint.json")["covered_until"])

    def test_missing_citation_cannot_commit(self):
        draft = self.draft()
        path = draft / "report.md"
        path.write_text(path.read_text(encoding="utf-8").replace("https://example.org/paper", "https://example.org/other"), encoding="utf-8")
        with self.assertRaisesRegex(app.Invalid, "source absent"):
            app.finalize(self.root, draft)

    def test_future_item_and_unmarked_backfill_rejected(self):
        draft = self.draft()
        for published, error in [("2026-11-20", "future-dated"), ("2026-10-01", "late_discovery")]:
            with self.subTest(published=published):
                self.mutate(draft, lambda m: m["items"][0].update(published_at=published))
                with self.assertRaisesRegex(app.Invalid, error):
                    app.candidate(self.root, draft)
        self.mutate(draft, lambda m: m["items"][0].update(late_discovery=True, late_reason="Delayed discovery"))
        app.finalize(self.root, draft)

    def test_report_tampering_detected(self):
        rid = app.finalize(self.root, self.draft())
        path = self.root / "reports" / (rid + ".md")
        with path.open("a", encoding="utf-8") as out:
            out.write("Unexpected change")
        with self.assertRaisesRegex(app.Invalid, "hash mismatch"):
            app.validate(self.root)

    def test_active_run_and_command_lock_block_concurrency(self):
        self.draft()
        with self.assertRaisesRegex(app.Invalid, "already active"):
            app.begin(self.root)
        with app.command_lock(self.root):
            with self.assertRaisesRegex(app.Invalid, "command locked"):
                with app.command_lock(self.root):
                    self.fail("lock was bypassed")

    def test_abort_preserves_state_and_history(self):
        draft = self.draft()
        rid = app.abort(self.root, "Search provider unavailable")
        self.assertTrue((draft / "report.md").exists())
        self.assertTrue((self.root / "state/failures" / (rid + ".json")).exists())
        self.assertEqual(app.validate(self.root)[0], app.INITIAL)

    def test_crash_at_every_commit_write_is_recoverable(self):
        draft = self.draft()
        tx = app.candidate(self.root, draft)
        rid = tx["manifest"]["report_id"]
        original = app.atomic
        paths = ["reports/" + rid + ".md", "reports/" + rid + ".json",
                 "state/collected-items.json", "state/checkpoint.json"]
        for fail_path in paths:
            with self.subTest(fail_path=fail_path), tempfile.TemporaryDirectory() as sandbox:
                root = Path(sandbox)
                original(root / "state/checkpoint.json", (self.root / "state/checkpoint.json").read_bytes())
                original(root / "state/collected-items.json", app.encode(app.EMPTY_INDEX))
                original(root / "state/pending.json", app.encode(tx))

                def interrupted(path, data):
                    original(path, data)
                    if path == root / fail_path:
                        raise OSError("simulated interruption after write")

                with patch.object(app, "atomic", side_effect=interrupted):
                    with self.assertRaisesRegex(OSError, "simulated"):
                        app.replay(root, tx)
                with self.assertRaisesRegex(app.Invalid, "unfinished commit"):
                    app.validate(root)
                app.recover(root)
                self.assertEqual(len(app.validate(root)[1]["items"]), 1)
                self.assertEqual(app.recover(root), "no pending transaction")

    def test_canonical_arxiv_and_tracking_urls(self):
        self.assertEqual(app.canonical_url("https://arxiv.org/pdf/2611.21607v2.pdf"),
                         app.canonical_url("https://arxiv.org/html/2611.21607v1?utm_source=x"))
        self.assertEqual(app.canonical_url("https://example.org/paper/?utm_source=x#top"), "https://example.org/paper")

    def test_identity_change_via_arxiv_url_variant_rejected(self):
        draft = self.draft()
        self.mutate(draft, lambda m: m["items"][0].update(work_id="arxiv:2611.21607"))
        app.finalize(self.root, draft)
        second = self.draft("2026-11-18T10:00:00+08:00", event="v2")
        with self.assertRaisesRegex(app.Invalid, "identity changed"):
            app.finalize(self.root, second)


if __name__ == "__main__":
    unittest.main()
