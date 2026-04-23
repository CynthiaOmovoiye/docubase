from types import SimpleNamespace

from app.domains.memory.evidence import (
    MemoryEvidenceBundle,
    build_auth_flow_chunks,
    build_change_summary_chunks,
    build_feature_summary_chunks,
    build_onboarding_map_chunks,
    build_risk_summary_chunks,
    build_workspace_synthesis_content,
)


def _file(path: str, role: str | None = None, language: str | None = "python"):
    return SimpleNamespace(
        path=path,
        framework_role=role,
        language=language,
        source_id="11111111-1111-1111-1111-111111111111",
        snapshot_id="sha:test",
    )


def _symbol(path: str, qualified_name: str, symbol_name: str | None = None):
    return SimpleNamespace(
        path=path,
        qualified_name=qualified_name,
        symbol_name=symbol_name or qualified_name.rsplit(".", 1)[-1],
        start_line=10,
        end_line=22,
        source_id="11111111-1111-1111-1111-111111111111",
        snapshot_id="sha:test",
    )


def _relationship(source_ref: str, target_ref: str):
    return SimpleNamespace(
        source_ref=source_ref,
        target_ref=target_ref,
        relationship_type=SimpleNamespace(value="uses"),
    )


def _activity(title: str, occurred_at: str, paths: list[str]):
    return SimpleNamespace(
        title=title,
        occurred_at=occurred_at,
        path_refs=paths,
        activity_key=title.lower().replace(" ", "-"),
    )


def _bundle() -> MemoryEvidenceBundle:
    return MemoryEvidenceBundle(
        twin_id="00000000-0000-0000-0000-000000000123",
        workspace_id="00000000-0000-0000-0000-000000000999",
        indexed_files=[
            _file("app/auth.py", "api_routes"),
            _file("app/models.py", "data_models"),
            _file("pyproject.toml", "dependency_manifest", "toml"),
            _file("tests/test_auth.py", "tests"),
        ],
        indexed_symbols=[
            _symbol("app/auth.py", "auth.get_current_user"),
            _symbol("app/auth.py", "auth.login"),
            _symbol("app/models.py", "models.User"),
        ],
        indexed_relationships=[
            _relationship("app/auth.py", "models.User"),
            _relationship("app/auth.py", "jwt.decode"),
        ],
        git_activities=[
            _activity(
                "Add auth middleware",
                "2026-04-20T09:00:00Z",
                ["app/auth.py", "tests/test_auth.py"],
            )
        ],
        structure_overview=[
            {"dir_path": "app", "file_paths": ["app/auth.py", "app/models.py"], "file_count": 2},
            {"dir_path": "tests", "file_paths": ["tests/test_auth.py"], "file_count": 1},
        ],
    )


def test_feature_summary_chunks_include_provenance():
    chunks = build_feature_summary_chunks(_bundle())

    assert chunks
    assert chunks[0]["chunk_type"] == "feature_summary"
    assert chunks[0]["chunk_metadata"]["provenance"]


def test_auth_flow_chunks_capture_auth_files_and_symbols():
    chunks = build_auth_flow_chunks(_bundle())

    assert len(chunks) == 1
    assert chunks[0]["chunk_type"] == "auth_flow"
    assert "`app/auth.py`" in chunks[0]["content"]
    assert "`auth.get_current_user`" in chunks[0]["content"]
    assert chunks[0]["chunk_metadata"]["provenance"]


def test_auth_flow_chunks_capture_relationship_only_provenance():
    bundle = MemoryEvidenceBundle(
        twin_id="00000000-0000-0000-0000-000000000123",
        workspace_id="00000000-0000-0000-0000-000000000999",
        indexed_files=[
            _file("community_contributions/product.tsx", "library_module", "tsx"),
        ],
        indexed_symbols=[],
        indexed_relationships=[
            _relationship(
                "file:community_contributions/product.tsx",
                "symbol_external:login",
            ),
        ],
        git_activities=[],
        structure_overview=[],
    )

    chunks = build_auth_flow_chunks(bundle)

    assert len(chunks) == 1
    assert "`community_contributions/product.tsx`" in chunks[0]["content"]
    assert chunks[0]["chunk_metadata"]["provenance"] == [
        {
            "kind": "file",
            "path": "community_contributions/product.tsx",
            "source_id": "11111111-1111-1111-1111-111111111111",
            "snapshot_id": "sha:test",
        }
    ]


def test_onboarding_map_prefers_manifests_and_core_files():
    chunks = build_onboarding_map_chunks(_bundle())

    assert len(chunks) == 1
    assert chunks[0]["chunk_type"] == "onboarding_map"
    assert "`pyproject.toml`" in chunks[0]["content"]


def test_risk_summary_chunks_are_grounded_in_index_complexity():
    chunks = build_risk_summary_chunks(_bundle())

    assert chunks
    assert chunks[0]["chunk_type"] == "risk_note"
    assert "indexed symbols" in chunks[0]["content"]
    assert chunks[0]["chunk_metadata"]["provenance"]


def test_change_summary_chunks_group_git_activity():
    chunks = build_change_summary_chunks(_bundle())

    assert len(chunks) == 1
    assert chunks[0]["chunk_type"] == "change_entry"
    assert "Add auth middleware" in chunks[0]["content"]
    assert chunks[0]["chunk_metadata"]["activity_count"] == 1


def test_workspace_synthesis_content_aggregates_project_rows():
    content, metadata = build_workspace_synthesis_content(
        workspace_name="Studio",
        project_rows=[
            {
                "twin_id": "1",
                "name": "Alpha API",
                "files_indexed": 4,
                "symbols_indexed": 3,
                "relationships_indexed": 2,
                "artifact_labels": ["feature_summary", "auth_flow"],
                "brief_excerpt": "FastAPI service for auth.",
                "languages": ["python"],
            },
            {
                "twin_id": "2",
                "name": "Beta Web",
                "files_indexed": 6,
                "symbols_indexed": 5,
                "relationships_indexed": 3,
                "artifact_labels": ["onboarding_map"],
                "brief_excerpt": "Frontend surface for customer flows.",
                "languages": ["typescript"],
            },
        ],
    )

    assert "## Workspace synthesis for Studio" in content
    assert "### Alpha API" in content
    assert "### Beta Web" in content
    assert metadata["languages"] == ["python", "typescript"]
