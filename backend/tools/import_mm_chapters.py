"""导入「数学建模备赛」书的 6 章教学内容（Markdown → 项目章节）。

用法：先启动后端（本脚本走 HTTP 上传接口，与前端同一管道），再运行
    python backend/tools/import_mm_chapters.py
"""
import urllib.request
import uuid
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent.parent  # 仓库根目录
PROJECT_ID = "f05b8b48-7011-4bbc-aadf-14a5fa60e8a5"
URL = "http://127.0.0.1:8010/api/documents/upload"

CHAPTERS = [
    ("docs/数学建模课程/00-数学建模是什么.md", "第〇章 数学建模是什么（零基础）"),
    ("docs/数学建模课程/01-完整流程六步走.md", "第一章 完整流程六步走"),
    ("docs/数学建模课程/02-模型工具箱-优化-预测-评价.md", "第二章 模型工具箱：优化 / 预测 / 评价"),
    ("docs/数学建模课程/03-Python实战-跑通第一个模型.md", "第三章 Python 实战：跑通第一个模型"),
    ("docs/数学建模课程/04-论文写作与格式规范.md", "第四章 论文写作与格式规范"),
    ("docs/数学建模课程/05-备赛四周作战计划.md", "第五章 备赛四周作战计划"),
]


def build_multipart(fields: dict[str, str], file_path: Path) -> tuple[bytes, str]:
    boundary = uuid.uuid4().hex
    parts: list[bytes] = []
    for key, value in fields.items():
        parts.append(
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="{key}"\r\n\r\n'
            f"{value}\r\n".encode("utf-8")
        )
    parts.append(
        (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="{file_path.name}"\r\n'
            "Content-Type: text/markdown\r\n\r\n"
        ).encode("utf-8")
    )
    parts.append(file_path.read_bytes())
    parts.append(b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode("utf-8"))
    return b"".join(parts), boundary


def main() -> None:
    for rel, title in CHAPTERS:
        path = BASE / rel
        if not path.exists():
            print("MISSING:", rel)
            continue
        body, boundary = build_multipart(
            {"project_id": PROJECT_ID, "chapter_title": title}, path
        )
        req = urllib.request.Request(
            URL,
            data=body,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            payload = resp.read().decode("utf-8")
            print(f"OK  {title}  ->  {payload[:160]}")


if __name__ == "__main__":
    main()
