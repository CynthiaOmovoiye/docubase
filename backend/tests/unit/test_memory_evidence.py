from app.domains.memory.evidence import MemoryEvidenceBundle, build_workspace_synthesis_content


def test_memory_evidence_bundle_structure_overview_default():
    b = MemoryEvidenceBundle(
        doctwin_id="00000000-0000-0000-0000-000000000001",
        workspace_id="00000000-0000-0000-0000-000000000002",
    )
    assert b.structure_overview == []


def test_workspace_synthesis_content_aggregates_project_rows():
    content, metadata = build_workspace_synthesis_content(
        workspace_name="Studio",
        project_rows=[
            {
                "doctwin_id": "1",
                "name": "Alpha API",
                "files_indexed": 4,
                "symbols_indexed": 3,
                "relationships_indexed": 2,
                "artifact_labels": ["feature_summary", "auth_flow"],
                "brief_excerpt": "FastAPI service for auth.",
                "languages": ["python"],
            },
            {
                "doctwin_id": "2",
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
