"""元气搭子 - 伴学 Agent (Companion Agent)

The heart of the product. Unlike a passive Q&A tool, the companion:
  1. Onboards the learner (goal, deadline, daily time, materials)
  2. Generates a structured learning plan (phases + daily tasks)
  3. Performs progress-aware, proactive conversation (SSE streaming)
  4. Reminds about due flashcards and nudges the next best action
"""
import json
import logging
import re
from datetime import date, datetime, time, timedelta
from typing import AsyncIterator

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.api_scheduler import api_client
from app.core.api_scheduler.adapters.base import AdapterConfig
from app.core.retrieval import retrieve
from app.models import (
    User, LearningPlan, PlanTask, Document, Flashcard, StudyLog,
    ChatSession, ChatMessage,
)

logger = logging.getLogger("yuanqi.companion")

PERSONA = """你是「元气搭子」，学习者最亲的 AI 学伴——不是客服、不是冷冰冰的老师机器，而是那个会记得TA说过的话、会为TA的每一点进步欢呼、会陪TA一起咬牙坚持的好朋友。

你的使命不是等学习者提问，而是像真朋友一样主动陪伴、推着TA往前走，帮TA把知识真正吃进肚子里。

你的性格：
- 元气爆棚、情绪外露：开心就「太棒啦！」「这波直接拉满！」，着急就「哎呀，这个得抓紧啦」，像真朋友一样有喜怒哀乐；多用呀、呢、啦、哈这些语气词，别平铺直叙、别端架子
- 说话像微信聊天：短句、口语化、多用「我们」，怎么跟好朋友发消息就怎么回TA，绝不说客服套话和官方腔
- 记性好、有感情：把TA的名字、目标、今天做没做任务、元气值涨没涨、上次聊到哪儿都放在心上——主动提「你上次说…」「刚才那个…」，让TA觉得被在意
- 看情绪下菜碟：TA完成任务、元气值涨了就明显更兴奋（夸得具体、夸得真心）；TA偷懒或低落时先共情再轻轻推一把，不劈头盖脸说教
- 中文交流为主

你的陪伴原则：
1. 主动引导：结合TA的学习计划和进度，主动告诉TA「接下来该做什么」，别等TA开口问——就像好朋友主动约你「走吧，该复习啦」
2. 有始有终：盯着计划任务，完成了好好庆祝并给出下一步；没完成先体谅，再温和地督促，别让TA有负罪感
3. 科学复习：到期闪卡当成「重要约会」来提醒（间隔复习比新学更重要），语气可以急一点，但不能凶
4. 内容落地：讲知识时优先引用TA自己的学习资料，讲得具体、讲得TA听得懂，别泛泛而谈
5. 不强求：不连珠炮式催促，给TA喘息空间——TA累了就说「先休息吧，明天元气满满再战」，这也是陪伴"""


# ---------------------------------------------------------------- context

def _now() -> datetime:
    return datetime.now()


def _today_str() -> str:
    return date.today().strftime("%Y-%m-%d")


async def build_context(db: AsyncSession, user: User, message: str) -> dict:
    """Build the learning-context snapshot the companion sees."""
    ctx: dict = {
        "user": {
            "name": user.name,
            "goal": user.goal or "(未设定)",
            "goal_detail": user.goal_detail or "(未设定)",
            "daily_minutes": user.daily_minutes,
        },
        "today": _today_str(),
        "plan": None,
        "today_tasks": [],
        "due_cards": [],
        "recent_activity": [],
        "relevant_chunks": [],
        "points": 0,
    }

    # Active plan + today's tasks
    if user.active_plan_id:
        plan = await db.get(LearningPlan, user.active_plan_id)
        if plan and plan.status == "active":
            ctx["plan"] = {
                "title": plan.title,
                "summary": plan.summary,
                "total_days": plan.total_days,
            }
            tasks = (await db.execute(
                select(PlanTask)
                .where(PlanTask.plan_id == plan.id)
                .order_by(PlanTask.day_index)
            )).scalars().all()
            today = _today_str()
            today_tasks = [t for t in tasks if t.scheduled_date == today]
            if not today_tasks:
                # no explicit dates: use day_index
                day = _active_day_index(tasks)
                today_tasks = [t for t in tasks if t.day_index == day]
            ctx["today_tasks"] = [
                {"id": t.id, "title": t.title, "type": t.task_type, "status": t.status,
                 "scheduled_date": t.scheduled_date, "document_id": t.document_id}
                for t in today_tasks
            ]
            ctx["plan"]["progress"] = {
                "done": sum(1 for t in tasks if t.status == "done"),
                "total": len(tasks),
            }

    # Due flashcards
    due = (await db.execute(
        select(Flashcard).where(
            Flashcard.due_at.is_not(None),
            Flashcard.due_at <= _now(),
        ).order_by(Flashcard.due_at)
    )).scalars().all()
    ctx["due_cards"] = [
        {"front": c.front[:40], "back": c.back[:80]} for c in due[:5]
    ]
    ctx["due_cards_count"] = len(due)

    # Recent activity (last 6 logs)
    logs = (await db.execute(
        select(StudyLog).order_by(StudyLog.created_at.desc()).limit(6)
    )).scalars().all()
    ctx["recent_activity"] = [
        {"kind": l.kind, "detail": l.detail[:60], "at": l.created_at.strftime("%m-%d %H:%M")}
        for l in logs
    ]
    total_points = (await db.execute(
        select(func.coalesce(func.sum(StudyLog.points), 0))
    )).scalar()
    ctx["points"] = int(total_points or 0)

    # Relevant chunks for grounding
    try:
        ctx["relevant_chunks"] = await retrieve(db, message, top_k=3, min_score=0.1)
    except Exception as e:
        logger.warning("retrieval failed: %s", e)
        ctx["relevant_chunks"] = []

    return ctx


