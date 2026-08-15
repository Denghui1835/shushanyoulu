"""一次性迁移：把「数学建模备赛」书的科目归位为「数学建模」，接通老教授课堂 39 考点。

背景：该书创建时 subject 填成了「数学」，而系统课程库的科目键是「数学建模」，
导致书内「老教授课堂」入口不出现。此脚本把该书的 subject 修正为「数学建模」。
"""
import sqlite3
from pathlib import Path

DB = Path(__file__).resolve().parent.parent / "data" / "app.db"
PROJECT_ID = "f05b8b48-7011-4bbc-aadf-14a5fa60e8a5"


def main() -> None:
    conn = sqlite3.connect(DB, timeout=10)
    try:
        cur = conn.cursor()
        cur.execute("UPDATE projects SET subject=? WHERE id=?", ("数学建模", PROJECT_ID))
        print("updated rows:", cur.rowcount)
        conn.commit()
        row = cur.execute(
            "SELECT id, subject, category, category_sub FROM projects WHERE id=?",
            (PROJECT_ID,),
        ).fetchone()
        print(row)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
