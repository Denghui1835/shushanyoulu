"""提取《计算机二级》练习软件里的 Python 真题题面，生成数据文件。

输入：D:\\softmove\\newpython\\folders\\python.rar（内含 131 个 Word 导出的 htm，UTF-16 编码）
输出：backend/app/core/ncre_real_questions.py（REAL_QUESTIONS 列表）

只提取「题面」——原软件里配套的 .py 答案文件是加密的，这里不含官方答案；
作答后由应用里的 AI 阅卷点评判分。
广告（data.txt 等）不在此范围。
"""
import html
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

RAR = Path(r"D:\softmove\newpython\folders\python.rar")
OUT = Path(__file__).resolve().parent.parent / "app" / "core" / "ncre_real_questions.py"

def py_subtype(py_file: str) -> str:
    """按 PY 文件前缀判操作题子型：PY1xx=基本操作、PY2xx=简单应用、PY3xx=综合应用。"""
    stem = py_file.split(".")[0].upper()
    if stem.startswith("PY1"):
        return "basic"
    if stem.startswith("PY2"):
        return "applied"
    if stem.startswith("PY3"):
        return "comprehensive"
    return "applied"

# 清理 Word 导出 htm 里的跟踪修订噪音
_NOISE = re.compile(r"\b(Clean|false|true|Inserted|Deleted|Formatting)\b", re.I)


def extract_rar(tmp: Path) -> list[Path]:
    """用 bsdtar 解压 rar 到临时目录，返回题面 htm 文件列表。"""
    subprocess.run(["bsdtar", "-xf", str(RAR), "-C", str(tmp)], check=True)
    files = []
    for f in tmp.rglob("*.htm"):
        name = f.name
        if re.fullmatch(r"\d+_\d+\.htm", name):  # 形如 10_41.htm（跳过 .files/header.htm）
            files.append(f)
    return sorted(files)


def read_text(p: Path) -> str:
    """按 UTF-16（BOM）解码；失败回退 gbk/utf-8。"""
    raw = p.read_bytes()
    for enc in ("utf-16", "gbk", "utf-8"):
        try:
            return raw.decode(enc)
        except (UnicodeDecodeError, ValueError):
            continue
    return raw.decode("gbk", errors="ignore")


def strip_html(text: str) -> str:
    # 只保留 <body>…</body>（Word 导出的 head/XML 全是样式噪音）
    m = re.search(r"<body[^>]*>(.*)</body>", text, re.S)
    if m:
        text = m.group(1)
    text = html.unescape(text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = _NOISE.sub(" ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


# Word 残留标记：命中即从该处截断（题面正文后面跟的样式/修订噪音）
_JUNK = re.compile(r"(EN-US ZH-CN|MicrosoftInternetExplorer|/\* Style Definitions \*/|table\.MsoNormalTable|mso-[a-z-]+:)", re.I)


def clean_body(body: str) -> str:
    body = _NOISE.sub(" ", body)
    m = _JUNK.search(body)
    if m:
        body = body[: m.start()]
    return " ".join(body.split()).strip()


def parse_questions(text: str) -> list[dict]:
    """把一页 htm 文本切成若干题（形如 '41、...'）。"""
    out = []
    for part in re.split(r"(?=\d+、)", text):
        m = re.match(r"(\d+)、(.*)", part, re.S)
        if not m:
            continue
        body = clean_body(m.group(2))
        if len(body) < 15:
            continue
        py_refs = re.findall(r"PY\d+(?:-\d+)?\.py", body, re.I)
        out.append({"num": int(m.group(1)), "py": [x.upper() for x in py_refs], "body": body})
    return out


def build_question(item: dict) -> dict | None:
    """组装成 QUESTION_BANK 兼容的 essay 题。"""
    if not item["py"]:
        return None
    subtype = py_subtype(item["py"][0])
    question = f"【真题操作题】{item['body']}"
    return {
        "qtype": "essay",
        "question": question,
        "answer": "（本题为真实真题，官方答案在原软件中加密未提供；按题目要求写代码，提交后由 AI 阅卷点评）",
        "explanation": "真实真题·Python 二级操作题。先读懂题目要求与示例输入/输出，再动手写代码；写完对照 AI 点评自查。",
        "subtype": subtype,
        "source_text": "NCRE 二级 Python 真题（练习软件题面，答案加密）",
    }


def main() -> int:
    if not RAR.exists():
        print(f"找不到 {RAR}")
        return 1
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        files = extract_rar(tmp)
        print(f"解压出题面文件 {len(files)} 个")

        parsed: list[dict] = []
        for f in files:
            text = strip_html(read_text(f))
            parsed.extend(parse_questions(text))
        print(f"原始切分题目 {len(parsed)} 段")

        # 去重（按题面正文前 60 字）
        seen: dict[str, dict] = {}
        for it in parsed:
            key = it["body"][:60]
            if key not in seen:
                seen[key] = it
        print(f"去重后 {len(seen)} 道")

        questions = []
        for it in seen.values():
            q = build_question(it)
            if q:
                questions.append(q)

        OUT.write_text(
            "#!/usr/bin/env python\n"
            "# -*- coding: utf-8 -*-\n"
            '"""真实真题数据：从《计算机二级》练习软件提取的 Python 操作题题面。\n\n'
            "官方答案在原软件中加密未提供；作答由应用内 AI 阅卷点评。\n"
            '"""\n\n'
            "REAL_QUESTIONS = " + json.dumps(questions, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"写入 {OUT}，共 {len(questions)} 题")
        return 0


if __name__ == "__main__":
    sys.exit(main())