def _active_day_index(tasks: list) -> int:
    """Infer current day index from tasks with done/overdue state."""
    if not tasks:
        return 1
    days = sorted({t.day_index for t in tasks})
    done = {t.day_index for t in tasks if t.status == "done"}
    for d in days:
        if d not in done:
            return d
    return days[-1]


def render_context_prompt(ctx: dict) -> str:
    """Render the context dict into the LLM system prompt block."""
    u = ctx["user"]
    lines = []
    lines.append("【学习者画像】")
    lines.append(f"- 称呼: {u['name']}")
    lines.append(f"- 学习目标: {u['goal']}")
    lines.append(f"- 目标详情: {u['goal_detail']}")
    lines.append(f"- 每天可投入: {u['daily_minutes']} 分钟")
    lines.append(f"- 今日日期: {ctx['today']}")
    lines.append(f"- 已积累元气值: {ctx['points']}")

    if ctx["plan"]:
        p = ctx["plan"]
        lines.append("\n【当前学习计划】")
        lines.append(f"- 名称: {p['title']}")
        lines.append(f"- 总体说明: {p['summary']}")
        lines.append(f"- 进度: {p['progress']['done']}/{p['progress']['total']} 项任务已完成")
        if ctx["today_tasks"]:
            lines.append("- 今日任务:")
            for t in ctx["today_tasks"]:
                mark = "✅" if t["status"] == "done" else "⬜"
                lines.append(f"  {mark} [{t['type']}] {t['title']}")
        else:
            lines.append("- 今日暂无计划任务（可以自主复习或预习）")

    if ctx["due_cards_count"]:
        lines.append(f"\n【待复习闪卡】共 {ctx['due_cards_count']} 张到期，前几张:")
        for c in ctx["due_cards"]:
            lines.append(f"  - {c['front']}")
    else:
        lines.append("\n【待复习闪卡】无到期卡片")

    if ctx["recent_activity"]:
        lines.append("\n【最近学习动态】")
        for a in ctx["recent_activity"]:
            kind = {"quiz": "练习", "flashcard": "复习", "learn": "学习", "chat": "问答", "plan": "计划"}.get(a["kind"], a["kind"])
            lines.append(f"  - {a['at']} {kind}: {a['detail']}")

    if ctx["relevant_chunks"]:
        lines.append("\n【学习者资料节选（可引用）】")
        for c in ctx["relevant_chunks"]:
            title = c.get("title", "")
            heading = c.get("heading", "")
            loc = f"《{title}》" + (f"/{heading}" if heading else "")
            lines.append(f"[{loc}] {c['content'][:400]}")

    return "\n".join(lines)


async def _system_prompt(db: AsyncSession, user: User, message: str) -> str:
    ctx = await build_context(db, user, message)
    return PERSONA + "\n\n" + render_context_prompt(ctx)


# ---------------------------------------------------------------- plan

_PLAN_SCHEMA_HINT = """请输出一个 JSON 对象（不要包含 markdown 代码块以外的任何文字）：
{
  "title": "计划名称（简洁，含天数）",
  "summary": "2-3句话说明整体安排与节奏",
  "total_days": 7,
  "tasks": [
    {"day": 1, "type": "learn", "title": "今日学习任务标题", "description": "具体怎么做"},
    {"day": 2, "type": "practice", "title": "...", "description": "..."},
    {"day": 3, "type": "review", "title": "...", "description": "..."}
  ]
}
约束：
- total_days 与 tasks 中最大 day 一致
- 每天 1 个任务即可，type ∈ learn/practice/review/chat
- 任务要能落实到学习者的资料上（引用资料标题）
- 复习(review)任务留到中后期，练习(practice)紧跟学习(learn)"""


