"""Short-lived loopback browser sessions for choosing verified Unity Sprites."""

from __future__ import annotations

import hmac
import json
import secrets
import threading
import time
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlsplit

from .broker import BridgeError

SESSION_TTL_SECONDS = 15 * 60
MAX_SESSIONS = 8
MAX_BODY_BYTES = 16_384

DEFAULT_TARGET_SIZES = {
    "panel": [900, 520],
    "button": [480, 96],
    "banner": [720, 160],
    "title": [720, 180],
    "icon": [96, 96],
    "pointer": [96, 96],
    "generic": [480, 160],
}


@dataclass
class SpriteSelectionSession:
    created_at: float
    slots: list[dict[str, Any]]
    catalog_fingerprint: str
    source_path: str
    submitted: list[dict[str, Any]] | None = None
    project_root: str | None = None
    base_spec_fingerprint: str | None = None
    layout_fingerprint: str | None = None


def _slot_role(slot: dict[str, Any]) -> str:
    value = " ".join(str(slot.get(key, "")) for key in ("id", "label", "description")).lower()
    if any(token in value for token in ("panel", "dialog", "面板", "对话框")):
        return "panel"
    if any(token in value for token in ("button", "按钮", "action")):
        return "button"
    if "背景" in value:
        return "panel"
    if any(token in value for token in ("banner", "横幅")):
        return "banner"
    if any(token in value for token in ("title", "标题", "logo", "装饰")):
        return "title"
    if any(token in value for token in ("pointer", "cursor", "指针", "光标")):
        return "pointer"
    if any(token in value for token in ("icon", "图标", "symbol", "符号")):
        return "icon"
    return "generic"


def _role_guidance(role: str) -> tuple[str, str]:
    guidance = {
        "panel": ("面板背景通常需要稳定的四角和可拉伸的中心区域。优先检查 Sliced 与 Border。", "先比较 Sliced 预览；如果四角变形或 Border 为零，改选其他候选。"),
        "button": ("按钮背景需要在目标按钮尺寸下保持边缘清楚，并且通常要能横向拉伸。", "先看目标尺寸预览，再比较按钮文字区域是否足够宽。"),
        "banner": ("横幅适合承载标题或章节装饰，先判断它应保持比例还是允许拉伸。", "如果图案需要完整保留，优先 Simple；需要延展背景时再考虑 Sliced。"),
        "title": ("标题装饰通常希望保持比例；Simple 会铺满矩形，需要让 Spec 尺寸与图片比例一致。", "先看 Simple 预览，确认透明边缘和主体没有被拉伸变形。"),
        "pointer": ("指针/光标通常是小尺寸 Simple 图标，不应遮挡按钮文字或扩大点击区域。", "优先选择透明边缘清楚、尺寸接近目标的候选。"),
        "icon": ("图标通常希望保持比例；Simple 本身不会自动保持比例，需核对节点尺寸。", "优先比较 Simple 预览和透明边缘；不要仅按文件名选择。"),
        "generic": ("先确认这个用途需要保持比例还是允许拉伸，再选择 Simple 或 Sliced。", "目标尺寸预览只提供结构建议，最终视觉选择仍由开发者决定。"),
    }
    return guidance[role]


