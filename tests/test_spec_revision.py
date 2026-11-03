from __future__ import annotations

import copy
import json

import pytest

from codex_funplay_bridge.broker import BridgeError
from codex_funplay_bridge.spec_revision import revise_spec
from codex_funplay_bridge.config import BridgeConfig
from codex_funplay_bridge.ui_agent_tools import UiAgentTools


@pytest.fixture
def sample():
    spec = {"schemaVersion": 2, "outputPrefabPath": "Assets/AgentDemos/UIAgent/Prefabs/PF_Old.prefab",
            "root": {"id": "Screen", "type": "Panel", "style": {"color": "#112233"},
                     "placement": {"anchoredPosition": [1000, 0]}, "children": []}}
    diagnosis = {"complete": True, "status": "diagnosed", "diagnosisFingerprint": "a" * 64,
                 "issues": [{"issueId": "OUTSIDE_REFERENCE_CANVAS:Screen", "suggestedChanges": [
                     {"nodeId": "Screen", "field": "placement.anchoredPosition", "beforeExists": True,
                      "before": [1000, 0], "after": [600, 0]}]}]}
    return spec, diagnosis


NEW = "Assets/AgentDemos/UIAgent/Prefabs/PF_New.prefab"
SELECT = '["OUTSIDE_REFERENCE_CANVAS:Screen"]'


def test_revision_preserves_original_and_unrelated_fields(sample):
    spec, diagnosis = sample
    original = copy.deepcopy(spec)
    result = revise_spec(spec, diagnosis, SELECT, NEW)
    assert spec == original
    assert result["spec"]["root"]["placement"]["anchoredPosition"] == [600, 0]
    assert result["spec"]["root"]["style"] == spec["root"]["style"]
    assert result["spec"]["outputPrefabPath"] == NEW
    assert result["writesPerformed"] is False and result["requiresGenerationConfirmation"] is True
    assert result["changes"][0]["evidenceIssueId"] == "OUTSIDE_REFERENCE_CANVAS:Screen"


@pytest.mark.parametrize("selection", ['[]', '[1]', '["missing"]', '["OUTSIDE_REFERENCE_CANVAS:Screen","OUTSIDE_REFERENCE_CANVAS:Screen"]', '{}', 'bad'])
def test_bad_or_unsupported_issue_selection(sample, selection):
    with pytest.raises(BridgeError): revise_spec(*sample, selection, NEW)


def test_rejects_old_output_and_stale_field(sample):
    spec, diagnosis = sample
    with pytest.raises(BridgeError, match="different"): revise_spec(spec, diagnosis, SELECT, spec["outputPrefabPath"])
    spec["root"]["placement"]["anchoredPosition"] = [200, 0]
    with pytest.raises(BridgeError, match="differs"): revise_spec(spec, diagnosis, SELECT, NEW)


def test_no_silent_fix_for_unhandled_issue(sample):
    spec, diagnosis = sample
    diagnosis["issues"][0]["suggestedChanges"] = []
    with pytest.raises(BridgeError) as error: revise_spec(spec, diagnosis, SELECT, NEW)
    assert error.value.kind == "unsupported_revision"


def test_rejects_conflicting_or_unapproved_fields(sample):
    spec, diagnosis = sample
    change = diagnosis["issues"][0]["suggestedChanges"][0]
    diagnosis["issues"][0]["suggestedChanges"].append(copy.deepcopy(change))
    with pytest.raises(BridgeError): revise_spec(spec, diagnosis, SELECT, NEW)
    diagnosis["issues"][0]["suggestedChanges"] = [{**change, "field": "style.color"}]
    with pytest.raises(BridgeError): revise_spec(spec, diagnosis, SELECT, NEW)


def test_incomplete_evidence_never_becomes_revision(sample):
    spec, diagnosis = sample
    diagnosis["complete"] = False
    with pytest.raises(BridgeError): revise_spec(spec, diagnosis, SELECT, NEW)


def test_bridge_refreshes_diagnosis_and_validates_without_prepare_or_write(sample, tmp_path, monkeypatch):
    spec, diagnosis = sample
    service = UiAgentTools(lambda: BridgeConfig("Test", "http://127.0.0.1:21898/", 10, tmp_path / "bridge.toml", tmp_path))
    calls = []
    def execute(name, code, **kwargs):
        calls.append((name, code))
        return {"ok": True, "result": diagnosis if name == "ui_agent_diagnose_composition" else {"valid": True}}
    monkeypatch.setattr(service, "_execute", execute)
    result = service.revise_composition(json.dumps(spec), "a" * 64, SELECT, NEW)
    assert result["result"]["validation"]["valid"] is True
    assert [c[0] for c in calls] == ["ui_agent_diagnose_composition", "ui_agent_validate_composition"]
    assert "UiCompositionDiagnostics.DiagnoseJson" in calls[0][1]
    with pytest.raises(BridgeError) as error:
        service.revise_composition(json.dumps(spec), "b" * 64, SELECT, NEW)
    assert error.value.kind == "diagnosis_stale"
    monkeypatch.setattr(service, "_execute", lambda *a, **k: {"ok": True, "result": {"complete": False}})
    with pytest.raises(BridgeError) as error: service.revise_composition(json.dumps(spec), "a" * 64, SELECT, NEW)
    assert error.value.kind == "diagnosis_incomplete"


def test_bridge_rejects_invalid_unity_revision(sample, tmp_path, monkeypatch):
    spec, diagnosis = sample
    service = UiAgentTools(lambda: BridgeConfig("Test", "http://127.0.0.1:21898/", 10, tmp_path / "bridge.toml", tmp_path))
    monkeypatch.setattr(service, "_execute", lambda name, *a, **k: {"ok": True, "result": diagnosis if name == "ui_agent_diagnose_composition" else {"valid": False}})
    with pytest.raises(BridgeError) as error: service.revise_composition(json.dumps(spec), "a" * 64, SELECT, NEW)
    assert error.value.kind == "revised_spec_invalid"
