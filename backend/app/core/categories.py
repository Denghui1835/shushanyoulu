"""学科分类体系 — 三级分类：学科门类 → 一级学科 → 具体课程/书.

类似图书馆分类：不把《数学分析》当一级，而是「理学 → 数学 → 《数学分析》」。
内置门类树 + 旧 subject 数据归位映射。
"""
from typing import Any

# 一级：学科门类 → 二级：一级学科（常用子集，可扩充）
CATEGORY_TREE: dict[str, list[str]] = {
    "理学": ["数学", "统计学", "物理学", "化学", "生物学", "地理学"],
    "工学": ["人工智能", "计算机科学与技术", "软件工程", "电子信息", "机械工程", "土木工程", "自动化"],
    "经济学": ["应用经济学", "理论经济学", "金融学"],
    "管理学": ["管理科学与工程", "工商管理", "公共管理", "农林经济管理"],
    "教育学": ["教育学", "心理学"],
    "文学": ["中国语言文学", "外国语言文学", "新闻传播学"],
    "法学": ["法学", "社会学", "政治学"],
    "农学": ["作物学", "植物保护", "园艺学", "农业资源与环境", "畜牧学"],
    "医学": ["基础医学", "临床医学", "药学", "公共卫生与预防医学"],
    "艺术学": ["美术学", "设计学", "音乐与舞蹈学"],
    "哲学": ["哲学"],
    "历史学": ["中国史", "世界史"],
}

# 学科门类（一级）列表，保持稳定顺序
def categories() -> list[str]:
    return list(CATEGORY_TREE.keys())


def subcategories(category: str) -> list[str]:
    return CATEGORY_TREE.get(category, [])


def category_tree() -> dict[str, list[str]]:
    return CATEGORY_TREE


# 旧 subject（课程目录时代的一级学科名）→ (门类, 一级学科) 归位映射
_LEGACY_SUBJECT_MAP: dict[str, tuple[str, str]] = {
    "3DGS": ("工学", "人工智能"),
    "数学建模": ("理学", "数学"),
    "数学分析": ("理学", "数学"),
    "高等代数": ("理学", "数学"),
    "数理统计": ("理学", "统计学"),
    "机器学习": ("工学", "人工智能"),
    "深度学习": ("工学", "人工智能"),
    "计算机": ("工学", "计算机科学与技术"),
    "Python程序设计": ("工学", "计算机科学与技术"),
    "C语言程序设计": ("工学", "计算机科学与技术"),
    "线性代数": ("理学", "数学"),
    "概率论": ("理学", "统计学"),
}


def legacy_mapping(subject: str) -> tuple[str, str] | None:
    """旧 subject 值 → (门类, 一级学科)。匹配失败返回 None。"""
    if not subject:
        return None
    return _LEGACY_SUBJECT_MAP.get(subject.strip())


def normalize_category(category: str | None, category_sub: str | None,
                       fallback_subject: str = "") -> tuple[str, str]:
    """规整分类输入：
    - 显式给了门类/子学科 → 校验并返回
    - 只给了旧 subject → 用归位映射
    - 都无 → 未分类
    """
    cat = (category or "").strip()
    sub = (category_sub or "").strip()

    if cat and cat in CATEGORY_TREE:
        if sub and sub not in CATEGORY_TREE[cat]:
            sub = ""
        return cat, sub

    # 尝试用旧 subject 归位
    mapped = legacy_mapping(fallback_subject or sub or cat)
    if mapped:
        return mapped

    return "", ""
