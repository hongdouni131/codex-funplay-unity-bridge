from __future__ import annotations

import copy
import json
import re
import shutil
import subprocess

import pytest

from codex_funplay_bridge.broker import BridgeError
from codex_funplay_bridge.spec_selection_merge import fingerprint, merge_selection, parse_spec
from codex_funplay_bridge.sprite_selection import _render_page
from test_sprite_selection import catalog, make_service, project


def spec():
    return {"schemaVersion": 2, "root": {"id": "Panel", "type": "Panel", "placement": {"mode": "anchors"},
        "style": {"color": "#12345678", "spritePath": "Assets/old.png", "spriteGuid": "old",
                  "spriteName": "oldSlice", "spriteLocalFileId": "999999999999999999", "imageType": "sliced", "border": [8]*4},
        "children": [{"id": "Label", "type": "Text", "text": "Keep text", "style": {"fontSize": 40}}]}}


def selection(node="Panel"):
    return {"specNodeId": node, "sourcePath": "Assets/UI/button.png", "sourceGuid": "sprite-guid",
            "spriteLocalFileId": "21300000", "style": {"spritePath": "Assets/UI/button.png",
            "spriteGuid": "sprite-guid", "imageType": "simple"}}


def layout(hash_value="c"*64):
    return {"basis": "unity_ugui_reference_resolution", "layoutFingerprint": hash_value,
            "nodes": [{"nodeId": "Panel", "targetSize": [688.125, 388.5],
                       "referencePixelsPerUnit": 100, "pixelsPerUnitMultiplier": 1}]}


def test_merge_is_a_sprite_only_copy_and_removes_obsolete_selectors():
    original = spec()
    snapshot = copy.deepcopy(original)
    result = merge_selection(original, fingerprint(original), [selection()])
    expected = copy.deepcopy(original)
    expected["root"]["style"] = {"color": "#12345678", **selection()["style"]}
    assert result["spec"] == expected and original == snapshot
    assert {change["field"] for change in result["changes"]} == {
        "style.spritePath", "style.spriteGuid", "style.spriteName", "style.spriteLocalFileId", "style.imageType", "style.border"}
    assert not result["writesPerformed"] and result["requiresGenerationConfirmation"]


def test_merge_reuses_one_sprite_at_different_nodes_and_is_idempotent():
    original = spec()
    original["root"]["children"].append({"id": "Other", "type": "Button", "style": {"color": "#FFFFFF"}})
    result = merge_selection(original, fingerprint(original), [selection(), selection("Other")])
    assert result["reusedResources"][0]["nodeIds"] == ["Panel", "Other"]
    again = merge_selection(result["spec"], fingerprint(result["spec"]), [selection(), selection("Other")])
    assert again["changes"] == []


@pytest.mark.parametrize("kind", ["spec_stale", "ambiguous_mapping", "invalid_mapping", "invalid_selection"])
def test_merge_rejects_conflicting_or_out_of_scope_patches(kind):
    original = spec()
    choices = [selection()]
    fp = fingerprint(original)
    if kind == "spec_stale": original["root"]["children"][0]["text"] = "Changed"
    if kind == "ambiguous_mapping": choices *= 2
    if kind == "invalid_mapping": choices[0]["specNodeId"] = "Label"
    if kind == "invalid_selection": choices[0]["style"]["color"] = "#FFFFFF"
    with pytest.raises(BridgeError) as error:
        merge_selection(original, fp, choices)
    assert error.value.kind == kind


@pytest.mark.parametrize("payload", ['{"schemaVersion":2,"root":{},"root":{}}',
    '{"schemaVersion":2,"root":{"x":NaN}}', '{"schemaVersion":2,"root":{"x":Infinity}}',
    '{"schemaVersion":2,"root":{"x":1e400}}'])
def test_ambiguous_or_nonfinite_json_is_rejected(payload):
    with pytest.raises(BridgeError): parse_spec(payload)


def bound_session(project, monkeypatch):
    service = make_service(project)
    def execute(name, *_args, **_kwargs):
        if name == "ui_agent_measure_composition_layout":
            return {"ok": True, "result": {"status": "measured", "layout": layout()}}
        if name == "ui_agent_validate_composition":
            return {"ok": True, "result": {"valid": True}}
        return catalog()
    monkeypatch.setattr(service, "_execute", execute)
    slots = [{"id": "panel", "label": "面板", "specNodeId": "Panel", "candidates": [
        {"path": "Assets/UI/button.png", "guid": "sprite-guid", "localFileId": "21300000"}]}]
    response = service.create_sprite_selection_session("Assets/UI", "a"*64, json.dumps(slots), json.dumps(spec()))["result"]
    assert service._sprite_selection_sessions.submit(response["sessionId"], [{"candidateIndex": 0, "imageType": "simple"}])
    return service, response, execute, slots


def test_service_merge_revalidates_and_never_calls_prepare_or_generate(project, monkeypatch):
    service, response, execute, _ = bound_session(project, monkeypatch)
    calls = []
    def traced(name, *args, **kwargs):
        calls.append(name)
        return execute(name, *args, **kwargs)
    monkeypatch.setattr(service, "_execute", traced)
    result = service.merge_sprite_selection(response["sessionId"], json.dumps(spec()))["result"]
    assert result["status"] == "merged_requires_prepare" and result["validation"]["valid"]
    assert calls == ["ui_agent_find_sprites", "ui_agent_measure_composition_layout", "ui_agent_validate_composition"]
    session, _ = service._sprite_selection_sessions.get(response["sessionId"])
    assert session.slots[0]["targetSize"] == [688.125, 388.5]
    assert not result["writesPerformed"]


