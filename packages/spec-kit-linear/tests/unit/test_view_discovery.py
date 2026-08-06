from __future__ import annotations

import unittest


from spec_kit_linear.errors import AppError
from spec_kit_linear.linear_client import RemoteSharedView
from spec_kit_linear.view_discovery import conventional_view_name, resolve_shared_views_by_name


class _FakeViewClient:
    def __init__(self, views: tuple[RemoteSharedView, ...] = ()) -> None:
        self._views = views

    def find_shared_views_by_name(self, name: str) -> tuple[RemoteSharedView, ...]:
        return tuple(item for item in self._views if item.name == name)


SLUG = "spec-kit"


class ViewDiscoveryTests(unittest.TestCase):
    def test_conventional_names(self) -> None:
        self.assertEqual(conventional_view_name(SLUG, "Features"), "spec-kit / Features")
        self.assertEqual(conventional_view_name(SLUG, "Work"), "spec-kit / Work")

    def test_zero_matches_warns_and_leaves_fields_unset(self) -> None:
        client = _FakeViewClient()

        result = resolve_shared_views_by_name(client, SLUG)

        self.assertEqual(result.resolved, {})
        self.assertEqual(len(result.diagnostics), 2)
        self.assertTrue(all(d.code == "shared_view_missing" and d.severity == "warning" for d in result.diagnostics))

    def test_single_match_per_view_is_adopted(self) -> None:
        views = (
            RemoteSharedView(id="view-project", name="spec-kit / Features", type="project", shared=True),
            RemoteSharedView(id="view-issue", name="spec-kit / Work", type="issue", shared=True),
        )
        client = _FakeViewClient(views)

        result = resolve_shared_views_by_name(client, SLUG)

        self.assertEqual(result.resolved, {"project_view_id": "view-project", "issue_view_id": "view-issue"})
        self.assertTrue(all(d.code == "shared_view_adopted" for d in result.diagnostics))

    def test_ambiguous_matches_always_abort(self) -> None:
        views = (
            RemoteSharedView(id="view-a", name="spec-kit / Features", type="project", shared=True),
            RemoteSharedView(id="view-b", name="spec-kit / Features", type="project", shared=True),
        )
        client = _FakeViewClient(views)

        with self.assertRaises(AppError) as raised:
            resolve_shared_views_by_name(client, SLUG)

        self.assertEqual(raised.exception.code, 6)
        self.assertEqual(raised.exception.diagnostics[0].code, "shared_view_ambiguous")

    def test_wrong_model_type_aborts(self) -> None:
        views = (RemoteSharedView(id="view-a", name="spec-kit / Features", type="issue", shared=True),)
        client = _FakeViewClient(views)

        with self.assertRaises(AppError) as raised:
            resolve_shared_views_by_name(client, SLUG)

        self.assertEqual(raised.exception.code, 6)
        self.assertEqual(raised.exception.diagnostics[0].code, "shared_view_type_mismatch")

    def test_not_shared_aborts(self) -> None:
        views = (RemoteSharedView(id="view-a", name="spec-kit / Features", type="project", shared=False),)
        client = _FakeViewClient(views)

        with self.assertRaises(AppError) as raised:
            resolve_shared_views_by_name(client, SLUG)

        self.assertEqual(raised.exception.code, 6)
        self.assertEqual(raised.exception.diagnostics[0].code, "shared_view_type_mismatch")


if __name__ == "__main__":
    unittest.main()
