"""文档文件路径解析。

库里 `documents.file_path` 存的是**绝对路径**，所以项目目录一改名/搬迁（例如
`元气搭子` → `书山有路`），或者打包版把 data/ 挪到 exe 旁边，所有存量记录就全都指向
一个不存在的路径——表现为「PDF 阅读页空白、听读无正文、播客生成不出来」，
而且**不报错**，很容易被当成功能坏了。

这里做一次兜底解析：原路径不在，就按文件名去当前 `settings.document_dir` 里找。
纯读取、不改库，所以对存量数据是安全的自愈；将来再搬家也照样能找回来。
"""
import logging
from pathlib import Path

from app.config import settings

logger = logging.getLogger("yuanqi.paths")

_warned: set[str] = set()


def resolve_doc_file(file_path: str | None) -> Path | None:
    """把库里存的文档路径解析成真实存在的路径；找不到返回 None。"""
    if not file_path:
        return None

    p = Path(file_path)
    if p.exists():
        return p

    # 兜底：同名文件是否在当前的 documents 目录下（目录改名/搬迁后的自愈）
    candidate = Path(settings.document_dir) / p.name
    if candidate.exists():
        # 同一份路径只提醒一次，避免刷屏
        key = str(p.parent)
        if key not in _warned:
            _warned.add(key)
            logger.warning(
                "文档路径已失效，按文件名自愈：%s → %s（库里的旧前缀是 %s）",
                p.name, candidate, p.parent,
            )
        return candidate

    logger.warning("文档文件找不到：%s（也不在 %s 下）", file_path, settings.document_dir)
    return None