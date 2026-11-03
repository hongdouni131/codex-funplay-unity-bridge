from __future__ import annotations

import http.client
import json
from pathlib import Path
from urllib.parse import urlsplit

import pytest

from codex_funplay_bridge.broker import BridgeError
from codex_funplay_bridge.config import BridgeConfig
from codex_funplay_bridge.ui_agent_tools import UiAgentTools
from codex_funplay_bridge.sprite_selection import _render_page, enrich_selection_slot

PNG_1X1 = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000b49444154789c636000020000050001a5f645400000000049454e44ae426082"
)


@pytest.fixture
def project(tmp_path: Path) -> Path:
    root = tmp_path / "UnityProject"
    asset = root / "Assets" / "UI"
    asset.mkdir(parents=True)
    (asset / "button.png").write_bytes(PNG_1X1)
    return root


def catalog(fingerprint: str = "a" * 64) -> dict:
    return {"ok": True, "result": {
        "status": "complete", "complete": True, "hasMore": False,
        "catalogFingerprint": fingerprint,
        "sprites": [{
            "path": "Assets/UI/button.png", "guid": "sprite-guid", "name": "button",
            "localFileId": "21300000", "rect": [0, 0, 1, 1], "border": [0, 0, 0, 0],
            "slicedBorderUsable": False, "pixelsPerUnit": 100, "padding": [0, 0, 0, 0],
            "specReference": {"spritePath": "Assets/UI/button.png", "spriteGuid": "sprite-guid"},
            "preview": {"texturePath": "Assets/UI/button.png", "textureWidth": 1, "textureHeight": 1,
                        "rect": [0, 0, 1, 1], "origin": "bottom_left"},
        }],
    }}


def make_service(project_root: Path) -> UiAgentTools:
    config = BridgeConfig("Unity Project", "http://127.0.0.1:1/", 1, project_root / "bridge.toml", project_root)
    return UiAgentTools(lambda: config)


def create(service: UiAgentTools) -> dict:
    slots = [{"id": "dialog.panel", "label": "对话框面板", "description": "选择最合适的背景", "candidates": [
        {"path": "Assets/UI/button.png", "guid": "sprite-guid", "localFileId": "21300000"},
    ]}]
    return service.create_sprite_selection_session("Assets/UI", "a" * 64, json.dumps(slots))["result"]


