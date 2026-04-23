
from app.domains.knowledge.pipeline import (
    _build_structure_index,
    _patch_structure_index,
    _select_meaningful_dirs,
)


class TestSelectMeaningfulDirs:
    def test_flat_repo_groups_root_files(self):
        result = _select_meaningful_dirs(["README.md", "pyproject.toml"])
        assert result == {"_root": ["README.md", "pyproject.toml"]}

    def test_course_repo_keeps_weeks_separate(self):
        result = _select_meaningful_dirs(
            [
                "week1/README.md",
                "week2/README.md",
                "week3/day1.md",
                "week4/day2.md",
            ]
        )
        assert "week1" in result
        assert "week2" in result
        assert "week3" in result
        assert "week4" in result

    def test_pass_through_dirs_group_by_actual_parent(self):
        result = _select_meaningful_dirs(
            [
                "src/api/routes.py",
                "src/models/user.py",
            ]
        )
        assert set(result.keys()) == {"src/api", "src/models"}

    def test_deep_paths_are_truncated_to_depth_four(self):
        result = _select_meaningful_dirs(["a/b/c/d/e/file.py"])
        assert result == {"a/b/c/d": ["a/b/c/d/e/file.py"]}

    def test_large_repo_is_capped_to_fifty_groups(self):
        paths = [f"dir{i}/file.py" for i in range(60)]
        result = _select_meaningful_dirs(paths)
        assert len(result) == 50


class TestPatchStructureIndex:
    def test_delta_patch_adds_and_removes_paths(self):
        existing = {
            "schema_version": 1,
            "meaningful_dirs": {
                "week1": ["week1/README.md"],
                "week2": ["week2/README.md"],
            },
            "total_files": 2,
            "generated_at": "2026-04-20T00:00:00+00:00",
            "is_partial": False,
        }

        patched = _patch_structure_index(
            existing,
            added=["week3/README.md"],
            deleted=["week1/README.md"],
        )

        assert "week1" not in patched["meaningful_dirs"]
        assert patched["meaningful_dirs"]["week2"] == ["week2/README.md"]
        assert patched["meaningful_dirs"]["week3"] == ["week3/README.md"]
        assert patched["total_files"] == 2
        assert patched["is_partial"] is False


class TestBuildStructureIndex:
    def test_carries_snapshot_identity(self):
        built = _build_structure_index(
            ["app/auth.py"],
            snapshot_id="abc123",
            snapshot_root_hash="deadbeef",
        )

        assert built["schema_version"] == 2
        assert built["snapshot_id"] == "abc123"
        assert built["snapshot_root_hash"] == "deadbeef"