def enrich_selection_slot(slot: dict[str, Any]) -> dict[str, Any]:
    """Add explainable, deterministic UI hints without changing Sprite identity."""
    role = _slot_role(slot)
    target_size = slot.get("targetSize") or DEFAULT_TARGET_SIZES[role]
    slot["role"] = role
    slot["targetSize"] = target_size
    hint, tip = _role_guidance(role)
    slot["usageHint"] = slot.get("usageHint") or hint
    slot["beginnerTip"] = slot.get("beginnerTip") or tip
    slot["specNodeId"] = slot.get("specNodeId") or slot["id"]
    slot["writeScope"] = slot.get("writeScope") or "仅把选择映射到该 Spec 节点的 style；不修改素材、场景或已有 Prefab。"
    width, height = target_size
    for candidate in slot["candidates"]:
        rect = candidate["rect"]
        border = candidate["border"]
        score = 45
        reasons: list[str] = []
        cautions: list[str] = []
        if role in {"panel", "button"}:
            if "sliced" in candidate["imageTypes"]:
                score += 35
                reasons.append("已通过 Sliced Border 就绪检查")
            else:
                score -= 20
                cautions.append("没有可用的 Sliced Border，拉伸边缘可能变形")
        else:
            if "simple" in candidate["imageTypes"]:
                score += 12
                reasons.append("支持 Simple；默认会按节点矩形铺满")
        if border != [0, 0, 0, 0] and "sliced" in candidate["imageTypes"]:
            score += 8
            reasons.append(f"Border {border} 可用于九宫格预览")
        if rect[2] > 0 and rect[3] > 0:
            aspect = rect[2] / rect[3]
            target_aspect = width / height
            if abs(aspect - target_aspect) / max(target_aspect, 0.01) < 0.35:
                score += 8
                reasons.append("原始宽高比与目标尺寸较接近")
            elif role in {"panel", "button"} and "sliced" not in candidate["imageTypes"]:
                cautions.append("原始宽高比与目标尺寸差异较大")
        if rect[2] < width / 3 or rect[3] < height / 3:
            cautions.append("原始切片明显小于目标尺寸，放大后可能变糊")
        candidate["recommendationScore"] = max(0, min(100, score))
        candidate["recommendedImageType"] = (
            "sliced" if role in {"panel", "button"} and "sliced" in candidate["imageTypes"]
            else "simple" if "simple" in candidate["imageTypes"]
            else candidate["imageTypes"][0]
        )
        candidate["recommendationReasons"] = reasons or ["已通过资源身份和预览完整性检查"]
        candidate["cautions"] = cautions
    ranked = sorted(slot["candidates"], key=lambda item: item["recommendationScore"], reverse=True)
    for rank, candidate in enumerate(ranked, 1):
        candidate["recommendationRank"] = rank
        candidate["recommended"] = rank == 1
        candidate["recommendationNote"] = (
            "结构规则首选；仅按导入可用性、Border 和目标尺寸推荐，不判断美术风格。"
            if rank == 1 else
            f"未优先推荐：结构适配分 {candidate['recommendationScore']}/100，排名第 {rank}；"
            f"首选为 {ranked[0]['recommendationScore']}/100。评分只反映资源结构，不判断美术风格。"
        )
        if rank > 1:
            candidate["cautions"].insert(0, candidate["recommendationNote"])
    return slot


