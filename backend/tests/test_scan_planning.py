"""Unit tests for the pure scan-planning helpers in app.services.scanner.

scan_library() interleaves these steps with DB sessions, which makes them hard
to exercise end-to-end. The helpers are pure, so they are tested directly.
"""
import os
from datetime import datetime

from app.models.enums import MediaType
from app.services.scanner import (
    classify_missing,
    index_existing_rows,
    plan_scan_changes,
)


def row(mid, path, mtime, size, missing=False, deleted=False, media_type=MediaType.LOCAL):
    """Row shape: (id, file_path, mtime, size, file_missing, media_type, is_deleted)."""
    return (mid, path, mtime, size, missing, media_type, deleted)


def scanned(path, name, mtime, size):
    """File dict as `scan_directory` produces it: native separators (os.walk)."""
    return {
        "file_path": os.path.normpath(path),
        "file_name": name,
        "file_modified_at": mtime,
        "file_size": size,
    }


T0 = datetime(2024, 1, 1, 12, 0, 0)
T1 = datetime(2024, 6, 1, 12, 0, 0)


class TestIndexExistingRows:
    def test_keys_by_normalized_path_and_keeps_original(self):
        raw = os.path.join("F:", "movies", "a.mp4")
        index = index_existing_rows([row(1, raw, T0, 100)])
        norm = os.path.normpath(raw)
        assert list(index.by_path) == [norm]
        assert index.by_path[norm]["orig_path"] == raw

    def test_missing_rows_are_indexed_by_basename(self):
        index = index_existing_rows([
            row(1, os.path.join("F:", "a.mp4"), T0, 100, missing=True),
            row(2, os.path.join("F:", "b.mp4"), T0, 100),
        ])
        assert list(index.missing_by_name) == ["a.mp4"]
        assert index.missing_by_name["a.mp4"][0]["id"] == 1

    def test_soft_deleted_rows_are_not_relink_candidates(self):
        index = index_existing_rows([
            row(1, os.path.join("F:", "a.mp4"), T0, 100, missing=True, deleted=True),
        ])
        assert index.missing_by_name == {}

    def test_empty_result(self):
        index = index_existing_rows([])
        assert index.by_path == {} and index.missing_by_name == {}


class TestPlanScanChanges:
    def test_unseen_file_is_created(self):
        plan = plan_scan_changes([scanned("F:/a.mp4", "a.mp4", T0, 100)], index_existing_rows([]), 7)
        assert plan.new_count == 1
        assert len(plan.to_create) == 1
        media = plan.to_create[0]
        assert (media.library_id, media.title, media.file_name) == (7, "a", "a.mp4")
        assert media.media_type == MediaType.LOCAL

    def test_unchanged_file_produces_nothing(self):
        index = index_existing_rows([row(1, "F:/a.mp4", T0, 100)])
        plan = plan_scan_changes([scanned("F:/a.mp4", "a.mp4", T0, 100)], index, 7)
        assert (plan.new_count, plan.relink_count) == (0, 0)
        assert plan.to_update == [] and plan.to_create == []

    def test_changed_mtime_is_queued_for_update(self):
        index = index_existing_rows([row(1, "F:/a.mp4", T0, 100)])
        plan = plan_scan_changes([scanned("F:/a.mp4", "a.mp4", T1, 100)], index, 7)
        assert plan.to_update == [(1, T1, 100)]
        assert plan.to_create == []

    def test_same_path_twice_counts_once(self):
        # The second occurrence is already in seen_paths and has no existing row,
        # so it must not be created or updated again.
        plan = plan_scan_changes(
            [scanned("F:/a.mp4", "a.mp4", T0, 100), scanned("F:/a.mp4", "a.mp4", T0, 100)],
            index_existing_rows([]),
            7,
        )
        assert plan.new_count == 1
        assert len(plan.to_create) == 1

    def test_missing_record_with_same_name_is_relinked(self):
        index = index_existing_rows([row(1, "F:/old/a.mp4", T0, 100, missing=True)])
        plan = plan_scan_changes([scanned("F:/new/a.mp4", "a.mp4", T1, 100)], index, 7)
        assert plan.relink_count == 1
        assert plan.new_count == 0
        assert plan.to_relink[1] == {
            "file_path": os.path.normpath("F:/new/a.mp4"),
            "file_size": 100,
            "file_modified_at": T1,
        }

    def test_relink_prefers_size_match(self):
        index = index_existing_rows([
            row(1, "F:/old/a.mp4", T0, 111, missing=True),
            row(2, "F:/old2/a.mp4", T0, 100, missing=True),
        ])
        plan = plan_scan_changes([scanned("F:/new/a.mp4", "a.mp4", T1, 100)], index, 7)
        assert list(plan.to_relink) == [2]

    def test_one_file_relinks_one_record(self):
        index = index_existing_rows([
            row(1, "F:/old/a.mp4", T0, 100, missing=True),
            row(2, "F:/old2/a.mp4", T0, 100, missing=True),
        ])
        plan = plan_scan_changes(
            [
                scanned("F:/new/a.mp4", "a.mp4", T1, 100),
                scanned("F:/new2/a.mp4", "a.mp4", T1, 100),
            ],
            index,
            7,
        )
        assert plan.relink_count == 2
        assert sorted(plan.to_relink) == [1, 2]
        assert plan.new_count == 0


class TestClassifyMissing:
    def test_vanished_file_becomes_missing(self):
        index = index_existing_rows([row(1, "F:/a.mp4", T0, 100)])
        missing, restored = classify_missing(index, set(), set())
        assert (missing, restored) == ([1], [])

    def test_reappeared_file_becomes_restored(self):
        index = index_existing_rows([row(1, "F:/a.mp4", T0, 100, missing=True)])
        # scanned_paths come from scan_directory → native separators
        missing, restored = classify_missing(index, {os.path.normpath("F:/a.mp4")}, set())
        assert (missing, restored) == ([], [1])

    def test_already_missing_stays_out_of_missing_ids(self):
        index = index_existing_rows([row(1, "F:/a.mp4", T0, 100, missing=True)])
        missing, restored = classify_missing(index, set(), set())
        assert (missing, restored) == ([], [])

    def test_soft_deleted_rows_are_ignored(self):
        index = index_existing_rows([row(1, "F:/a.mp4", T0, 100, deleted=True)])
        assert classify_missing(index, set(), set()) == ([], [])

    def test_relinked_rows_are_skipped(self):
        index = index_existing_rows([row(1, "F:/old/a.mp4", T0, 100)])
        assert classify_missing(index, set(), {1}) == ([], [])
