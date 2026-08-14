"""计算机二级 · Python 语言程序设计 备考课程种子数据.

把「5 周冲刺备考路线」作为一本可读的书种进书架：
- Project（工学 → 计算机科学与技术，公开到广场）
- 每章 = 一个学习阶段，Markdown 内容含逐日任务与自检清单
- 复用 parse_file / chunk_text 生成 Chunk，章节可在阅读页阅读/朗读/总结/挖空
"""
import json
import logging
import re
import uuid
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ncre_real_questions import REAL_QUESTIONS
from app.core.ncre_public_base import PUBLIC_BASE_QUESTIONS

from app.config import settings
from app.core.parsing import parse_file, chunk_text
from app.models import Project, Document, Chunk, Question

logger = logging.getLogger("yuanqi.ncre")

COURSE_TITLE = "计算机二级 · Python 语言程序设计"
COURSE_ICON = "🐍"
COURSE_DESC = (
    "全国计算机等级考试二级 Python 语言程序设计，5 周冲刺备考路线。"
    "每天 1~1.5 小时：40 分选择题靠刷题、60 分操作题靠动手，60 分合格一次过！"
)

# 章节：每个阶段一章，内容为逐日任务 + 自检清单
CHAPTERS: list[dict] = [
    {"title": "备考总纲与考试结构", "md": """# 备考总纲与考试结构

全国计算机等级考试（NCRE）二级 · Python 语言程序设计。目标：60 分合格，机考一次过。

## 考试结构（机考 120 分钟，满分 100）

| 题型 | 分值 | 说明 |
| --- | --- | --- |
| 单项选择题 | 40 分 | 公共基础知识约 10 分 + Python 知识约 30 分 |
| 基本操作题 | 15 分 | 3 小题，补全/修改一段小程序 |
| 简单应用题 | 25 分 | 2 小题，按需求编写函数或程序 |
| 综合应用题 | 20 分 | 1 大题，组合数据类型 + 文件 + 生态库 |

合格线：60 分。选择题稳定拿到 30+，操作题完整写出 3 道基本 + 1 道简单，就很稳。

## 考试环境

- Python 3.x（考场一般为 3.5+），用 IDLE 编写运行，另自带 Python Shell。
- 题目在考试系统中打开，写完点「保存」再「运行」验证，最后交卷。
- 掌握 IDLE 的打开文件、运行（F5）、看报错（Traceback）就够用。

## 通过策略

1. 选择 40 分：靠刷真题选择；公共基础 10 分考前突击背记。
2. 操作 60 分：每类题型动手写，别只看不练——考场是上机，手不熟等于白搭。
3. 时间分配：选择 30 分钟内解决，操作题 70 分钟，留 20 分钟检查保存。
4. 报错不可怕：看懂 Traceback 的「最后一行」就能改对，练习时故意写错看报错。

## 5 周总览

- 第 1 周 · 语法地基：程序格式、数据类型、流程控制
- 第 2 周 · 组合数据类型与函数：列表/字符串/字典 + 函数
- 第 3 周 · 文件、异常与计算生态：文件、CSV/JSON、标准库/生态库
- 第 4 周 · 真题刷题：每天一套操作题 + 错题补讲
- 第 5 周 · 全真模拟与冲刺：3 次限时模拟 + 错题复盘

## 题库安装（实操练习用）

备考用的「计算机二级 python 题库安装包」：含历年真题与操作题练习，直接安装到电脑刷题。

- 网盘资源：
  - 百度网盘：https://pan.baidu.com/s/1BzVJzCcy33h4v4xwnUVeXw?pwd=8888 （提取码 8888）
  - 夸克网盘：https://pan.quark.cn/s/d8bb207d82b3
- 安装方法：把文件里的题库安装包保存到网盘 → 下载到电脑桌面 → 双击安装 → 有问题随时咨询客服
- 使用节奏：第 4 周「真题刷题」、第 5 周「全真模拟」都用这套题库，模拟时用它的考试模式限时做"""},
    {"title": "第 1 周 · 语法地基", "md": """# 第 1 周 · 语法地基

本周目标：看懂并写出最简单的 Python 程序，掌握程序格式、数据、分支、循环。

## 周一 · 程序格式与缩进

- 了解注释（#）、多行注释（''' '''）、标识符命名规则（字母/下划线开头，可含数字）
- 记住常见保留字：if / else / for / while / def / return / import / from / True / False / None
- **缩进就是语法**：同一代码块必须同一缩进，Tab 与空格不要混用
- 自检：写一个 3 行的程序，故意改错缩进，看报错（IndentationError）

## 周二 · 变量与基本数据类型

- 整数 int、浮点 float、字符串 str、布尔 bool、空值 NoneType
- 类型转换：int() / float() / str() / bool()；注意字符串转 int 的坑（'12.3' 会报错）
- 运算符：+ - * / // % **；注意 / 得到浮点、// 整除、% 取余
- 自检：算一下 7 // 2、7 % 2、2 ** 3 各是多少

## 周三 · 输入输出与格式化

- input() 一定返回字符串，用之前要转类型
- print() 多参数、sep、end 参数
- 三种格式化：f-string（f"{x:.2f}"）、format()、% 占位
- 自检：读入两个数，输出它们的和与平均值（保留两位小数）

## 周四 · 分支结构

- if / elif / else 的语法与缩进
- 比较运算符 == != > < >= <=；逻辑 and / or / not；成员 in
- 注意 == 与 = 的区别；if x: 与 if x is not None: 的语义
- 自检：读入成绩，≥90 输出「优秀」、≥60 输出「及格」、否则「不及格」

## 周五 · 循环结构

- for 与 range：range(n)、range(a,b)、range(a,b,step)
- while 与循环变量；break 跳出、continue 跳过
- 循环 else（正常结束才执行 else）
- 自检：输出 1~100 中所有能被 3 整除的数的和

## 周末 · 公共基础 + 操作题

- 公共基础：算法概念、时间复杂度（O 记号，常识判断即可）
- 动手：做 3 道「基本操作题」真题，先自己写再对答案"""},
    {"title": "第 2 周 · 组合数据类型与函数", "md": """# 第 2 周 · 组合数据类型与函数

本周目标：掌握四大组合数据类型和函数的写法——操作题的主力。

## 周一 · 列表 list

- 创建、索引、切片 list[a:b]
- 增删改：append / extend / insert / remove / pop / del
- 排序与统计：sort / sorted / reverse / index / count / sum / max / min
- 列表推导式：[表达式 for x in 列表 if 条件]
- 自检：用推导式生成 1~20 的平方列表，再求总和

## 周二 · 字符串进阶

- 切片、len、in；字符串不可变（要改只能重建）
- 常用方法：upper / lower / strip / replace / split / join / find / count / startswith
- format / f-string 高级用法：:>10 右对齐、:.2f
- 自检：把一句话按空格拆成单词列表，统计每个单词出现次数

## 周三 · 元组与集合

- 元组 tuple：不可变，可解包 a, b = (1, 2)
- 集合 set：去重、in 判断、集合运算（& | - ^）
- 何时用集合：快速去重、判断成员
- 自检：求两个列表的交集、并集

## 周四 · 字典 dict

- 键值对，键必须不可变；dict() / 大括号
- 增删改查：d[key] / get / setdefault / keys / values / items / pop
- 遍历：for k, v in d.items()
- 自检：统计字符串中各字符出现次数（经典真题！）

## 周五 · 函数

- def 定义、参数：位置参数、默认参数、关键字参数、*args/**kwargs（了解）
- 返回值 return；无 return 返回 None
- lambda 匿名函数、全局变量 global（了解）
- 递归：必须有递归出口（n 的阶乘、斐波那契）
- 自检：写 is_prime(n) 判断素数；写阶乘递归

## 周末 · 公共基础 + 简单应用

- 公共基础：栈、队列、二叉树（前/中/后序，常识）
- 动手：做 2 道「简单应用题」真题，重点练「按需求写函数」"""},
    {"title": "第 3 周 · 文件、异常与计算生态", "md": """# 第 3 周 · 文件、异常与计算生态

本周目标：文件读写、CSV/JSON 数据格式化、异常处理，以及高频生态库。

## 周一 · 文件读写

- open(path, mode)：'r' / 'w' / 'a' / 'rb' / 'wb'，encoding='utf-8'
- with open(...) as f: 自动关闭；f.read() / f.readline() / f.readlines() / f.write()
- 逐行遍历 for line in f
- 自检：读一个文本文件，统计行数与单词数

## 周二 · CSV 与 JSON

- csv 模块：csv.reader / csv.writer（处理二维列表）
- 二维数据：行列组织，读写二维表
- json 模块：json.dumps / json.loads / json.dump / json.load；ensure_ascii=False
- 自检：把成绩字典列表写入 CSV，再读回计算平均分

## 周三 · 异常处理

- try / except / else / finally 的语义与顺序
- 捕获多种异常：except (ValueError, TypeError):；except Exception as e:
- raise 主动抛异常；断言 assert（了解）
- 自检：读入一个数字，输入非法时给出友好提示而不是崩溃

## 周四 · 标准库

- random：random() / randint(a, b) / choice(列表) / shuffle
- time：time() / sleep() 计时
- datetime：date / time / datetime 基础用法、strftime
- math：pi / sqrt / ceil / floor
- 自检：随机生成 6 位验证码

## 周五 · 第三方库与生态

- jieba：jieba.lcut(文本) 中文分词（综合题高频！）
- wordcloud：词云（综合题组合用，掌握接口即可）
- PyInstaller：把程序打包成 exe（了解流程）
- 安装与导入：pip install + import
- 自检：用 jieba 对一句话分词并统计词频

## 周末 · 公共基础 + 综合应用

- 公共基础：查找（顺序/二分）、排序（冒泡/选择）、软件工程概念
- 动手：做 1 道「综合应用题」真题（通常是 文本 + 词典 + jieba 词频统计 这类）"""},
    {"title": "第 4 周 · 真题刷题", "md": """# 第 4 周 · 真题刷题

本周目标：重心转向操作题，每天一套，动手能力碾压式提升。

## 每天固定流程（约 1 小时）

1. 先做 3 道「基本操作题」（15 分钟）：补全/改错/填空，练手速
2. 再做 2 道「简单应用题」（25 分钟）：按需求写函数/程序
3. 对答案，把不会的考点记下来
4. 用「小书虫」深度教学补讲这些考点（选 Python程序设计 对应知识点）

## 周一~周五 · 连做 5 套操作题

- 全部亲手敲进 Python，别只在纸上写
- 报错了先看 Traceback 最后一行，自己改 5 分钟再问

## 周六 · 综合应用题专项

- 一次做 2 道综合大题：先通读需求 → 拆成小函数 → 逐步实现 → 整体运行
- 高频综合题套路：读取文本 → jieba 分词 → 词频统计 → 排序输出 / 生成词云

## 周日 · 公共基础突击 + 错题本

- 公共基础系统过：数据结构（表/栈/队列/树/图）、数据库基础、操作系统常识
- 把本周所有错题整理进错题本，标注考点"""},
    {"title": "第 5 周 · 全真模拟与冲刺", "md": """# 第 5 周 · 全真模拟与冲刺

本周目标：3 次全真模拟适应节奏，考前只做两件事：模拟 + 错题。

## 模拟安排（周二、四、六）

- 按真实考试限时 120 分钟，完整一套真题（选择 40 + 操作 60）
- 环境：在考场同款 Python 里做，手机静音、不翻书
- 考完立即对分：选择题对错，操作题以自己跑通为准

## 模拟后的复盘（重点）

- 选择：把公共基础错题背下来（考前突击最划算）
- 操作：把每道题重新独立写一遍，直到不看答案也能跑通
- 高频考点冲刺：字符串/列表/字典操作、文件读写、jieba 词频统计、random

## 考前 2 天

- 不再做新题，只看错题本 + 高频语法速查
- 把每个模块的「固定套路」过一遍：建字典计数、排序输出、文件逐行处理

## 考前 1 天

- 睡够觉，不熬夜刷题
- 准备好心态：60 分合格，你练了一个月，稳的

## 考场 10 条提醒

1. 先看操作题全部题目再动手，心里有数
2. 选择 30 分钟内必须做完
3. 操作题先易后难：基本操作 → 简单应用 → 综合
4. 每写一题就运行一次，确认能跑
5. 千万别漏保存！交卷前检查每题都保存了
6. 报错别慌，看最后一行
7. 综合题写不出来也要把会的小函数写上（有步骤分）
8. 时间剩 20 分钟时立刻去检查保存
9. 交卷前再点一次「保存全部」
10. 你已经准备好了，冲！"""},
    {"title": "📝 题库 · 选择题（40 分）", "md": """# 题库 · 选择题（40 分）

考试中选择题共 40 分（公共基础约 10 分 + Python 知识约 30 分）。
这里收录了覆盖二级 Python 全部考点的选择题，配合「练习」功能刷题。

## 使用方法

1. 打开本章 → 点章节上的「练习」按钮进入刷题
2. 逐题选择答案，提交后自动判断对错并给出解析
3. 做错的题点「加入错题本」，考前集中复习

## 考点分布

- 公共基础：数据结构（栈/队列/复杂度）、算法、软件工程
- Python 语法：程序格式、数据类型、运算符、流程控制、列表/字符串/元组/字典、
  函数、文件、异常、标准库与生态库（random / jieba）

小提示：选择题先保证把 Python 知识那 30 分拿到手，公共基础 10 分考前突击背记。"""},
    {"title": "📝 题库 · 操作题（60 分）", "md": """# 题库 · 操作题（60 分）

考试中操作题共 60 分：基本操作题 15 分 + 简单应用题 25 分 + 综合应用题 20 分。
这里收录 10 道典型操作题，覆盖各类题型。

## 使用方法

1. 打开本章 → 点章节上的「练习」按钮进入刷题
2. 在答题框里写下你的代码/思路，提交后看参考答案与解析
3. 动手敲一遍再对答案，做错的题「加入错题本」

## 高分提醒

- 基本操作题：补全/修改小段程序，练手速，几乎都是套路
- 简单应用题：按需求写函数/程序，重点是列表、字典、字符串操作
- 综合应用题：读文本 → jieba 分词 → 词频统计 → 排序输出/词云，高频套路
- 考场每写一题就运行一次，确认能跑再保存"""},
    {"title": "📝 真题 · 操作题（真实真题）", "md": """# 📝 真题 · 操作题（真实真题）

这里是从《计算机二级》练习软件提取的 **Python 二级真实真题操作题**：
PY1xx 基本操作 / PY2xx 简单应用 / PY3xx 综合应用。

## 使用方法

1. 打开本章 → 点章节上的「练习」按钮刷题
2. 读懂题目要求与示例输入/输出，在答题框里写代码
3. 提交后由 **AI 阅卷点评**（官方答案在原软件中加密，未随题面提供）

## 提示

- 每题尽量自己动手写，写不出的考点去「深度教学」补
- 真题操作题高频套路：字符串/列表处理、字典统计、turtle 绘图、jieba 分词、文件读取
- 做完对照 AI 点评自查，把没掌握的考点记进错题本"""},
    {"title": "📝 题库 · 公共基础选择题（10 分）", "md": """# 📝 题库 · 公共基础选择题（10 分）

选择题 40 分里，**公共基础知识占约 10 分**（数据结构/算法/软件工程/数据库/计算机基础），
这部分内容 Python、C、Office 各科目通用。

## 使用方法

1. 打开本章 → 点章节上的「练习」按钮刷题
2. 逐题选择答案，提交后自动判断并给出解析
3. 做错的题「加入错题本」，考前突击背记性价比最高

## 考点分布

- 算法：时间复杂度、算法特征
- 数据结构：栈/队列/线性表/二叉树/循环队列
- 查找与排序：顺序/二分查找、各排序最坏复杂度
- 计算机基础：指令周期、内存、运算器、补码、总线带宽
- 软件工程：DFD、结构化设计、生命周期
- 数据库：DBMS、关系模型、三级模式"""},
]