def test_slot_guidance_recommendations_and_mapping_are_explained(project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    service = make_service(project)
    monkeypatch.setattr(service, "_execute", lambda *_args, **_kwargs: catalog())
    slots = [{
        "id": "dialog.panel",
        "label": "对话框面板",
        "description": "承载正文",
        "usageHint": "优先使用可拉伸背景",
        "beginnerTip": "先比较九宫格预览",
        "specNodeId": "MainPanel",
        "writeScope": "仅更新 MainPanel.style",
        "targetSize": [900, 520],
        "candidates": [{"path": "Assets/UI/button.png", "guid": "sprite-guid", "localFileId": "21300000"}],
    }]
    result = service.create_sprite_selection_session("Assets/UI", "a" * 64, json.dumps(slots, ensure_ascii=False))["result"]
    session, exists = service._sprite_selection_sessions.get(result["sessionId"])
    assert exists and session is not None
    slot = session.slots[0]
    assert slot["usageHint"] == "优先使用可拉伸背景"
    assert slot["beginnerTip"] == "先比较九宫格预览"
    assert slot["specNodeId"] == "MainPanel"
    assert slot["writeScope"] == "仅更新 MainPanel.style"
    assert slot["targetSize"] == [900, 520]
    assert slot["targetSizeSource"] == "manual"
    assert slot["candidates"][0]["recommendationRank"] == 1
    assert slot["candidates"][0]["recommended"] is True
    assert slot["candidates"][0]["recommendationReasons"]
    assert "结构规则首选" in slot["candidates"][0]["recommendationNote"]


@pytest.mark.parametrize("target_size", [[15, 100], [100, 4097], [100], [100.0, 100]])
def test_target_size_is_bounded_before_page_creation(project: Path, monkeypatch: pytest.MonkeyPatch, target_size: list) -> None:
    service = make_service(project)
    monkeypatch.setattr(service, "_execute", lambda *_args, **_kwargs: catalog())
    slots = [{"id": "panel", "label": "面板", "targetSize": target_size, "candidates": [
        {"path": "Assets/UI/button.png", "guid": "sprite-guid", "localFileId": "21300000"},
    ]}]
    with pytest.raises(BridgeError) as error:
        service.create_sprite_selection_session("Assets/UI", "a" * 64, json.dumps(slots))
    assert error.value.kind == "invalid_arguments"


def test_nonpreferred_candidate_shows_rank_and_specific_structural_reasons() -> None:
    slot = enrich_selection_slot({"id": "dialog.panel", "label": "面板", "candidates": [
        {"rect": [0, 0, 512, 512], "border": [32, 32, 32, 32], "imageTypes": ["simple", "sliced"]},
        {"rect": [0, 0, 32, 32], "border": [0, 0, 0, 0], "imageTypes": ["simple"]},
    ]})
    preferred, other = slot["candidates"]
    assert preferred["recommended"] is True
    assert other["recommended"] is False
    assert "未优先推荐" in other["recommendationNote"]
    assert other["recommendationNote"] in other["cautions"]
    assert any("Border" in reason or "小于目标尺寸" in reason for reason in other["cautions"])


def test_browser_submission_round_trips_and_revalidates(project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    service = make_service(project)
    monkeypatch.setattr(service, "_execute", lambda *_args, **_kwargs: catalog())
    session = create(service)
    parts = urlsplit(session["url"])
    connection = http.client.HTTPConnection(parts.hostname, parts.port, timeout=3)
    connection.request("GET", parts.path, headers={"Host": f"{parts.hostname}:{parts.port}"})
    page = connection.getresponse()
    page_body = page.read().decode("utf-8")
    assert page.status == 200
    assert "对话框面板" in page_body
    assert "button" in page_body
    assert "drawImage" in page_body
    assert "用途和目标尺寸" in page_body
    assert "Simple" in page_body and "Sliced" in page_body
    assert "按节点矩形拉伸" in page_body
    assert "option.selected=optionValue===candidate.recommendedImageType" in page_body
    assert "推荐候选" in page_body
    assert "未优先推荐" in page_body
    assert "结构适配分" in page_body
    assert "recommendationNote" in page_body
    assert "Spec 节点" in page_body
    assert "不会生成 Prefab" in page_body
    assert "仍需更新 Spec、Validate、Prepare" in page_body
    assert "127.0.0.1" in session["url"]

    connection.request("GET", f"/image/{session['sessionId']}/0/0", headers={"Host": f"{parts.hostname}:{parts.port}"})
    image = connection.getresponse()
    assert image.status == 200
    assert image.getheader("Content-Type") == "image/png"
    assert image.read() == PNG_1X1

    body = json.dumps({"choices": [{"candidateIndex": 0, "imageType": "simple"}]})
    connection.request("POST", f"/submit/{session['sessionId']}", body,
                       {"Host": f"{parts.hostname}:{parts.port}", "Origin": "http://attacker.invalid", "Content-Type": "application/json"})
    rejected = connection.getresponse()
    assert rejected.status == 403
    rejected.read()

    connection.request("POST", f"/submit/{session['sessionId']}", body,
                       {"Host": f"{parts.hostname}:{parts.port}", "Origin": f"http://{parts.hostname}:{parts.port}", "Content-Type": "application/json"})
    accepted = connection.getresponse()
    assert accepted.status == 200
    accepted.read()
    connection.close()

    result = service.get_sprite_selection(session["sessionId"], wait_seconds=0)["result"]
    assert result["status"] == "submitted"
    assert result["selections"][0]["spriteLocalFileId"] == "21300000"
    assert result["selections"][0]["specNodeId"] == "dialog.panel"
    assert result["selections"][0]["targetSize"] == [900, 520]
    assert result["selections"][0]["writeScope"]
    assert result["selections"][0]["recommendation"]["rank"] == 1
    assert result["selections"][0]["style"] == {
        "spritePath": "Assets/UI/button.png", "spriteGuid": "sprite-guid", "imageType": "simple",
    }
    assert "Validate" in result["nextStep"]
    assert "Prepare" in result["nextStep"]
    assert "explicit developer confirmation" in result["nextStep"]


def test_stale_catalog_fingerprint_rejects_submitted_selection(project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    service = make_service(project)
    reports = iter([catalog(), catalog("b" * 64)])
    monkeypatch.setattr(service, "_execute", lambda *_args, **_kwargs: next(reports))
    session = create(service)
    assert service._sprite_selection_sessions.submit(session["sessionId"], [{"candidateIndex": 0, "imageType": "simple"}])
    with pytest.raises(BridgeError) as error:
        service.get_sprite_selection(session["sessionId"], wait_seconds=0)
    assert error.value.kind == "catalog_stale"


def test_candidate_absent_from_live_catalog_is_rejected(project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    service = make_service(project)
    monkeypatch.setattr(service, "_execute", lambda *_args, **_kwargs: catalog())
    slots = [{"id": "x", "label": "X", "candidates": [
        {"path": "Assets/UI/missing.png", "guid": "missing", "localFileId": "123"},
    ]}]
    with pytest.raises(BridgeError) as error:
        service.create_sprite_selection_session("Assets/UI", "a" * 64, json.dumps(slots))
    assert error.value.kind == "candidate_not_in_catalog"


def test_catalog_invalidation_on_create_stops_before_page_creation(project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    service = make_service(project)
    monkeypatch.setattr(service, "_execute", lambda *_args, **_kwargs: catalog("b" * 64))
    slots = [{"id": "x", "label": "X", "candidates": [
        {"path": "Assets/UI/button.png", "guid": "sprite-guid", "localFileId": "21300000"},
    ]}]
    with pytest.raises(BridgeError) as error:
        service.create_sprite_selection_session("Assets/UI", "a" * 64, json.dumps(slots))
    assert error.value.kind == "catalog_stale"


def test_default_image_type_recommendation_depends_on_slot_role() -> None:
    panel = enrich_selection_slot({"id": "dialog.panel", "label": "面板", "candidates": [
        {"rect": [0, 0, 512, 256], "border": [24, 24, 24, 24], "imageTypes": ["simple", "sliced"]},
    ]})
    pointer = enrich_selection_slot({"id": "menu.pointer", "label": "指针", "candidates": [
        {"rect": [0, 0, 512, 256], "border": [24, 24, 24, 24], "imageTypes": ["simple", "sliced"]},
    ]})
    assert panel["candidates"][0]["recommendedImageType"] == "sliced"
    assert pointer["candidates"][0]["recommendedImageType"] == "simple"
    button = enrich_selection_slot({"id": "StartButton", "label": "开始按钮背景", "candidates": [
        {"rect": [0, 0, 96, 48], "border": [12, 12, 12, 12], "imageTypes": ["simple", "sliced"]},
    ]})
    assert button["role"] == "button"


def test_unity_float_border_becomes_integer_spec_pixels(project: Path) -> None:
    sprite = catalog()["result"]["sprites"][0]
    sprite["border"] = [12.0, 12.0, 12.0, 12.0]
    sprite["slicedBorderUsable"] = True
    candidate, _ = make_service(project)._verified_candidate(sprite, project)
    assert "sliced" in candidate["imageTypes"]
    assert all(type(value) is int for value in candidate["border"])
    sprite["border"][0] = 12.5
    candidate, _ = make_service(project)._verified_candidate(sprite, project)
    assert candidate["imageTypes"] == ["simple"]


def test_spec_node_rect_size_overrides_manual_preview_hint(project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    service = make_service(project)
    monkeypatch.setattr(service, "_execute", lambda name, *_args, **_kwargs: {
        "ok": True, "result": {"status": "measured", "layout": {
            "basis": "unity_ugui_reference_resolution", "layoutFingerprint": "c" * 64,
            "nodes": [{"nodeId": "MainPanel", "targetSize": [820.25, 660.5],
                       "referencePixelsPerUnit": 100, "pixelsPerUnitMultiplier": 1}],
        }}} if name == "ui_agent_measure_composition_layout" else catalog())
    spec = {
        "schemaVersion": 2,
        "referenceResolution": {"width": 1920, "height": 1080},
        "root": {
            "id": "Screen", "placement": {"mode": "anchors", "anchorMin": [0, 0], "anchorMax": [1, 1], "sizeDelta": [0, 0]},
            "children": [{
                "id": "MainPanel", "type": "Panel", "placement": {"mode": "anchors", "anchorMin": [0.5, 0.5], "anchorMax": [0.5, 0.5], "sizeDelta": [820, 660]},
                "children": [],
            }],
        },
    }
    slots = [{"id": "panel", "label": "面板", "specNodeId": "MainPanel", "targetSize": [900, 520], "candidates": [
        {"path": "Assets/UI/button.png", "guid": "sprite-guid", "localFileId": "21300000"},
    ]}]
    result = service.create_sprite_selection_session(
        "Assets/UI", "a" * 64, json.dumps(slots), json.dumps(spec),
    )["result"]
    session, exists = service._sprite_selection_sessions.get(result["sessionId"])
    assert exists and session is not None
    assert session.slots[0]["targetSize"] == [820.25, 660.5]
    assert session.slots[0]["targetSizeSource"] == "unity_layout"
    html = _render_page(result["sessionId"], session).decode("utf-8")
    assert "Unity 实测" in html


def test_session_is_one_submission_and_cancelable(project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    service = make_service(project)
    monkeypatch.setattr(service, "_execute", lambda *_args, **_kwargs: catalog())
    session = create(service)
    choices = [{"candidateIndex": 0, "imageType": "simple"}]
    assert service._sprite_selection_sessions.submit(session["sessionId"], choices)
    assert not service._sprite_selection_sessions.submit(session["sessionId"], choices)
    assert service.cancel_sprite_selection(session["sessionId"])["result"]["cancelled"] is True
