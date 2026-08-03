"""元气搭子 · 启动器（打包版入口）。

双击 exe 即运行：定位 exe 旁的 data/ 作数据目录（数据库/文档/播客音频），
找个空闲端口起 FastAPI 服务，自动打开浏览器。

开发时：在 backend/ 下 `python launcher.py` 同样可用（数据目录 = backend/data）。
"""
import os
import socket
import sys
import threading
import time
import webbrowser
from pathlib import Path


def _base_dir() -> Path:
    """打包版 = exe 所在目录；开发版 = backend/。"""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def _free_port(start: int = 8720) -> int:
    for port in range(start, start + 200):
        with socket.socket() as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    return 8000


def _open_browser_later(port: int) -> None:
    def job():
        for _ in range(120):
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                    break
            except OSError:
                time.sleep(0.5)
        webbrowser.open(f"http://127.0.0.1:{port}")

    threading.Thread(target=job, daemon=True).start()


if __name__ == "__main__":
    base = _base_dir()
    os.environ.setdefault("YQ_DATA_DIR", str(base / "data"))
    os.environ["PYTHONIOENCODING"] = "utf-8"

    port = _free_port()
    print(f"元气搭子启动中 → http://127.0.0.1:{port}  （数据目录：{base / 'data'}）")

    _open_browser_later(port)

    # 显式导入 app 包（否则 PyInstaller 静态分析看不到字符串导入，会把 app 漏掉）
    from app.main import app

    import uvicorn
    # 打包版默认只本机访问（安全）；如需局域网/手机连接，设环境变量 YQ_HOST=0.0.0.0
    host = os.environ.get("YQ_HOST", "127.0.0.1")
    uvicorn.run(app, host=host, port=port, log_level="info")