# 题库：章节标题 → 题目列表。选择题 answer 必须等于某个选项的原文（判分按精确匹配）；
# 填空/简答 answer 含关键术语（判分按关键词覆盖率）。
QUESTION_BANK: dict[str, list[dict]] = {
    "📝 题库 · 选择题（40 分）": [
        # ── 公共基础（4 题）──
        {"qtype": "choice",
         "question": "下列叙述中正确的是（）",
         "options": ["算法的时间复杂度是指算法执行过程中所需要的基本运算次数",
                     "算法的时间复杂度是指执行算法程序所需要的时间",
                     "算法的时间复杂度是指算法执行过程中所需存储空间的多少",
                     "算法的时间复杂度是指算法程序的长短"],
         "answer": "算法的时间复杂度是指算法执行过程中所需要的基本运算次数",
         "explanation": "时间复杂度衡量算法执行所需的基本运算（操作）次数，与问题规模 n 相关；涉及存储空间的是空间复杂度，不是时间。",
         "source_text": ""},
        {"qtype": "choice",
         "question": "下列关于栈的叙述，正确的是（）",
         "options": ["栈按“先进后出”原则组织数据",
                     "栈按“先进先出”原则组织数据",
                     "栈顶元素是最先被插入的元素",
                     "栈只能在底部插入和删除元素"],
         "answer": "栈按“先进后出”原则组织数据",
         "explanation": "栈（stack）是后进先出（LIFO），只能在栈顶插入/删除；先进先出（FIFO）的是队列。",
         "source_text": ""},
        {"qtype": "choice",
         "question": "队列（queue）中数据元素的进出原则是（）",
         "options": ["先进先出", "先进后出", "后进先出", "随机存取"],
         "answer": "先进先出",
         "explanation": "队列是先进先出（FIFO），一端入队、一端出队，类似排队买饭；后进先出的是栈。",
         "source_text": ""},
        {"qtype": "choice",
         "question": "下列软件中，属于应用软件的是（）",
         "options": ["学生成绩管理系统", "操作系统", "编译程序", "数据库管理系统"],
         "answer": "学生成绩管理系统",
         "explanation": "操作系统、编译程序、数据库管理系统都属于系统软件；面向具体应用开发的如学生成绩管理系统才是应用软件。",
         "source_text": ""},
        # ── 程序格式与数据类型（8 题）──
        {"qtype": "choice",
         "question": "下列关于 Python 缩进的叙述，正确的是（）",
         "options": ["缩进表示语句块的层次关系，是 Python 语法的一部分",
                     "缩进只能用空格，不能用 Tab",
                     "缩进只影响代码美观，不影响程序执行",
                     "同一个代码块内可以随意混用 Tab 和空格"],
         "answer": "缩进表示语句块的层次关系，是 Python 语法的一部分",
         "explanation": "Python 用缩进定义代码块，同一代码块必须保持一致缩进（推荐 4 空格）；Tab 与空格混用会报 IndentationError。",
         "source_text": ""},
        {"qtype": "choice",
         "question": "下列变量名中，合法的是（）",
         "options": ["_abc", "2abc", "a-b", "a b"],
         "answer": "_abc",
         "explanation": "标识符由字母、数字、下划线组成且不能以数字开头，不能含连字符和空格。a-b、a b 非法，2abc 以数字开头非法。",
         "source_text": ""},
        {"qtype": "choice",
         "question": "下列属于 Python 保留字（关键字）的是（）",
         "options": ["def", "function", "var", "each"],
         "answer": "def",
         "explanation": "def 用于定义函数，是 Python 保留字；function、var、each 不是 Python 的关键字。",
         "source_text": ""},
        {"qtype": "choice",
         "question": "执行 int(\"12.3\") 的结果是（）",
         "options": ["抛出 ValueError 异常", "返回 12.3", "返回 12", "返回 0"],
         "answer": "抛出 ValueError 异常",
         "explanation": "int() 只能把纯整数字符串转成整数，“12.3”含小数点，转换会抛 ValueError；float(\"12.3\") 才合法。",
         "source_text": ""},
        {"qtype": "choice",
         "question": "表达式 7 // 2 的结果是（）",
         "options": ["3", "3.5", "4", "1"],
         "answer": "3",
         "explanation": "// 是整除运算符，向下取整：7 // 2 = 3；7 / 2 = 3.5；7 % 2 = 1。",
         "source_text": ""},
        {"qtype": "choice",
         "question": "表达式 2 ** 3 的结果是（）",
         "options": ["8", "6", "9", "23"],
         "answer": "8",
         "explanation": "** 是幂运算符，2 ** 3 = 2×2×2 = 8。",
         "source_text": ""},
        {"qtype": "choice",
         "question": "表达式 7 % 2 的结果是（）",
         "options": ["1", "3", "0.5", "3.5"],
         "answer": "1",
         "explanation": "% 是取余运算符，7 % 2 = 1；整除 7 // 2 = 3。",
         "source_text": ""},
        {"qtype": "choice",
         "question": "input() 函数返回值的类型是（）",
         "options": ["str", "int", "float", "list"],
         "answer": "str",
         "explanation": "input() 始终返回字符串，需要参与数学运算时要先转换，如 int(input())。",
         "source_text": ""},
        # ── 流程控制（4 题）──
        {"qtype": "choice",
         "question": "已知 x = 3.14159，下列语句能输出 3.14 的是（）",
         "options": ["print(f\"{x:.2f}\")", "print(f\"{x:2f}\")", "print(f\"{x:.2}\")", "print(f\"{x:d}\")"],
         "answer": "print(f\"{x:.2f}\")",
         "explanation": "{:.2f} 表示保留 2 位小数；{:.2} 是字符串截断并非小数；{d} 是整数格式，会报错。",
         "source_text": ""},
        {"qtype": "choice",
         "question": "下列表达式的值为 True 的是（）",
         "options": ["not (3 > 4)", "3 > 4", "3 == 4", "3 != 3"],
         "answer": "not (3 > 4)",
         "explanation": "3 > 4 为 False，not False = True；其余三项均为 False。",
         "source_text": ""},
        {"qtype": "choice",
         "question": "下列逻辑表达式的值为 True 的是（）",
         "options": ["True or False", "False and True", "not True", "False or False"],
         "answer": "True or False",
         "explanation": "and 一假即假，or 一真即真：True or False = True；其余三项均为 False。",
         "source_text": ""},
        {"qtype": "choice",
         "question": "list(range(1, 10, 2)) 的结果是（）",
         "options": ["[1, 3, 5, 7, 9]", "[1, 3, 5, 7]", "[1, 2, 3, 4, 5]", "[2, 4, 6, 8]"],
         "answer": "[1, 3, 5, 7, 9]",
         "explanation": "range(1, 10, 2) 从 1 开始、步长 2、不包含 10，得到 1, 3, 5, 7, 9。",
         "source_text": ""},
        # ── 列表与字符串（5 题）──
        {"qtype": "choice",
         "question": "已知 L = [1, 2, 3, 4, 5]，则 L[1:3] 的结果是（）",
         "options": ["[2, 3]", "[2, 3, 4]", "[1, 2]", "[1, 3]"],
         "answer": "[2, 3]",
         "explanation": "切片 L[a:b] 含头不含尾，L[1:3] 取下标 1、2 两个元素，即 [2, 3]。",
         "source_text": ""},
        {"qtype": "choice",
         "question": "已知 L = [1, 2, 3]，执行 L.append(4) 后 L 的值是（）",
         "options": ["[1, 2, 3, 4]", "[4, 1, 2, 3]", "[[1, 2, 3], 4]", "[1, 2, 3, 4, 4]"],
         "answer": "[1, 2, 3, 4]",
         "explanation": "append() 在列表末尾追加一个元素；insert 可指定位置插入；extend 追加序列中的多个元素。",
         "source_text": ""},
        {"qtype": "choice",
         "question": "下列列表推导式的结果是 [1, 4, 9] 的是（）",
         "options": ["[x * x for x in range(1, 4)]", "[x * x for x in range(1, 5)]", "[x * x for x in range(0, 3)]", "[x * 2 for x in range(1, 4)]"],
         "answer": "[x * x for x in range(1, 4)]",
         "explanation": "range(1, 4) 得 1, 2, 3，平方后为 1, 4, 9；其余分别得 1,4,9,16 或 0,1,4 或 2,4,6。",
         "source_text": ""},
        {"qtype": "choice",
         "question": "下列关于字符串的叙述，正确的是（）",
         "options": ["字符串是不可变类型，一旦创建不能原地修改", "字符串是可变类型，可以直接修改", "字符串只能由英文字母组成", "字符串不能使用切片操作"],
         "answer": "字符串是不可变类型，一旦创建不能原地修改",
         "explanation": "str 不可变，任何“修改”都会生成新字符串；字符串支持切片、可包含任意字符。",
         "source_text": ""},
        {"qtype": "choice",
         "question": "已知 s = \"a,b,c\"，则 s.split(\",\") 的结果是（）",
         "options": ["['a', 'b', 'c']", "['a,b,c']", "('a', 'b', 'c')", "['a', 'b']"],
         "answer": "['a', 'b', 'c']",
         "explanation": "split() 按分隔符把字符串拆成列表；join() 则把列表拼成字符串。",
         "source_text": ""},
        # ── 元组/集合/字典（4 题）──
        {"qtype": "choice",
         "question": "下列叙述正确的是（）",
         "options": ["元组 tuple 是不可变类型，列表 list 是可变类型", "元组和列表都可以随意修改", "元组只能存储数字", "列表中的元素类型必须相同"],
         "answer": "元组 tuple 是不可变类型，列表 list 是可变类型",
         "explanation": "元组创建后不可修改，列表可变；两者元素都可以是任意类型且类型不必相同。",
         "source_text": ""},
        {"qtype": "choice",
         "question": "下列代码能对列表 L 去重的是（）",
         "options": ["set(L)", "list(L)", "sorted(L)", "L.unique()"],
         "answer": "set(L)",
         "explanation": "set() 把序列转成集合，集合元素不重复，天然去重；list/sorted 不去重，L.unique() 不存在。",
         "source_text": ""},
        {"qtype": "choice",
         "question": "已知 d = {\"a\": 1, \"b\": 2}，则 d.get(\"c\", 0) 的结果是（）",
         "options": ["0", "抛出 KeyError 异常", "None", "1"],
         "answer": "0",
         "explanation": "get(key, 默认值) 在键不存在时返回默认值 0，不报错；直接写 d[\"c\"] 才会抛 KeyError。",
         "source_text": ""},
        {"qtype": "choice",
         "question": "已知 d = {\"a\": 1, \"b\": 2}，下列能遍历所有键值对的是（）",
         "options": ["for k, v in d.items()", "for k, v in d", "for v in d", "for k in d 得到的是值"],
         "answer": "for k, v in d.items()",
         "explanation": "items() 返回(键, 值)的视图，可解包遍历；直接 for x in d 遍历的是键，d.values() 才是值。",
         "source_text": ""},
        # ── 函数（3 题）──
        {"qtype": "choice",
         "question": "下列关于函数默认参数的叙述，正确的是（）",
         "options": ["def f(a, b=1): 合法，默认参数只能放在最后", "def f(a=1, b): 合法，默认参数可放前面", "默认参数在调用时不能省略", "Python 函数不支持默认参数"],
         "answer": "def f(a, b=1): 合法，默认参数只能放在最后",
         "explanation": "默认参数必须放在非默认参数之后，否则语法报错（SyntaxError）。",
         "source_text": ""},
        {"qtype": "choice",
         "question": "下列定义匿名函数正确的是（）",
         "options": ["f = lambda x: x * 2", "f = lambda x: x * 2 需要配合 def 使用", "f = lambda(x) { return x * 2 }", "lambda 和 def 定义的是两种互不相通的函数"],
         "answer": "f = lambda x: x * 2",
         "explanation": "lambda 定义匿名函数：冒号前是参数、冒号后是表达式，如 lambda x: x * 2，可直接赋值给变量。",
         "source_text": ""},
        {"qtype": "choice",
         "question": "递归函数必须具备的条件是（）",
         "options": ["有明确的递归出口（边界条件）", "参数必须是整数", "必须返回一个列表", "函数名必须以 r 开头"],
         "answer": "有明确的递归出口（边界条件）",
         "explanation": "递归由“递推 + 回归”构成，必须有终止条件（递归出口），否则无限递归导致栈溢出。",
         "source_text": ""},
        # ── 文件/异常/生态（6 题）──
        {"qtype": "choice",
         "question": "下列关于 with 语句的叙述，正确的是（）",
         "options": ["with open(f) as f: 语句块结束后文件会被自动关闭", "with 只能用于文件操作", "使用 with 打开的文件仍需手动 close", "with 打开的文件只能读不能写"],
         "answer": "with open(f) as f: 语句块结束后文件会被自动关闭",
         "explanation": "with 是上下文管理器，退出代码块时自动调用 close()，避免忘记关闭文件。",
         "source_text": ""},
        {"qtype": "choice",
         "question": "下列关于 json 模块的叙述，正确的是（）",
         "options": ["json.loads() 把 JSON 字符串解析成 Python 对象", "json.loads() 把 Python 对象转成 JSON 字符串", "json 模块无需 import 可直接使用", "json.dumps() 只能处理数字"],
         "answer": "json.loads() 把 JSON 字符串解析成 Python 对象",
         "explanation": "loads = load string，把 JSON 字符串解析成 Python 对象；dumps = dump string，把对象转成 JSON 字符串。",
         "source_text": ""},
        {"qtype": "choice",
         "question": "下列 Python 异常处理结构正确的是（）",
         "options": ["try / except / finally", "try / catch / finally", "if / else / except", "while / except"],
         "answer": "try / except / finally",
         "explanation": "Python 用 try/except（可加 else、finally）；catch 是 Java/C++ 等语言的关键字。",
         "source_text": ""},
        {"qtype": "choice",
         "question": "下列能生成 1 到 6 闭区间的随机整数的是（）",
         "options": ["random.randint(1, 6)", "random.random(1, 6)", "random.choice(1, 6)", "random.shuffle(1, 6)"],
         "answer": "random.randint(1, 6)",
         "explanation": "randint(a, b) 返回 [a, b] 闭区间的随机整数；random() 返回 [0,1) 浮点；choice 从序列取一个；shuffle 打乱列表。",
         "source_text": ""},
        {"qtype": "choice",
         "question": "下列关于 jieba 库的叙述，正确的是（）",
         "options": ["jieba.lcut(文本) 对中文文本分词并返回词列表", "jieba.lcut() 返回一个字符串", "jieba 只能处理英文文本", "jieba 是 Python 内置标准库，无需安装"],
         "answer": "jieba.lcut(文本) 对中文文本分词并返回词列表",
         "explanation": "jieba 是第三方中文分词库，需 pip install jieba；lcut 返回列表，是综合题词频统计的高频工具。",
         "source_text": ""},
        {"qtype": "choice",
         "question": "下列关于循环结构的叙述，正确的是（）",
         "options": ["break 终止整个循环，continue 跳过本次循环的剩余语句", "break 和 continue 的作用完全相同", "break 只跳过本次迭代", "continue 会终止整个循环"],
         "answer": "break 终止整个循环，continue 跳过本次循环的剩余语句",
         "explanation": "break 立即退出整个循环；continue 跳过本次循环体剩余语句，直接进入下一次迭代。",
         "source_text": ""},
        # ── 扩充到 40 题（公共基础 +2、Python +4，凑齐 40 分）──
        {"qtype": "choice",
         "question": "在长度为 n 的线性表中进行顺序查找，最坏情况下需要比较的次数是（）",
         "options": ["n", "n / 2", "log n", "n²"],
         "answer": "n",
         "explanation": "顺序查找最坏情况是目标元素在末尾或不存在，需要比较 n 次；平均约 n/2 次。",
         "source_text": ""},
        {"qtype": "choice",
         "question": "下列属于软件生命周期中「定义阶段」的活动的是（）",
         "options": ["需求分析", "代码编写", "软件测试", "软件维护"],
         "answer": "需求分析",
         "explanation": "软件生命周期分定义（问题定义、可行性研究、需求分析）、开发（设计、编码、测试）、维护三阶段；需求分析属定义阶段。",
         "source_text": ""},
        {"qtype": "choice",
         "question": "已知 L = [1, 2, 3, 4, 5]，则 L[::-1] 的结果是（）",
         "options": ["[5, 4, 3, 2, 1]", "[1, 5]", "原列表被原地反转", "[]"],
         "answer": "[5, 4, 3, 2, 1]",
         "explanation": "步长为 -1 表示从后往前取，L[::-1] 得到逆序的新列表，原列表不变；list.reverse() 才是原地反转。",
         "source_text": ""},
        {"qtype": "choice",
         "question": "已知 s = \"Python\"，则 s[1:4] 的结果是（）",
         "options": ["\"yth\"", "\"Pyt\"", "\"ytho\"", "\"Python\""],
         "answer": "\"yth\"",
         "explanation": "切片含头不含尾，s[1:4] 取下标 1、2、3 的字符，即 yth。",
         "source_text": ""},
        {"qtype": "choice",
         "question": "下列代码的输出正确的是（）",
         "options": ["print(1 + 2 == 3) 输出 True", "print(1 + 2 == 3) 输出 False", "print(\"1\" + 2) 输出 3", "print(1 + \"2\") 输出 12"],
         "answer": "print(1 + 2 == 3) 输出 True",
         "explanation": "1 + 2 = 3，3 == 3 为 True；字符串与整数不能直接相加，会抛 TypeError。",
         "source_text": ""},
        {"qtype": "choice",
         "question": "下列关于 global 的叙述，正确的是（）",
         "options": ["在函数内用 global 声明后，可修改全局变量", "global 用于定义全局常量", "函数内默认可以直接修改全局变量", "global 只能在类中使用"],
         "answer": "在函数内用 global 声明后，可修改全局变量",
         "explanation": "函数内默认访问的是全局变量的值，若要赋值修改必须先用 global 声明；否则赋值会创建局部变量。",
         "source_text": ""},
    ],
    "📝 题库 · 操作题（60 分）": [
        {"qtype": "essay",
         "question": "编写函数 is_prime(n)：判断 n 是否为素数，是则返回 True，否则返回 False。",
         "answer": "用 for 循环让 i 从 2 到 n 的平方根范围遍历，若 n 能被其中任意整数整除则不是素数返回 False；循环结束后没有能整除的数则返回 True。注意 1 不是素数，2 是素数。",
         "explanation": "参考实现：\ndef is_prime(n):\n    if n < 2:\n        return False\n    for i in range(2, int(n ** 0.5) + 1):\n        if n % i == 0:\n            return False\n    return True\n判断到平方根即可，减少循环次数。",
         "source_text": ""},
        {"qtype": "essay",
         "question": "统计字符串 s 中每个字符出现的次数，用字典存储并输出。",
         "answer": "遍历字符串中的每个字符，若字符已在字典中则计数加 1，否则初始化为 1；用 d.get(c, 0) + 1 的写法更简洁，避免判断键是否存在。",
         "explanation": "参考实现：\nd = {}\nfor c in s:\n    d[c] = d.get(c, 0) + 1\nprint(d)\n这是字典计数的高频套路，综合题常考。",
         "source_text": ""},
        {"qtype": "essay",
         "question": "读取文本文件 a.txt，统计文件一共有多少行，以及总共多少个单词（每行按空白分割）。",
         "answer": "用 with open 打开文件，for line in f 逐行遍历，行数累加一；每行用 len(line.split()) 得到该行单词数并累加，最后输出行数与单词数。",
         "explanation": "参考实现：\nlines = words = 0\nwith open(\"a.txt\", encoding=\"utf-8\") as f:\n    for line in f:\n        lines += 1\n        words += len(line.split())\nprint(lines, words)\n注意 with 会自动关闭文件，split() 默认按空白分割。",
         "source_text": ""},
        {"qtype": "essay",
         "question": "编写函数 dedup(L)：接收一个列表，返回去掉重复元素的新列表（保持原顺序）。",
         "answer": "新建一个空列表，遍历原列表，若当前元素不在新列表中则加入，最后返回新列表；注意不能用集合直接转，因为会丢失顺序。",
         "explanation": "参考实现：\ndef dedup(L):\n    r = []\n    for x in L:\n        if x not in r:\n            r.append(x)\n    return r\n若不在乎顺序，用 set(L) 一行即可。",
         "source_text": ""},
        {"qtype": "essay",
         "question": "生成一个 6 位随机验证码，由数字和大小写字母组成。",
         "answer": "用 random 模块，先准备数字和字母组成的字符串，用 random.choice 随机取 6 个字符拼接，或用 random.sample 一次取出 6 个不重复字符。",
         "explanation": "参考实现：\nimport random\nimport string\nchars = string.ascii_letters + string.digits\ncode = \"\".join(random.choice(chars) for _ in range(6))\nprint(code)\nstring.ascii_letters 含大小写字母，digits 含数字。",
         "source_text": ""},
        {"qtype": "essay",
         "question": "给定一篇中文文本 text，用 jieba 分词，统计出现次数最多的前 10 个词并输出。",
         "answer": "用 jieba.lcut 对全文分词得到词列表，遍历统计到字典中计数，再用 sorted 按值从大到小排序，取前 10 个输出；分词后可过滤掉长度为 1 的标点等。",
         "explanation": "参考实现：\nimport jieba\nwords = jieba.lcut(text)\nd = {}\nfor w in words:\n    if len(w) > 1:\n        d[w] = d.get(w, 0) + 1\ntop = sorted(d.items(), key=lambda x: x[1], reverse=True)[:10]\nprint(top)\n这是综合应用题最经典的套路。",
         "source_text": ""},
        {"qtype": "essay",
         "question": "把学生成绩的二维列表 data 写入 CSV 文件，再从文件读回并计算平均分。",
         "answer": "用 csv.writer 的 writerows 把二维列表写入文件；再用 csv.reader 逐行读取，跳过表头行，把成绩累加求平均。",
         "explanation": "参考实现：\nimport csv\nwith open(\"scores.csv\", \"w\", newline=\"\", encoding=\"utf-8\") as f:\n    writer = csv.writer(f)\n    writer.writerows(data)\nwith open(\"scores.csv\", encoding=\"utf-8\") as f:\n    rows = list(csv.reader(f))\nscores = [int(r[1]) for r in rows[1:]]\nprint(sum(scores) / len(scores))\n写 CSV 记得加 newline=\"\"。",
         "source_text": ""},
        {"qtype": "essay",
         "question": "读入一行若干整数，输出其中最大值与最小值的差。",
         "answer": "用 max 和 min 分别求出列表的最大值与最小值，两者相减得到极差并输出。",
         "explanation": "参考实现：\nnums = [int(x) for x in input().split()]\nprint(max(nums) - min(nums))\ninput().split() 按空白拆分输入，列表推导式转成整数。",
         "source_text": ""},
        {"qtype": "essay",
         "question": "读入正整数 n，计算 1 到 n 的累加和并输出。",
         "answer": "用 for 循环从 1 到 n 累加到一个变量，或用 sum(range(1, n + 1)) 一行求和，最后输出结果。",
         "explanation": "参考实现：\nn = int(input())\ntotal = sum(range(1, n + 1))\nprint(total)\nrange(1, n+1) 含头不含尾，正好覆盖 1 到 n。",
         "source_text": ""},
        {"qtype": "essay",
         "question": "把字符串 s 中的所有数字字符提取出来，拼接成一个整数并输出（如 \"a1b2c3\" → 123）。",
         "answer": "遍历字符串的每个字符，用 isdigit 判断是否为数字字符，是则拼接到结果字符串，最后用 int 把拼接结果转成整数输出。",
         "explanation": "参考实现：\ns = \"a1b2c3\"\ndigits = \"\".join(c for c in s if c.isdigit())\nprint(int(digits))  # 123\nisdigit() 判断数字字符，join 把字符列表拼成字符串。",
         "source_text": ""},
    ],
}

