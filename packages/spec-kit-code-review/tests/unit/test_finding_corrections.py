"""Focused parser contract for lossless category recovery."""

import unittest
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from spec_kit_code_review.errors import EXIT_ENVIRONMENT, AppError
from spec_kit_code_review.finding_corrections import digest, finish, parse_bytes, prepare, verify_history
from spec_kit_code_review.finding_corrections import validate_attempt
from spec_kit_code_review.session import ReviewSession, load_session


class CorrectionTests(unittest.TestCase):

    def _session(self, root: Path) -> ReviewSession:
        return ReviewSession(root, {
            "phase": "open", "findings_attempt_id": "attempt-1", "candidate_id": "c" * 64,
            "packet_sha256": "p" * 64, "config_sha256": "q" * 64,
            "packet": {"inventory_sha256": "i" * 64},
        })

    def _documents(self):
        finding = {
            "path": "src/feature.py", "start_line": 1, "end_line": 1, "severity": "blocking",
            "category": "vibes", "title": "title", "content": "content", "optional": None,
            "suggestion_code": "return validated",
        }
        # Keep the document fields deliberately varied: category recovery must
        # compare their JSON types, presence, and ordering exactly.
        finding.pop("optional")
        second = {**finding, "category": "correctness", "title": "second"}
        return {"findings": [finding, second], "coverage": {"reads": ["one"], "covered": True}}

    def _prepared(self, root: Path):
        session = self._session(root)
        document = self._documents()
        prepare(session, json.dumps(document).encode(), document)
        corrected = json.loads(json.dumps(document))
        corrected["findings"][0]["category"] = "security"
        prepare(session, json.dumps(corrected).encode(), corrected)
        attempt = root / "finding-corrections" / "attempt-1"
        return session, attempt

    def test_category_only_prepare_preserves_all_other_document_fields(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            session = self._session(root)
            original = self._documents()
            raw = json.dumps(original, indent=2).encode()
            prepare(session, raw, original)
            corrected = json.loads(raw)
            corrected["findings"][0]["category"] = "security"
            record, submitted = prepare(session, json.dumps(corrected, sort_keys=True).encode(), corrected)
            self.assertEqual(record["changed_categories"][0]["index"], 1)
            self.assertEqual((root / "finding-corrections" / "attempt-1" / "original.json").read_bytes(), raw)
            self.assertEqual(record["submitted_sha256"], submitted)

    def test_missing_category_to_null_records_presence_change(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            session = self._session(root)
            original = self._documents()
            original["findings"][0].pop("category")
            prepare(session, json.dumps(original).encode(), original)
            corrected = json.loads(json.dumps(original))
            corrected["findings"][0]["category"] = None
            record, _ = prepare(session, json.dumps(corrected).encode(), corrected)
            change = record["changed_categories"][0]
            self.assertFalse(change["old_present"])
            self.assertTrue(change["new_present"])

    def test_prepare_rejects_type_presence_and_structure_changes(self) -> None:
        mutations = {
            "missing": lambda doc: doc["findings"][0].pop("suggestion_code", None),
            "null": lambda doc: doc["findings"][0].update(existing_code=None),
            "bool": lambda doc: doc["findings"][0].update(start_line=True),
            "number": lambda doc: doc["findings"][0].update(content=7),
            "valid_category": lambda doc: doc["findings"][1].update(category="security"),
            "reorder": lambda doc: doc.update(findings=list(reversed(doc["findings"]))),
            "addition": lambda doc: doc["findings"].append(dict(doc["findings"][0])),
            "deletion": lambda doc: doc["findings"].pop(),
            "coverage": lambda doc: doc["coverage"].update(extra="changed"),
        }
        for name, mutate in mutations.items():
            with self.subTest(name=name), TemporaryDirectory() as temporary:
                root = Path(temporary)
                session = self._session(root)
                original = self._documents()
                raw = json.dumps(original).encode()
                prepare(session, raw, original)
                corrected = json.loads(raw)
                corrected["findings"][0]["category"] = "security"
                mutate(corrected)
                with self.assertRaises(AppError) as caught:
                    prepare(session, json.dumps(corrected).encode(), corrected)
                self.assertEqual(caught.exception.diagnostics[0].code, "correction_non_category_change")
                records = list((root / "finding-corrections" / "attempt-1").glob("*.json"))
                self.assertTrue(any(json.loads(path.read_text()).get("changed_categories") for path in records))

    def test_history_rejects_tampered_original_record_and_unindexed_digest(self) -> None:
        for mutation in ("original", "record", "unindexed", "binding"):
            with self.subTest(mutation=mutation), TemporaryDirectory() as temporary:
                root = Path(temporary)
                session, attempt = self._prepared(root)
                record = next(attempt.glob("[0-9a-f]*.json"))
                if mutation == "original":
                    (attempt / "original.json").write_bytes(b"tampered")
                elif mutation == "record":
                    record.write_bytes(record.read_bytes() + b" ")
                elif mutation == "binding":
                    payload = json.loads(record.read_text(encoding="utf-8"))
                    payload["candidate_id"] = "d" * 64
                    record.write_text(json.dumps(payload), encoding="utf-8")
                    session.payload["correction_record_digests"][record.stem] = digest(record.read_bytes())
                else:
                    extra = attempt / ("f" * 64 + ".json")
                    extra.write_text("{}", encoding="utf-8")
                with self.assertRaises(AppError) as caught:
                    verify_history(session)
                self.assertIn(caught.exception.diagnostics[0].code, {"correction_evidence_tampered", "correction_record_unreadable"})

    def test_history_rejects_symlinked_evidence_paths(self) -> None:
        for target_name in ("parent", "attempt", "original", "record"):
            with self.subTest(target=target_name), TemporaryDirectory() as temporary:
                root = Path(temporary)
                session, attempt = self._prepared(root)
                record = next(attempt.glob("[0-9a-f]*.json"))
                if target_name == "parent":
                    real = root / "finding-corrections-real"
                    (root / "finding-corrections").rename(real)
                    (root / "finding-corrections").symlink_to(real, target_is_directory=True)
                elif target_name == "attempt":
                    real = root / "attempt-real"
                    attempt.rename(real)
                    attempt.symlink_to(real, target_is_directory=True)
                else:
                    source = root / f"{target_name}-target.json"
                    source.write_bytes((attempt / ("original.json" if target_name == "original" else record.name)).read_bytes())
                    linked = attempt / ("original.json" if target_name == "original" else record.name)
                    linked.unlink()
                    linked.symlink_to(source)
                with self.assertRaises(AppError):
                    verify_history(session)

    def test_duplicate_keys_fail_closed(self):
        with self.assertRaises(AppError):
            parse_bytes(b'{"findings":[],"findings":[]}')

    def test_repeating_the_same_submitted_digest_reuses_its_record(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            session = self._session(root)
            original = self._documents()
            prepare(session, json.dumps(original).encode(), original)
            corrected = json.loads(json.dumps(original))
            corrected["findings"][0]["category"] = "security"
            raw = json.dumps(corrected).encode()
            _, submitted = prepare(session, raw, corrected)
            session = load_session(session.path)
            pending, _ = prepare(session, raw, corrected)
            self.assertEqual(pending["status"], "pending")
            finish(session, submitted, status="validated")
            session = load_session(session.path)
            self.assertEqual(session.payload["correction_accepted_digest"], submitted)
            count = len(list((root / "finding-corrections" / "attempt-1").glob("[0-9a-f]*.json")))
            prepare(session, raw, corrected)
            records = list((root / "finding-corrections" / "attempt-1").glob("[0-9a-f]*.json"))
            self.assertEqual(len(records), count)

    def test_missing_original_and_record_are_diagnosed(self) -> None:
        for missing in ("original", "record"):
            with self.subTest(missing=missing), TemporaryDirectory() as temporary:
                root = Path(temporary)
                session, attempt = self._prepared(root)
                target = attempt / ("original.json" if missing == "original" else next(attempt.glob("[0-9a-f]*.json")).name)
                target.unlink()
                with self.assertRaises(AppError) as caught:
                    verify_history(session)
                self.assertIn(caught.exception.diagnostics[0].code, {"correction_evidence_tampered", "correction_record_unreadable"})

    def test_record_written_before_index_failure_cannot_accept_a_different_digest(self) -> None:
        from unittest import mock

        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            session = self._session(root)
            original = self._documents()
            prepare(session, json.dumps(original).encode(), original)
            first = json.loads(json.dumps(original))
            first["findings"][0]["category"] = "security"
            with mock.patch.object(session, "write", side_effect=OSError("index unavailable")):
                with self.assertRaises(OSError):
                    prepare(session, json.dumps(first).encode(), first)
            session = load_session(session.path)
            second = json.loads(json.dumps(original))
            second["findings"][0]["category"] = "contract"
            with self.assertRaises(AppError) as caught:
                prepare(session, json.dumps(second).encode(), second)
            self.assertEqual(caught.exception.diagnostics[0].code, "correction_evidence_tampered")

    def test_unbound_current_attempt_evidence_blocks_every_submission(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            session = self._session(root)
            attempt = root / "finding-corrections" / "attempt-1"
            attempt.mkdir(parents=True)
            original = attempt / "original.json"
            original.write_bytes(b'{"findings":[]}')

            with self.assertRaises(AppError) as caught:
                validate_attempt(session)

            self.assertEqual(caught.exception.code, EXIT_ENVIRONMENT)
            self.assertEqual(caught.exception.diagnostics[0].code, "correction_evidence_tampered")
            self.assertEqual(original.read_bytes(), b'{"findings":[]}')