class SpriteSelectionSessions:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._changed = threading.Condition(self._lock)
        self._sessions: dict[str, SpriteSelectionSession] = {}
        self._httpd: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    def create(self, slots: list[dict[str, Any]], catalog_fingerprint: str, source_path: str,
               project_root: str | None = None, base_spec_fingerprint: str | None = None,
               layout_fingerprint: str | None = None) -> dict[str, Any]:
        with self._lock:
            self._prune()
            if len(self._sessions) >= MAX_SESSIONS:
                raise BridgeError("session_limit", "Too many active Sprite selection sessions; read or cancel an existing session first")
            self._ensure_server()
            token = secrets.token_urlsafe(32)
            self._sessions[token] = SpriteSelectionSession(time.monotonic(), slots, catalog_fingerprint, source_path,
                project_root=project_root, base_spec_fingerprint=base_spec_fingerprint, layout_fingerprint=layout_fingerprint)
            port = self._httpd.server_port if self._httpd else 0
            return {
                "sessionId": token,
                "url": f"http://127.0.0.1:{port}/{token}",
                "expiresInSeconds": SESSION_TTL_SECONDS,
                "slotCount": len(slots),
                "candidateCount": sum(len(slot["candidates"]) for slot in slots),
                "catalogFingerprint": catalog_fingerprint,
                "baseSpecFingerprint": base_spec_fingerprint,
                "layoutFingerprint": layout_fingerprint,
                "mergeAvailable": base_spec_fingerprint is not None,
            }

    def get(self, token: str) -> tuple[SpriteSelectionSession | None, bool]:
        with self._lock:
            self._prune()
            session = self._sessions.get(token)
            return session, session is not None

    def wait_for_submission(self, token: str, wait_seconds: int) -> SpriteSelectionSession | None:
        deadline = time.monotonic() + wait_seconds
        with self._changed:
            while True:
                self._prune()
                session = self._sessions.get(token)
                if session is None or session.submitted is not None:
                    return session
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return session
                self._changed.wait(remaining)

    def submit(self, token: str, choices: Any) -> bool:
        with self._lock:
            self._prune()
            session = self._sessions.get(token)
            if session is None or session.submitted is not None:
                return False
            selected: list[dict[str, Any]] = []
            if not isinstance(choices, list) or len(choices) != len(session.slots):
                return False
            for slot_index, slot in enumerate(session.slots):
                choice = choices[slot_index]
                if not isinstance(choice, dict) or type(choice.get("candidateIndex")) is not int:
                    return False
                candidate_index = choice["candidateIndex"]
                if not 0 <= candidate_index < len(slot["candidates"]):
                    return False
                candidate = slot["candidates"][candidate_index]
                image_type = choice.get("imageType")
                if image_type not in candidate["imageTypes"]:
                    return False
                style = {**candidate["specReference"], "imageType": image_type}
                if image_type == "sliced":
                    style["border"] = candidate["border"]
                selected.append({
                    "slot": slot["id"],
                    "label": slot["label"],
                    "specNodeId": slot["specNodeId"],
                    "writeScope": slot["writeScope"],
                    "targetSize": slot["targetSize"],
                    "referencePixelsPerUnit": slot.get("referencePixelsPerUnit", 100),
                    "pixelsPerUnitMultiplier": slot.get("pixelsPerUnitMultiplier", 1),
                    "layoutFingerprint": slot.get("layoutFingerprint"),
                    "sourcePath": candidate["path"],
                    "sourceGuid": candidate["guid"],
                    "spriteName": candidate["name"],
                    "spriteLocalFileId": candidate["localFileId"],
                    "rect": candidate["rect"],
                    "border": candidate["border"],
                    "pixelsPerUnit": candidate.get("pixelsPerUnit"),
                    "padding": candidate.get("padding", [0, 0, 0, 0]),
                    "imageType": image_type,
                    "recommendation": {
                        "score": candidate["recommendationScore"],
                        "rank": candidate["recommendationRank"],
                        "reasons": candidate["recommendationReasons"],
                        "cautions": candidate["cautions"],
                    },
                    "style": style,
                })
            session.submitted = selected
            self._changed.notify_all()
            return True

    def cancel(self, token: str) -> bool:
        with self._lock:
            return self._sessions.pop(token, None) is not None

    def _ensure_server(self) -> None:
        if self._httpd is not None:
            return
        owner = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def do_GET(self) -> None:  # noqa: N802
                host = f"127.0.0.1:{owner._httpd.server_port}" if owner._httpd else ""
                if self.headers.get("Host") != host:
                    self._send(421, "text/plain; charset=utf-8", b"Invalid host")
                    return
                parts = [part for part in urlsplit(self.path).path.split("/") if part]
                if len(parts) == 1:
                    session, exists = owner.get(parts[0])
                    if not exists or session is None:
                        self._send(404, "text/plain; charset=utf-8", b"Selection session expired")
                        return
                    body = _render_page(parts[0], session)
                    self._send(200, "text/html; charset=utf-8", body)
                    return
                if len(parts) == 4 and parts[0] == "image" and parts[2].isdigit() and parts[3].isdigit():
                    token, slot_index, candidate_index = parts[1], int(parts[2]), int(parts[3])
                    session, exists = owner.get(token)
                    if not exists or session is None or not 0 <= slot_index < len(session.slots):
                        self._send(404, "text/plain; charset=utf-8", b"Selection session expired")
                        return
                    candidates = session.slots[slot_index]["candidates"]
                    if not 0 <= candidate_index < len(candidates):
                        self._send(404, "text/plain; charset=utf-8", b"Sprite preview not found")
                        return
                    image = candidates[candidate_index].get("previewBytes")
                    content_type = candidates[candidate_index].get("previewMime")
                    if not isinstance(image, bytes) or not isinstance(content_type, str):
                        self._send(404, "text/plain; charset=utf-8", b"Sprite preview unavailable")
                        return
                    self._send(200, content_type, image)
                    return
                self._send(404, "text/plain; charset=utf-8", b"Not found")

            def do_POST(self) -> None:  # noqa: N802
                host = f"127.0.0.1:{owner._httpd.server_port}" if owner._httpd else ""
                expected_origin = f"http://{host}"
                if self.headers.get("Host") != host or self.headers.get("Origin") != expected_origin:
                    self._send(403, "application/json", b'{"ok":false,"error":"origin_rejected"}')
                    return
                parts = [part for part in urlsplit(self.path).path.split("/") if part]
                if len(parts) != 2 or parts[0] != "submit":
                    self._send(404, "application/json", b'{"ok":false,"error":"not_found"}')
                    return
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                except ValueError:
                    length = 0
                if length <= 0 or length > MAX_BODY_BYTES:
                    self._send(413, "application/json", b'{"ok":false,"error":"body_too_large"}')
                    return
                try:
                    payload = json.loads(self.rfile.read(length))
                except (json.JSONDecodeError, UnicodeDecodeError):
                    payload = None
                accepted = isinstance(payload, dict) and owner.submit(parts[1], payload.get("choices"))
                if not accepted:
                    self._send(409, "application/json", b'{"ok":false,"error":"invalid_or_closed_session"}')
                    return
                self._send(200, "application/json", b'{"ok":true}')

            def _send(self, status: int, content_type: str, body: bytes) -> None:
                self.close_connection = True
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Connection", "close")
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("Content-Security-Policy", "default-src 'none'; img-src 'self'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; connect-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'")
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *_: object) -> None:
                return

        self._httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._httpd.daemon_threads = True
        self._thread = threading.Thread(target=self._httpd.serve_forever, name="sprite-selection-http", daemon=True)
        self._thread.start()

    def _prune(self) -> None:
        now = time.monotonic()
        for token, session in list(self._sessions.items()):
            if now - session.created_at > SESSION_TTL_SECONDS:
                self._sessions.pop(token, None)


