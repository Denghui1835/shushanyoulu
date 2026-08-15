"""「一起学」演示数据：临时插入几条学习动态（含虚拟伙伴），截图/验证后 clean 清理。"""
import sqlite3
import sys
from pathlib import Path

DB = Path(__file__).resolve().parent.parent / "data" / "app.db"

POSTS = [
    ("local_user", "学习者", "checkin", "完成了今日打卡，连续打卡 3 天 🔥", 10),
    ("demo_amy", "阿米", "lesson", "学完「数学建模 · 优化模型入门」，已掌握 ✅", 0),
    ("demo_bob", "小波", "mock", "完成一场全真模拟（python），得分 82 分，合格！🎉", 0),
]


def seed() -> None:
    conn = sqlite3.connect(DB, timeout=10)
    cur = conn.cursor()
    for uid, name, kind, content, points in POSTS:
        cur.execute(
            "INSERT INTO social_posts (id, user_id, username, kind, content, points, created_at) "
            "VALUES (?,?,?,?,?,?, datetime('now'))",
            (f"demo_{uid}_{kind}", uid, name, kind, content, points),
        )
    conn.commit()
    conn.close()
    print("seeded")


def clean() -> None:
    conn = sqlite3.connect(DB, timeout=10)
    cur = conn.cursor()
    cur.execute("DELETE FROM social_posts WHERE id LIKE 'demo_%'")
    cur.execute("DELETE FROM social_likes WHERE post_id LIKE 'demo_%'")
    cur.execute(
        "DELETE FROM study_logs WHERE kind='social' "
        "AND (detail LIKE '%阿米%' OR detail LIKE '%小波%' OR detail LIKE '%学习者%' OR detail LIKE '%demo_%')"
    )
    conn.commit()
    conn.close()
    print("cleaned")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "clean":
        clean()
    else:
        seed()
