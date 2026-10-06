"""系统 / 元信息接口：把「本服务提供了哪些 HTTP 接口」报给设置页。

为什么不直接让前端读 `/openapi.json`：前端 dev server 只把 `/api` 反代到后端
（见 `frontend/vite.config.ts`），而 `/openapi.json` 挂在域名根上，开发环境下
前端根本够不着。这里包一层，同时把前端不关心的部分（`components`/`schemas`）
裁掉，只留「方法 + 路径 + 说明 + 分组」——159 个接口压到十几 KB。

暴露面：**没有新增**。FastAPI 默认就已经公开了 `/openapi.json` 与 `/docs`，
本接口返回的是同一份信息的精简版。
"""
import re

from fastapi import APIRouter, Request

router = APIRouter(prefix="/api/system", tags=["system"])

# 分组的中文名与展示顺序（前端设置页照这个渲染）。
# 顺序按产品主线排：听读 → 内容 → 学习 → 社区 → 账号 → 系统；
# 表里没有的 tag 排在最后，按字母序，免得新模块被漏掉。
_GROUP_LABELS: dict[str, str] = {
    "listen": "听读", "podcast": "播客", "reading": "阅读", "companion": "伴学",
    "lesson": "课程卡", "course": "课程", "documents": "文档", "projects": "项目 / 仓库",
    "knowledge": "知识点", "questions": "题库", "flashcards": "闪卡",
    "study": "学习计划", "pipeline": "导入管线", "schedules": "日程", "kanban": "看板",
    "community": "社区", "social": "一起学",
    "auth": "登录注册", "profile": "个人资料",
    "tts": "语音合成", "stats": "统计", "system": "系统", "admin": "管理",
}
_GROUP_ORDER = list(_GROUP_LABELS)
_METHOD_ORDER = {"GET": 0, "POST": 1, "PUT": 2, "PATCH": 3, "DELETE": 4}
_CJK_RE = re.compile(r"[一-鿿]")


def _route_label(op: dict) -> str:
    """挑一句给人看的中文说明。

    FastAPI 在没有显式 summary 时，会拿**函数名**自动生成英文摘要
    （`listen_album` → "Listen Album"），直接展示给中文界面很别扭。
    而 docstring 转成的 description 里，160 个接口有 100 个首行是中文
    （`"课程目录：某学科的知识点列表…"`），那才是写给人看的。所以优先取
    description 首行，只有它不含中文时才退回自动摘要。
    """
    desc = (op.get("description") or "").strip()
    first = desc.splitlines()[0].strip() if desc else ""
    if first and _CJK_RE.search(first):
        return first[:80]
    return (op.get("summary") or "").strip()


@router.get("/routes")
async def list_routes(request: Request):
    """本服务全部 HTTP 接口，按分组整理，供设置页展示。"""
    spec = request.app.openapi()
    groups: dict[str, list[dict]] = {}
    for path, ops in (spec.get("paths") or {}).items():
        for method, op in ops.items():
            m = method.upper()
            if m not in _METHOD_ORDER:
                continue  # 只留真正的业务方法，滤掉 head/options
            tag = (op.get("tags") or ["(未分组)"])[0]
            groups.setdefault(tag, []).append({
                "method": m,
                "path": path,
                "summary": _route_label(op),
                "deprecated": bool(op.get("deprecated")),
            })

    out = []
    for tag, routes in groups.items():
        routes.sort(key=lambda r: (r["path"], _METHOD_ORDER[r["method"]]))
        out.append({
            "tag": tag,
            "label": _GROUP_LABELS.get(tag, tag),
            "count": len(routes),
            "routes": routes,
        })
    out.sort(key=lambda g: (_GROUP_ORDER.index(g["tag"])
                            if g["tag"] in _GROUP_ORDER else len(_GROUP_ORDER), g["tag"]))
    return {"total": sum(g["count"] for g in out), "groups": out}