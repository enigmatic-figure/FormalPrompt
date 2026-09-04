from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).parents[1]


def test_seed_artifact_catalog_has_unique_existing_entries():
    library = ROOT / "artifact-library"
    catalog = json.loads((library / "catalog.json").read_text(encoding="utf-8"))

    assert catalog["contract"] == "formalprompt-artifact-catalog/v1"
    assert catalog["status"] == "seed"
    identifiers = [artifact["id"] for artifact in catalog["artifacts"]]
    paths = [artifact["path"] for artifact in catalog["artifacts"]]
    assert len(identifiers) == len(set(identifiers))
    assert len(paths) == len(set(paths))
    for relative_path in paths:
        artifact_path = library / relative_path
        assert artifact_path.is_file(), relative_path
        assert artifact_path.read_text(encoding="utf-8").strip(), relative_path


def test_muse_composer_eval_cases_are_invariant_based_and_unique():
    evals = json.loads((ROOT / "examples" / "muse-composer-evals.json").read_text(encoding="utf-8"))

    assert evals["contract"] == "formalprompt-muse-composer-evals/v1"
    identifiers = [case["id"] for case in evals["cases"]]
    assert len(identifiers) == len(set(identifiers))
    assert len(identifiers) >= 5
    for case in evals["cases"]:
        assert case["initial_prompt"].strip()
        assert case["expected_invariants"]
        assert all(invariant.strip() for invariant in case["expected_invariants"])