# 真实真题：从《计算机二级》练习软件提取的 Python 操作题（见 ncre_real_questions.py）
QUESTION_BANK["📝 真题 · 操作题（真实真题）"] = REAL_QUESTIONS
# 公共基础选择题（各科目通用，选择 40 分里那 10 分）
QUESTION_BANK["📝 题库 · 公共基础选择题（10 分）"] = PUBLIC_BASE_QUESTIONS

# 操作题子型（模拟考试按题型给分）：按题目文本前缀识别，与 QUESTION_BANK 中操作题一致。
# basic=基本操作题 / applied=简单应用题 / comprehensive=综合应用题
ESSAY_SUBTYPE_MAP: dict[str, str] = {
    "编写函数 is_prime": "basic",
    "统计字符串 s 中每个字符出现": "basic",
    "读取文本文件 a.txt": "applied",
    "编写函数 dedup": "basic",
    "生成一个 6 位随机验证码": "applied",
    "给定一篇中文文本 text，用 jieba": "comprehensive",
    "把学生成绩的二维列表": "applied",
    "读入一行若干整数": "basic",
    "读入正整数 n，计算 1 到 n 的累加和": "basic",
    "把字符串 s 中的所有数字字符": "applied",
}


def essay_subtype(question_text: str) -> str:
    """按题目文本前缀识别操作题子型；匹配不到返回空串。"""
    for prefix, sub in ESSAY_SUBTYPE_MAP.items():
        if question_text.startswith(prefix):
            return sub
    return ""


