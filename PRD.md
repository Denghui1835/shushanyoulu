# 元气搭子 · AI 主动伴学 — 产品需求文档（简版）

## 1. 产品定位

**一句话**：不是让你一个人面对学习资料的"工具"，而是一个**主动陪伴你学习全过程的 AI 伙伴**。

元气搭子会主动了解你的学习目标、制定学习计划、在你学习/练习/复习的每个环节陪伴引导，用 FSRS 间隔复习科学安排复习节奏，并用元气值激励你持续学习。

## 2. 核心差异化：主动陪伴引导

| 传统工具（KnowAll 风格） | 元气搭子 |
|---|---|
| 等用户自己发现功能 | AI 开场就问你目标，主动引导 |
| 用户自己规划 | AI 根据目标+资料+时间生成个性化计划 |
| 记不清学到哪 | 伴学 Agent 感知进度，主动建议"下一步该做什么" |
| 忘记复习 | 到期闪卡主动提醒 |
| 缺乏动力 | 元气值激励 + 真诚的进度喝彩 |

## 3. 核心功能（MVP v0.1）

- **伴学对话**（SSE 流式）：对话即首页，AI 主动开场、感知进度、引导学习闭环
- **学习计划**：AI 生成分阶段计划 + 每日任务，前端可标记完成
- **学习闭环**：上传资料 → 知识树 → 练习题 → 闪卡复习
- **复习提醒**：FSRS 算法安排闪卡复习，到期在侧栏和首页展示
- **元气值**：学习行为累积激励分
- **资料库**：PDF/Word/Markdown/TXT/PPT 上传，自动解析分块

## 4. 技术架构

```
React + Vite + Ant Design  (:5173)
        ↓ HTTP / SSE
FastAPI + SQLAlchemy (async)  (:8000)
        ↓
SQLite（本地优先，数据不出本机）
        ↓
LLM：DeepSeek（统一适配器，可换 Claude/OpenAI/Ollama）
```

关键设计：
- **轻量检索**：jieba 词法检索替代重型向量库，快速启动；接口独立可换向量后端
- **复用 KnowAll 适配层**：api_scheduler（缓存/限流/重试/多供应商）
- **本地优先**：SQLite 单用户，启动即用

## 5. 快速开始

```bash
# 前置：Python 3.10+、Node 18+
# 配置 API Key：复制 backend/.env.example 为 .env，填入 DEEPSEEK_API_KEY
start.bat
```

## 6. 项目结构

```
元气搭子/
├── backend/
│   ├── app/
│   │   ├── api/            # companion/documents/knowledge/questions/flashcards/pipeline/study
│   │   ├── core/           # companion(伴学Agent)/quiz/memory(FSRS)/knowledge/pipeline/parsing/retrieval
│   │   │   └── api_scheduler/   # 复用 KnowAll LLM 适配层（含流式扩展）
│   │   ├── models/         # 伴学层(User/Plan/PlanTask) + 内容层 + 对话层 + 调度层
│   │   ├── config.py
│   │   ├── database.py
│   │   └── main.py
│   └── requirements.txt
├── frontend/
│   └── src/pages/          # Companion(首页)/Plan/Upload/Knowledge/Quiz/Flashcard
├── start.bat
└── PRD.md
```

## 7. 路线图

- v0.1（当前 MVP）：伴学对话 + 学习计划 + 学习闭环 + 复习提醒 + 元气值
- v0.2：学习数据统计看板、薄弱点分析、计划动态调整
- v0.3：向量检索升级、多用户/云端同步、移动端适配