@pytest.mark.parametrize("kind", ["spec_stale", "layout_stale", "catalog_stale", "project_mismatch",
                                  "selection_required", "spec_binding_required", "merged_spec_invalid", "session_expired"])
def test_service_stops_when_selection_baselines_are_no_longer_valid(project, monkeypatch, kind):
    service, response, execute, _ = bound_session(project, monkeypatch)
    session, _ = service._sprite_selection_sessions.get(response["sessionId"])
    original = spec()
    if kind == "spec_stale": original["root"]["style"]["color"] = "#FFFFFF"
    if kind == "project_mismatch": session.project_root = "Other project"
    if kind == "selection_required": session.submitted = None
    if kind == "spec_binding_required": session.base_spec_fingerprint = None
    if kind == "session_expired": service.cancel_sprite_selection(response["sessionId"])
    def changed(name, *args, **kwargs):
        if kind == "layout_stale" and name == "ui_agent_measure_composition_layout":
            return {"ok": True, "result": {"status": "measured", "layout": layout("d"*64)}}
        if kind == "catalog_stale" and name == "ui_agent_find_sprites": return catalog("d"*64)
        if kind == "merged_spec_invalid" and name == "ui_agent_validate_composition":
            return {"ok": True, "result": {"valid": False, "errors": [{"code": "BAD_SPEC"}]}}
        return execute(name, *args, **kwargs)
    monkeypatch.setattr(service, "_execute", changed)
    with pytest.raises(BridgeError) as error:
        service.merge_sprite_selection(response["sessionId"], json.dumps(original))
    assert error.value.kind == kind


def test_duplicate_mapping_is_rejected_before_session_creation(project, monkeypatch):
    service, _, _, slots = bound_session(project, monkeypatch)
    duplicate = copy.deepcopy(slots[0]); duplicate["id"] = "other"
    with pytest.raises(BridgeError) as error:
        service.create_sprite_selection_session("Assets/UI", "a"*64, json.dumps(slots + [duplicate]), json.dumps(spec()))
    assert error.value.kind == "ambiguous_mapping"


@pytest.mark.parametrize("invalid", ["duplicate", "nan", "ppu", "missing", "blocked"])
def test_layout_measurement_rejects_unusable_native_results(project, monkeypatch, invalid):
    service = make_service(project)
    report = {"status": "measured", "layout": layout()}
    if invalid == "duplicate": report["layout"]["nodes"] *= 2
    if invalid == "nan": report["layout"]["nodes"][0]["targetSize"][0] = float("nan")
    if invalid == "ppu": report["layout"]["nodes"][0]["referencePixelsPerUnit"] = 0
    if invalid == "missing": del report["layout"]["layoutFingerprint"]
    if invalid == "blocked": report["status"] = "blocked"
    monkeypatch.setattr(service, "_execute", lambda *_a, **_k: {"ok": True, "result": report})
    with pytest.raises(BridgeError): service.measure_composition_layout(json.dumps(spec()))


def test_html_preview_executes_ppu_and_small_border_compression_math(project, monkeypatch, tmp_path):
    node = shutil.which("node")
    if node is None: pytest.skip("Node runtime unavailable for JS Canvas geometry check")
    service, response, _, _ = bound_session(project, monkeypatch)
    session, _ = service._sprite_selection_sessions.get(response["sessionId"])
    html = _render_page(response["sessionId"], session).decode()
    source = re.search(r"function renderPreview\(.*?(?=\nfunction updateReview)", html, re.S).group()
    runner = tmp_path / "preview.cjs"
    runner.write_text(source + '''
const assert=require('node:assert/strict');let draws=[];
const ctx={clearRect(){},drawImage(...args){draws.push(args.slice(1))}};
const canvas={getContext(){return ctx}};const image={complete:true,naturalWidth:100,naturalHeight:100};
const c={previewRect:[0,0,100,100],previewOrigin:'bottom_left',border:[20,20,20,20],padding:[0,0,0,0],pixelsPerUnit:200};
renderPreview(canvas,image,c,'sliced',100,100,100,1);
assert.equal(draws.length,9);assert.equal(draws[0][6],canvas.width*0.1);
draws=[];renderPreview(canvas,image,c,'sliced',10,10,100,1);
assert.equal(draws.length,4);assert.equal(draws[0][6],canvas.width/2);
draws=[];renderPreview(canvas,image,c,'simple',100,20,100,1);
assert.equal(draws.length,1);assert.deepEqual(draws[0].slice(4),[0,0,canvas.width,canvas.height]);
draws=[];c.padding=[4,4,4,4];renderPreview(canvas,image,c,'sliced',100,100,100,2);
assert.equal(draws[0][0],4);assert.equal(draws[0][4],canvas.width/100);
console.log('Canvas preview: PPU, multiplier, padding, compressed borders, Simple stretch passed');
''', encoding="utf-8")
    completed = subprocess.run([node, str(runner)], text=True, capture_output=True, timeout=10)
    assert completed.returncode == 0, completed.stdout + completed.stderr