_FILENAME_BAD_CHARS = re.compile(r'[\\/:*?"<>|\r\n]')


def _safe_filename(title: str) -> str:
    return _FILENAME_BAD_CHARS.sub("_", title).strip()[:60] or "chapter"


async def ensure_ncre_course() -> None:
    """幂等种入「计算机二级 · Python」课程书：Project + 章节 Document + Chunk + 题库 Question。

    按章节级幂等：课程不存在则整本创建；已存在则只补齐缺失章节
    （这样后续给课程新增章节/题库，重跑启动即可增量更新）。
    """
    from app.database import async_session

    async with async_session() as db:
        course = (await db.execute(
            select(Project).where(Project.title == COURSE_TITLE)
        )).scalars().first()

        if course is None:
            course = Project(
                user_id="local_user",
                title=COURSE_TITLE,
                description=COURSE_DESC,
                icon=COURSE_ICON,
                is_public=True,
                category="工学",
                category_sub="计算机科学与技术",
                subject="Python程序设计",
            )
            db.add(course)
            await db.flush()
            logger.info("创建课程「%s」", COURSE_TITLE)

        existing_titles = set((await db.execute(
            select(Document.title).where(Document.project_id == course.id)
        )).scalars().all())

        added = 0
        for idx, ch in enumerate(CHAPTERS):
            if ch["title"] in existing_titles:
                continue
            await _add_chapter(db, course, ch, idx)
            added += 1

        # 题目级幂等同步：补齐新增题目 + 为操作题回填 subtype
        await _sync_questions(db, course)

        await db.commit()
        if added:
            logger.info("课程「%s」新增 %d 章（共 %d 章）", COURSE_TITLE, added, len(CHAPTERS))
        else:
            logger.info("课程「%s」已完整（%d 章），跳过", COURSE_TITLE, len(CHAPTERS))