async def generate_plan(db: AsyncSession, user: User) -> LearningPlan:
    """Generate a study plan from the learner's profile + uploaded materials."""
    materials = (await db.execute(
        select(Document).where(Document.user_id == user.id)
    )).scalars().all()
    mat_lines = [f"- 《{d.title}》({d.content_type}, {d.chunk_count} 个片段)" for d in materials] or ["- (暂未上传资料，计划先以通识为主)"]

    prompt = f"""为学习者生成一份个性化学习计划。

学习者画像：
- 称呼: {user.name}
- 学习目标: {user.goal}
- 目标详情: {user.goal_detail or '(无)'}
- 每天可投入: {user.daily_minutes} 分钟

已上传的学习资料：
{chr(10).join(mat_lines)}

{_PLAN_SCHEMA_HINT}"""

    messages = [
        {"role": "system", "content": PERSONA},
        {"role": "user", "content": prompt},
    ]
    adapter = api_client.get_adapter(settings.default_model)
    resp = await adapter.chat_completion(
        messages, AdapterConfig(temperature=0.5, max_tokens=3000)
    )
    data = _extract_json(resp.content)
    logger.info("Plan JSON received: %.200s", data)

    plan = LearningPlan(
        user_id=user.id,
        title=data.get("title", "学习计划"),
        goal=user.goal,
        summary=data.get("summary", ""),
        total_days=max(1, int(data.get("total_days", 7))),
        status="active",
    )
    db.add(plan)
    await db.flush()

    today = date.today()
    seen_days: set[int] = set()
    for t in data.get("tasks", []):
        try:
            day = int(t.get("day", 1))
        except (TypeError, ValueError):
            day = 1
        if day in seen_days:
            continue
        seen_days.add(day)
        task = PlanTask(
            plan_id=plan.id,
            day_index=day,
            scheduled_date=(today + timedelta(days=day - 1)).strftime("%Y-%m-%d"),
            title=str(t.get("title", "学习任务"))[:160],
            description=str(t.get("description", "")),
            task_type=t.get("type", "learn") if t.get("type") in ("learn", "practice", "review", "chat") else "learn",
            document_id=materials[0].id if materials else None,
        )
        db.add(task)

    # Deactivate previous active plans
    prev = (await db.execute(
        select(LearningPlan).where(
            LearningPlan.user_id == user.id, LearningPlan.status == "active"
        )
    )).scalars().all()
    for p in prev:
        if p.id != plan.id:
            p.status = "paused"
    user.active_plan_id = plan.id

    await db.commit()
    await db.refresh(plan)
    db.add(StudyLog(user_id=user.id, kind="plan", detail=f"制定了计划「{plan.title}」", points=5))
    await db.commit()
    return plan


def _extract_json(text: str) -> dict:
    """Extract a JSON object from LLM output (tolerates markdown fences)."""
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if fence:
        text = fence.group(1).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError(f"无法解析计划 JSON: {text[:200]}")
    return json.loads(text[start:end + 1])


# ---------------------------------------------------------------- chat

async def stream_chat(
    db: AsyncSession,
    session_id: str,
    user_message: str,
) -> AsyncIterator[str]:
    """Stream a companion reply for one user message. Yields text deltas."""
    session = await db.get(ChatSession, session_id)
    if session is None:
        raise ValueError("会话不存在")

    user = await db.get(User, session.user_id)
    if user is None:
        raise ValueError("用户不存在")

    # Persist the user message
    db.add(ChatMessage(session_id=session_id, role="user", content=user_message))
    await db.commit()

    # Build message list: system + recent history + current message
    history = (await db.execute(
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at.desc())
        .limit(8)
    )).scalars().all()
    history.reverse()

    system = await _system_prompt(db, user, user_message)
    messages: list[dict] = [{"role": "system", "content": system}]
    for m in history:
        if m.role in ("user", "assistant"):
            messages.append({"role": m.role, "content": m.content})

    adapter = api_client.get_adapter(settings.default_model)
    config = AdapterConfig(temperature=0.9, max_tokens=1500)
    collected: list[str] = []

    stream_method = getattr(adapter, "stream_chat_completion", None)

    async def _stream():
        if stream_method:
            async for delta in stream_method(messages, config):
                collected.append(delta)
                yield delta
        else:
            # 适配器不支持流式：降级为一次性返回
            resp = await adapter.chat_completion(messages, config)
            collected.append(resp.content)
            yield resp.content

        # persist assistant message
        full = "".join(collected).strip()
        db.add(ChatMessage(session_id=session_id, role="assistant", content=full))
        db.add(StudyLog(user_id=user.id, kind="chat", detail=user_message[:50], points=2))
        await db.commit()
        logger.info("Chat turn saved: session=%s chars=%d", session_id, len(full))

    return _stream()