def _render_page(token: str, session: SpriteSelectionSession) -> bytes:
    safe_token = json.dumps(token)
    page_data = []
    for slot_index, slot in enumerate(session.slots):
        page_data.append({
            "id": slot["id"],
            "label": slot["label"],
            "description": slot["description"],
            "usageHint": slot["usageHint"],
            "beginnerTip": slot["beginnerTip"],
            "role": slot["role"],
            "specNodeId": slot["specNodeId"],
            "writeScope": slot["writeScope"],
            "targetSize": slot["targetSize"],
            "referencePixelsPerUnit": slot.get("referencePixelsPerUnit", 100),
            "pixelsPerUnitMultiplier": slot.get("pixelsPerUnitMultiplier", 1),
            "layoutFingerprint": slot.get("layoutFingerprint"),
            "targetSizeSource": slot.get("targetSizeSource", "role_default"),
            "candidates": [{
                "index": candidate_index,
                "name": candidate["name"],
                "path": candidate["path"],
                "imageTypes": candidate["imageTypes"],
                "rect": candidate["rect"],
                "border": candidate["border"],
                "pixelsPerUnit": candidate.get("pixelsPerUnit"),
                "padding": candidate.get("padding", [0, 0, 0, 0]),
                "score": candidate["recommendationScore"],
                "rank": candidate["recommendationRank"],
                "recommended": candidate["recommended"],
                "recommendedImageType": candidate["recommendedImageType"],
                "reasons": candidate["recommendationReasons"],
                "cautions": candidate["cautions"],
                "recommendationNote": candidate["recommendationNote"],
                "previewRect": candidate["previewRect"],
                "textureWidth": candidate["textureWidth"],
                "textureHeight": candidate["textureHeight"],
                "previewOrigin": candidate["previewOrigin"],
                "imageUrl": f"/image/{token}/{slot_index}/{candidate_index}",
            } for candidate_index, candidate in enumerate(slot["candidates"])],
        })
    data = json.dumps(page_data, ensure_ascii=False).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    page = f'''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>UI Agent 素材确认</title><style>
:root{{color-scheme:dark;--bg:#11191e;--surface:#1c292f;--surface2:#26373d;--line:#53636a;--ink:#f0f3ed;--muted:#b7c3c0;--accent:#f0bd66;--good:#8fd3a8;--warn:#ffcb75;--bad:#ff9a87}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--ink);font:14px/1.5 system-ui,"Microsoft YaHei",sans-serif}}header{{padding:22px clamp(16px,4vw,42px);border-bottom:1px solid var(--line)}}h1{{font-size:24px;margin:0 0 5px}}h2{{font-size:18px;margin:0 0 4px}}h3{{font-size:14px;margin:0 0 8px}}p{{margin:4px 0;color:var(--muted)}}main{{max-width:1280px;margin:auto;padding:20px clamp(16px,4vw,42px)}}.slot{{padding:18px 0;border-bottom:1px solid var(--line)}}.slothead{{display:flex;gap:18px;justify-content:space-between;align-items:flex-start;flex-wrap:wrap}}.slotmeta{{flex:1;min-width:240px}}.role{{display:inline-block;color:var(--accent);font-size:12px;font-weight:700;margin-right:8px}}.mapping{{border-left:3px solid var(--accent);padding:8px 12px;background:#202a2d;min-width:260px}}.target{{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-top:10px}}.target label{{color:var(--muted)}}.target input{{width:78px;background:#121c20;color:var(--ink);border:1px solid var(--line);padding:6px}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(285px,1fr));gap:12px;margin-top:14px}}.candidate{{border:1px solid var(--line);background:var(--surface);padding:12px;min-width:0;display:flex;flex-direction:column;gap:8px}}.candidate:has(input[type=radio]:checked){{border-color:var(--accent);box-shadow:inset 0 0 0 1px var(--accent)}}.candidate.recommended{{background:#202f32}}.cardhead{{display:flex;justify-content:space-between;gap:8px;align-items:flex-start}}.pick{{display:flex;gap:8px;align-items:center;font-weight:700;min-width:0}}.badge{{font-size:11px;color:#18231d;background:var(--good);padding:2px 7px;white-space:nowrap}}.score{{font-variant-numeric:tabular-nums;color:var(--accent);font-size:12px}}.previewrow{{display:grid;grid-template-columns:1fr 1fr;gap:8px}}.previewbox{{min-width:0}}.previewbox small{{display:block;color:var(--muted);margin-bottom:4px}}.thumb{{height:132px;background-color:#121c20;background-image:linear-gradient(45deg,#233036 25%,transparent 25%,transparent 75%,#233036 75%),linear-gradient(45deg,#233036 25%,transparent 25%,transparent 75%,#233036 75%);background-position:0 0,10px 10px;background-size:20px 20px;display:flex;align-items:center;justify-content:center;overflow:hidden}}canvas{{max-width:100%;max-height:100%}}.facts,.why,.caution{{font-size:12px;color:var(--muted)}}.why{{color:var(--good)}}.caution{{color:var(--warn)}}.type{{width:100%;padding:8px;background:#121c20;border:1px solid var(--line);color:var(--ink)}}.review{{margin:20px 0;padding:16px;background:var(--surface2);border-left:3px solid var(--accent)}}.reviewrow{{padding:8px 0;border-bottom:1px solid #53636a}}.submit{{position:sticky;bottom:0;background:linear-gradient(transparent,var(--bg) 28%);display:flex;justify-content:flex-end;padding:16px 0}}button{{border:0;background:var(--accent);color:#192125;font-weight:700;padding:12px 20px;cursor:pointer}}button:disabled{{opacity:.55;cursor:wait}}#status{{padding:10px 0;min-height:28px}}@media(max-width:640px){{.grid{{grid-template-columns:1fr}}.previewrow{{grid-template-columns:1fr 1fr}}.thumb{{height:112px}}}}
</style></head><body><header><h1>Sprite 候选确认</h1><p>先看用途和目标尺寸，再比较推荐理由与拉伸效果。选择只交回素材候选；不会生成 Prefab 或修改 Unity 资源。预览模拟源切片、PPU 与边框缩放；纹理压缩、过滤、材质及不同运行分辨率仍以 Unity 为准。</p></header><main><div id="slots"></div><section class="review"><h2>提交前检查</h2><div id="reviewRows"></div><p>提交后，Agent 仍需更新 Spec、Validate、Prepare 并展示完整生成计划；只有开发者确认计划后才会生成。</p></section><div class="submit"><button id="submit" type="button">提交素材选择</button></div><p id="status" role="status"></p></main>
<script>"use strict";const token={safe_token};const slots={data};const root=document.getElementById('slots');const selections=[];
function el(tag,cls,text){{const node=document.createElement(tag);if(cls)node.className=cls;if(text!==undefined)node.textContent=text;return node}}
function renderPreview(canvas,image,candidate,mode,width,height,referencePPU=100,multiplier=1){{
 if(!Number.isFinite(width)||!Number.isFinite(height)||width<=0||height<=0)return;
 const scale=Math.min(300/width,132/height);canvas.width=Math.max(1,Math.round(width*scale));canvas.height=Math.max(1,Math.round(height*scale));
 const ctx=canvas.getContext('2d');ctx.clearRect(0,0,canvas.width,canvas.height);if(!image.complete||image.naturalWidth===0)return;
 const [sx,sy,sw,sh]=candidate.previewRect;const top=candidate.previewOrigin==='bottom_left'?image.naturalHeight-sy-sh:sy;
 if(mode==='simple'){{ctx.drawImage(image,sx,top,sw,sh,0,0,canvas.width,canvas.height);return}}
 if(!(candidate.pixelsPerUnit>0))return;
 const ppu=candidate.pixelsPerUnit/referencePPU*multiplier;
 const [left,bottom,right,topBorder]=candidate.border;const [pl,pb,pr,pt]=candidate.padding;
 let l=left/ppu,r=right/ppu,b=bottom/ppu,t=topBorder/ppu;
 if(l+r>width){{const ratio=width/(l+r);l*=ratio;r*=ratio}}
 if(b+t>height){{const ratio=height/(b+t);b*=ratio;t*=ratio}}
 const xs=[sx+pl,sx+left,sx+sw-right,sx+sw-pr],ys=[top+pt,top+topBorder,top+sh-bottom,top+sh-pb];
 const scaleX=canvas.width/width,scaleY=canvas.height/height;
 const dx=[pl/ppu*scaleX,l*scaleX,(width-r)*scaleX,(width-pr/ppu)*scaleX],dy=[pt/ppu*scaleY,t*scaleY,(height-b)*scaleY,(height-pb/ppu)*scaleY];
 for(let row=0;row<3;row++)for(let col=0;col<3;col++){{const sourceW=xs[col+1]-xs[col],sourceH=ys[row+1]-ys[row],dw=dx[col+1]-dx[col],dh=dy[row+1]-dy[row];if(sourceW>0&&sourceH>0&&dw>0&&dh>0)ctx.drawImage(image,xs[col],ys[row],sourceW,sourceH,dx[col],dy[row],dw,dh)}}
}}

function updateReview(){{const target=document.getElementById('reviewRows');target.replaceChildren();slots.forEach((slot,i)=>{{const choice=selections[i];const row=el('div','reviewrow');if(!choice)row.textContent=slot.label+' → 尚未选择';else{{const candidate=slot.candidates[choice.candidateIndex];row.textContent=slot.label+' → '+candidate.name+'（'+choice.imageType.toUpperCase()+'） → Spec 节点 '+slot.specNodeId+'；参考尺寸 '+slot.targetSize.join(' × ')+'；'+slot.writeScope}}target.append(row)}})}}
for(const [si,slot] of slots.entries()){{const section=el('section','slot');const head=el('div','slothead');const meta=el('div','slotmeta');const title=el('h2');const role=el('span','role',slot.role==='panel'?'面板':slot.role==='button'?'按钮':slot.role==='banner'?'横幅':slot.role==='title'?'标题装饰':slot.role==='pointer'?'指针/光标':slot.role==='icon'?'图标':'其他用途');title.append(role,document.createTextNode(slot.label));meta.append(title);if(slot.description)meta.append(el('p','',slot.description));meta.append(el('p','',slot.usageHint),el('p','',slot.beginnerTip));head.append(meta);const mapping=el('div','mapping');mapping.append(el('strong','',`Spec 节点：${{slot.specNodeId}}`),el('p','',slot.writeScope));head.append(mapping);section.append(head);const target=el('div','target');target.append(el('label','',`目标预览尺寸（${{slot.targetSize[0]}} × ${{slot.targetSize[1]}}）`));if(slot.targetSizeSource==='unity_layout')target.lastChild.textContent+=' · Unity 实测 / 参考分辨率';else target.lastChild.textContent+=' · 示意尺寸';target.append(el('small','','临时改尺寸仅用于比较，不会写回 Spec。'));const width=el('input');width.type='number';width.min='1';width.max='4096';width.value=slot.targetSize[0];width.setAttribute('aria-label','目标宽度');const height=el('input');height.type='number';height.min='1';height.max='4096';height.value=slot.targetSize[1];height.setAttribute('aria-label','目标高度');target.append(width,height);section.append(target);const grid=el('div','grid');
for(const candidate of slot.candidates){{const card=el('article','candidate'+(candidate.recommended?' recommended':''));const cardhead=el('div','cardhead');const pick=el('label','pick');const radio=document.createElement('input');radio.type='radio';radio.name='slot-'+si;radio.value=String(candidate.index);radio.required=true;pick.append(radio,document.createTextNode(candidate.name));cardhead.append(pick);const badge=el('span','badge',candidate.recommended?'推荐候选':'候选');cardhead.append(badge);card.append(cardhead);card.append(el('div','score',`推荐度 ${{candidate.score}}/100 · 第 ${{candidate.rank}} 位`));const previews=el('div','previewrow');for(const mode of candidate.imageTypes){{const box=el('div','previewbox');box.append(el('small','',mode==='simple'?'Simple · 按节点矩形拉伸（不使用 Border）':'Sliced · 九宫格拉伸'));const thumb=el('div','thumb');const canvas=document.createElement('canvas');const image=new Image();const redraw=()=>renderPreview(canvas,image,candidate,mode,Number(width.value),Number(height.value),slot.referencePixelsPerUnit,slot.pixelsPerUnitMultiplier);image.onload=redraw;image.onerror=()=>thumb.append(el('span','caution','预览不可用'));image.src=candidate.imageUrl;thumb.append(canvas);box.append(thumb);previews.append(box);candidate._previewRedraw=candidate._previewRedraw||[];candidate._previewRedraw.push(redraw)}}card.append(previews);card.append(el('div','facts',`切片 ${{candidate.rect[2]}}×${{candidate.rect[3]}} · Border ${{candidate.border.join(', ')}} · Sprite PPU ${{candidate.pixelsPerUnit??'未知'}} / Canvas ${{slot.referencePixelsPerUnit}}`));candidate.reasons.forEach(reason=>card.append(el('div','why','推荐理由：'+reason)));if(candidate.cautions.length)candidate.cautions.forEach(reason=>card.append(el('div','caution','注意：'+reason)));else card.append(el('div','why','未发现导入/尺寸规则方面的明显阻碍；风格仍需人工判断。'));const type=document.createElement('select');type.className='type';type.setAttribute('aria-label',candidate.name+' 图片显示方式');for(const optionValue of candidate.imageTypes){{const option=document.createElement('option');option.value=optionValue;option.selected=optionValue===candidate.recommendedImageType;option.textContent=optionValue==='sliced'?'九宫格拉伸 Sliced':'按节点矩形拉伸 Simple';type.append(option)}}type.addEventListener('change',()=>{{if(selections[si]&&selections[si].candidateIndex===candidate.index){{selections[si].imageType=type.value;updateReview()}}}});card.append(type);radio.addEventListener('change',()=>{{selections[si]={{candidateIndex:candidate.index,imageType:type.value}};updateReview()}});grid.append(card)}}width.addEventListener('input',()=>slot.candidates.forEach(c=>c._previewRedraw?.forEach(fn=>fn())));height.addEventListener('input',()=>slot.candidates.forEach(c=>c._previewRedraw?.forEach(fn=>fn())));section.append(grid);root.append(section)}}updateReview();
for(const [si,slot] of slots.entries()){{const cards=root.querySelectorAll('.slot')[si].querySelectorAll('.candidate');for(const [ci,candidate] of slot.candidates.entries()){{const card=cards[ci];card.querySelector('.badge').textContent=candidate.recommended?'推荐候选':'未优先推荐';card.querySelector('.score').textContent=`结构适配分 ${{candidate.score}}/100 · 第 ${{candidate.rank}} 位`;const note=el('div',candidate.recommended?'why':'caution',candidate.recommendationNote);card.querySelector('.score').after(note)}}}}
document.getElementById('submit').addEventListener('click',async()=>{{const status=document.getElementById('status');if(slots.some((_,i)=>!selections[i])){{status.textContent='请先为每个用途选择一个候选。';return}}const button=document.getElementById('submit');button.disabled=true;try{{const response=await fetch('/submit/'+token,{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{choices:selections}})}});if(!response.ok)throw new Error('会话已过期或提交无效，请返回 Agent 重新创建候选页');status.textContent='素材选择已提交。Agent 还会重新校验并展示生成计划，不会立即生成。';status.style.color='var(--good)'}}catch(error){{status.textContent=error.message;button.disabled=false}}}});
</script></body></html>'''
    return page.encode("utf-8")