async def _add_chapter(db: AsyncSession, course: Project, ch: dict, idx: int) -> None:
    """创建一章：写 md 文件 → Document + Chunk；若该章是题库章节，再种入 Question。"""
    save_dir = Path(settings.document_dir)
    save_dir.mkdir(parents=True, exist_ok=True)

    doc_id = str(uuid.uuid4())
    filename = f"{doc_id}_{_safe_filename(ch['title'])}.md"
    file_path = save_dir / filename
    file_path.write_text(ch["md"], encoding="utf-8")

    doc = Document(
        id=doc_id,
        user_id="local_user",
        title=ch["title"],
        filename=filename,
        file_path=str(file_path),
        content_type="md",
        project_id=course.id,
        chapter_title=ch["title"],
        sort_order=idx,
    )
    db.add(doc)
    await db.flush()

    # 解析 + 分块：保证阅读页可用（阅读/朗读/总结/挖空都基于 Chunk）
    text, hints = parse_file(file_path)
    for seq, c in enumerate(chunk_text(text, hints)):
        db.add(Chunk(
            document_id=doc.id,
            seq=seq,
            content=c["content"],
            heading=c["heading"] or ch["title"],
        ))


async def _sync_questions(db: AsyncSession, course: Project) -> None:
    """题目级幂等同步：按题目文本查重，补齐章节缺失的题，并为操作题回填 subtype。

    题库数据更新后重跑启动即可增量补题（不重建已存在的章节）。
    """
    docs = (await db.execute(
        select(Document).where(Document.project_id == course.id)
    )).scalars().all()
    doc_by_title = {d.title: d for d in docs}

    added = filled = 0
    for title, questions in QUESTION_BANK.items():
        doc = doc_by_title.get(title)
        if doc is None:
            continue
        existing = (await db.execute(
            select(Question).where(Question.document_id == doc.id)
        )).scalars().all()
        by_text = {q.question: q for q in existing}
        for q in questions:
            row = by_text.get(q["question"])
            # subtype 优先用题目自带（真实真题已带），否则按题面前缀识别
            sub = q.get("subtype") or (essay_subtype(q["question"]) if q["qtype"] != "choice" else "")
            if row is None:
                db.add(Question(
                    document_id=doc.id,
                    qtype=q["qtype"],
                    question=q["question"],
                    options=json.dumps(q.get("options") or [], ensure_ascii=False),
                    answer=q["answer"],
                    explanation=q.get("explanation", ""),
                    source_text=q.get("source_text", ""),
                    subtype=sub,
                ))
                added += 1
            elif q["qtype"] != "choice" and not row.subtype and sub:
                row.subtype = sub
                filled += 1
    if added or filled:
        logger.info("题库同步：新增 %d 题，回填 subtype %d 题", added, filled)
