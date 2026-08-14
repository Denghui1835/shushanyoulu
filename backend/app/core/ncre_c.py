"""计算机二级 · C 语言程序设计 备考课程种子数据.

镜像 ncre_python.py 的机制：把「5 周冲刺备考路线」作为一本书种进书架，
并附带 C 二级题库（40 选择 + 操作题：程序填空/改错/设计）。
C 二级题型与 Python 不同：选择 40 + 操作 60（填空 3×6 + 改错 2×9 + 设计 1×24）。
"""
import json
import logging
import re
import uuid
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.parsing import parse_file, chunk_text
from app.models import Project, Document, Chunk, Question

logger = logging.getLogger("yuanqi.ncre")

COURSE_TITLE = "计算机二级 · C 语言程序设计"
COURSE_ICON = "💻"
COURSE_DESC = (
    "全国计算机等级考试二级 C 语言程序设计，5 周冲刺备考路线。"
    "每天 1~1.5 小时：选择题 40 分靠刷题，操作题（填空/改错/设计）靠动手练套路，60 分合格！"
)

CHAPTERS: list[dict] = [
    {"title": "备考总纲与考试结构", "md": """# 备考总纲与考试结构

全国计算机等级考试（NCRE）二级 · C 语言程序设计。目标：60 分合格，机考一次过。

## 考试结构（机考 120 分钟，满分 100）

| 题型 | 分值 | 说明 |
| --- | --- | --- |
| 单项选择题 | 40 分 | 公共基础知识约 10 分 + C 语言知识约 30 分 |
| 程序填空题 | 18 分 | 3 小题 × 6 分，补全程序中的空 |
| 程序改错题 | 18 分 | 2 小题 × 9 分，找出并改正程序错误 |
| 程序设计题 | 24 分 | 1 大题，按要求编写函数/程序 |

合格线：60 分。选择题稳定 30+，填空/改错各拿一半，设计题能写出主体就有戏。

## 考试环境

- 考场使用 C 语言集成开发环境（以考试系统为准，一般类似 Dev-C++ / VC6）。
- 熟练掌握：新建源文件（.c）、编译（Compile）、运行（Run）、看编译错误信息。
- 程序要能编译通过才有分，语法错误一定要会看（error 行号、缺少分号、括号不匹配）。

## 通过策略

1. 选择 40 分：靠刷真题；公共基础 10 分考前突击背记。
2. 填空 18 分：考数组、循环、字符串，补上表达式即可，最易拿分。
3. 改错 18 分：考 3 类高频错——漏分号、scanf 忘 &、求和忘初始化、字符串用 == 比较。
4. 设计 24 分：函数题模板化（遍历数组、统计、求和、平均），背熟套路。
5. 时间分配：选择 30 分钟，操作题 75 分钟，留 15 分钟检查保存。

## 5 周总览

- 第 1 周 · C 语法地基：类型、运算符、输入输出、选择、循环
- 第 2 周 · 数组与函数：一维/二维/字符数组、函数与作用域
- 第 3 周 · 指针、结构体与文件：指针、struct、文件、预处理
- 第 4 周 · 真题刷题：每天一套操作题（填空+改错+设计）
- 第 5 周 · 全真模拟与冲刺：3 次限时模拟 + 错题复盘"""},
    {"title": "第 1 周 · C 语法地基", "md": """# 第 1 周 · C 语法地基

本周目标：掌握 C 程序结构、数据类型、运算符、输入输出、选择与循环。

## 周一 · 程序结构与数据类型

- C 程序由函数组成，有且仅有一个 main 主函数，从 main 开始执行
- 基本类型：int / float / double / char；变量必须先定义后使用
- 符号常量 #define PI 3.14；const 定义只读变量
- 自检：写一个程序，定义三个变量并赋值，输出它们的和

## 周二 · 运算符与表达式

- 算术 + - * / %：整数相除 / 取整（5/2=2），% 取余
- 关系 > < == !=、逻辑 && || !、赋值 =、自增 ++ 与自减 --
- 优先级：! > 算术 > 关系 > && > || > 赋值（记这条就够）
- 自检：算 5/2、5%2、++i 与 i++ 的区别，并写程序验证

## 周三 · 输入输出

- printf("格式", 变量)：%d %f %c %s，\n 换行、%.2f 保留两位
- scanf("格式", &变量)：**必须取地址 &**，最容易忘
- getchar / putchar 单字符输入输出
- 自检：读入两个整数，输出它们的商（保留两位小数）

## 周四 · 选择结构

- if / else if / else：else 与最近的未配对 if 结合
- switch(表达式){ case 常量: ... break; default: }
- switch 里**漏 break 会穿透**继续执行下一个 case
- 自检：读入成绩，90 以上优秀、60 以上及格、否则不及格

## 周五 · 循环结构

- for(初值; 条件; 增量)、while、do-while（至少执行一次）
- break 终止循环、continue 跳过本次循环剩余语句
- 自检：求 1~100 中偶数的和；输出九九乘法表一行

## 周末 · 公共基础 + 填空练习

- 公共基础：算法、复杂度、数据结构（栈/队列/树）
- 动手：做 3 道「程序填空题」真题，先自己补再对答案"""},
    {"title": "第 2 周 · 数组与函数", "md": """# 第 2 周 · 数组与函数

本周目标：数组（操作题主力）与函数（设计题主力）。

## 周一 · 一维数组

- 定义 int a[5]；下标从 0 到 4；越界是高频错误
- 初始化 int a[] = {1,2,3}；遍历求和、找最大/最小
- 自检：输入 10 个数存数组，输出最大值及其下标

## 周二 · 二维数组

- 定义 int b[3][4]：3 行 4 列；行优先存储
- 双重循环遍历：外层行、内层列；求每行和/列和
- 自检：3×3 矩阵，输出主对角线（i==j）元素之和

## 周三 · 字符数组与字符串

- char s[20]；字符串以 '\\0' 结尾；char s[]="hi" 占 3 字节
- 逐个字符遍历直到 '\\0'；常用的字符判断：数字、字母、空格
- 自检：统计一个字符串中数字字符的个数

## 周四 · 函数定义与调用

- 函数三要素：返回值类型、函数名、参数表；先声明后使用
- 缺省返回类型是 int；return 返回；void 无返回值
- 自检：写一个 max(a,b) 返回较大值，并在 main 中调用

## 周五 · 参数传递与作用域

- 形参接收实参的**值**（传值），函数内改形参不影响实参
- 数组名作参数传的是**首地址**，函数内可改原数组
- 全局变量/局部变量作用域；同名时局部优先
- 自检：写函数求数组平均值，函数内求和并返回

## 周末 · 公共基础 + 改错练习

- 公共基础：排序（冒泡）、查找（顺序/二分）、软件工程
- 动手：做 2 道「程序改错题」真题，找漏分号、忘 &、忘初始化"""},
    {"title": "第 3 周 · 指针、结构体与文件", "md": """# 第 3 周 · 指针、结构体与文件

本周目标：指针（C 的灵魂）、结构体、文件操作与预处理。

## 周一 · 指针基础

- 声明 int *p = &a；*p 取所指变量的值；& 取地址
- p++ 指针后移一个元素（不是 1 字节）
- 自检：定义变量和指针，通过指针修改变量的值并输出

## 周二 · 指针与数组、函数

- a[i] 与 *(a+i) 等价；数组名是首地址常量
- 指针作函数参数可实现「传引用」效果（改实参）
- 自检：用指针遍历数组求和

## 周三 · 结构体与共用体

- struct Student { int id; char name[20]; }; 定义类型
- 访问：普通变量用 .，指针用 ->（p->id）
- typedef 给类型取别名，简化写法
- 自检：定义学生结构体数组，输出总分最高者的姓名

## 周四 · 文件操作

- fopen("a.txt", "r") / "w" / "a"；失败返回 NULL 要判断
- fprintf / fscanf 按格式读写；fclose 关闭
- 自检：把 5 个整数写入文件，再读回求和输出

## 周五 · 预处理与动态内存

- #define 宏、#include 头文件；stdlib.h 提供 malloc/free
- malloc(size) 返回 void*，用前转类型；用完 free
- 字符串库函数：strlen / strcpy / strcmp / strcat
- 自检：strcmp(s1,s2)==0 判断字符串相等；strcpy 复制

## 周末 · 公共基础 + 设计题

- 公共基础：数据库基础、操作系统常识
- 动手：做 1 道「程序设计题」真题，练习写完整函数"""},
    {"title": "第 4 周 · 真题刷题", "md": """# 第 4 周 · 真题刷题

本周目标：重心转向操作题，每天一套，把填空/改错/设计练成肌肉记忆。

## 每天固定流程（约 1 小时）

1. 先做 1 道「程序填空题」（10 分钟）：补表达式，注意循环边界与初值
2. 再做 1 道「程序改错题」（15 分钟）：优先找三类错——漏分号、scanf 忘 &、忘初始化
3. 最后做 1 道「程序设计题」（20 分钟）：按套路写函数
4. 对答案，不会的考点用「小书虫」深度教学补讲

## 周一~周五 · 连做 5 套操作题

- 每道题都要**亲手在编译器里编译运行**，看到输出正确才算过
- 编译报错先看 error 行号，别怕报错，报错信息是最好老师

## 周六 · 设计题专项

- 一次写 2 道程序设计题：数组遍历/统计/求和/求平均，背熟函数模板
- 高频设计题：统计数字字符、求最大值、平均值、逆序、累加和

## 周日 · 公共基础突击 + 错题本

- 公共基础系统过一遍，把错的选择题考点记进错题本
- 整理本周所有改错题的错误类型，总结成「错误清单」"""},
    {"title": "第 5 周 · 全真模拟与冲刺", "md": """# 第 5 周 · 全真模拟与冲刺

本周目标：3 次全真模拟适应节奏，考前只做两件事：模拟 + 错题。

## 模拟安排（周二、四、六）

- 按真实考试限时 120 分钟，完整一套真题（选择 40 + 填空 18 + 改错 18 + 设计 24）
- 在考场同款 C 编译器里做，手机静音、不翻书
- 考完立即对分：选择题对错，操作题以编译运行通过为准

## 模拟后的复盘（重点）

- 选择：把公共基础错题背下来（考前突击最划算）
- 填空/改错：重新独立写一遍，直到不看答案也能跑通
- 设计题：把常用函数模板默写一遍（求和/最大/平均/统计）

## 考前 2 天

- 不再做新题，只看错题本 + 高频语法速查
- 过一遍「错误清单」：漏分号、忘 &、忘初始化、== vs =、字符串 strcmp

## 考前 1 天

- 睡够觉，不熬夜刷题
- 心态：60 分合格，你练了一个月，稳的

## 考场 10 条提醒

1. 先看操作题全部题目再动手，心里有数
2. 选择 30 分钟内必须做完
3. 每写一题就编译一次，确认能跑再保存
4. 填空先看前后语句的变量名和类型，空一定和上下文一致
5. 改错按「错误清单」逐项排查
6. 设计题先写主函数骨架再补细节，能编译就有步骤分
7. 千万别漏保存！交卷前检查每题都保存了
8. 报错看 error 行号，缺分号/括号是重灾区
9. 时间剩 15 分钟时立刻去检查保存
10. 你已经准备好了，冲！"""},
    {"title": "📝 题库 · C选择题（40 分）", "md": """# 题库 · C 选择题（40 分）

考试中选择题共 40 分（公共基础约 10 分 + C 语言知识约 30 分）。
这里收录覆盖二级 C 全部考点的选择题，配合「练习」功能刷题。

## 使用方法

1. 打开本章 → 点章节上的「练习」按钮进入刷题
2. 逐题选择答案，提交后自动判断对错并给出解析
3. 做错的题点「加入错题本」，考前集中复习

## 考点分布

- 公共基础：数据结构（栈/队列）、算法复杂度、结构化程序设计
- C 语法：数据类型、运算符、输入输出、选择/循环、数组、函数、指针、结构体、文件、预处理"""},
    {"title": "📝 题库 · C操作题（60 分）", "md": """# 题库 · C 操作题（60 分）

考试中操作题共 60 分：程序填空 18（3×6）+ 程序改错 18（2×9）+ 程序设计 24（1×24）。
这里收录典型操作题，配合「练习」功能练习。

## 使用方法

1. 打开本章 → 点章节上的「练习」按钮进入刷题
2. 在答题框里写下你的答案/代码，提交后看参考答案与解析
3. 做错的题「加入错题本」

## 高分提醒

- 填空：补表达式，注意循环边界、初值、变量类型
- 改错：先查三类高频错——漏分号、scanf 忘 &、求和忘初始化
- 设计：背熟数组遍历/统计/求和/平均的函数模板
- 考场每写一题就编译运行一次，确认能跑再保存"""},
]

QUESTION_BANK: dict[str, list[dict]] = {
    "📝 题库 · C选择题（40 分）": [
        # ── 公共基础（4）──
        {"qtype": "choice",
         "question": "下列关于栈的叙述，正确的是（）",
         "options": ["栈按“先进后出”原则组织数据", "栈按“先进先出”原则组织数据", "栈顶元素是最先被插入的元素", "栈只能在底部插入和删除元素"],
         "answer": "栈按“先进后出”原则组织数据",
         "explanation": "栈（stack）是后进先出（LIFO），只能在栈顶插入/删除；先进先出的是队列。",
         "source_text": ""},
        {"qtype": "choice",
         "question": "对长度为 n 的线性表进行冒泡排序，最坏情况下需要的比较次数是（）",
         "options": ["n(n-1)/2", "n", "n²", "n(n+1)/2"],
         "answer": "n(n-1)/2",
         "explanation": "冒泡排序最坏情况下需比较 n-1 + n-2 + … + 1 = n(n-1)/2 次。",
         "source_text": ""},
        {"qtype": "choice",
         "question": "结构化程序设计的三种基本结构是（）",
         "options": ["顺序、选择、循环", "顺序、分支、递归", "顺序、循环、跳转", "选择、循环、递归"],
         "answer": "顺序、选择、循环",
         "explanation": "结构化程序设计只使用顺序、选择（分支）、循环三种基本结构，保证程序清晰可读。",
         "source_text": ""},
        {"qtype": "choice",
         "question": "下列软件中，属于应用软件的是（）",
         "options": ["人事管理系统", "操作系统", "编译程序", "数据库管理系统"],
         "answer": "人事管理系统",
         "explanation": "操作系统、编译程序、数据库管理系统属于系统软件；人事管理系统是面向具体业务的应用软件。",
         "source_text": ""},
        # ── 程序结构/类型（5）──
        {"qtype": "choice",
         "question": "一个 C 程序总是从（）开始执行",
         "options": ["main 函数", "第一个定义的函数", "任意一个函数", "库函数"],
         "answer": "main 函数",
         "explanation": "C 程序从 main 主函数开始执行，main 是程序的入口。",
         "source_text": ""},
        {"qtype": "choice",
         "question": "一个 C 程序中，main 函数可以有（）个",
         "options": ["有且仅有一个", "可以有多个", "至少两个", "不能有"],
         "answer": "有且仅有一个",
         "explanation": "C 程序由函数组成，有且仅有一个 main 主函数作为入口。",
         "source_text": ""},
        {"qtype": "choice",
         "question": "下列 C 语言标识符合法的是（）",
         "options": ["_abc", "2abc", "a-b", "int"],
         "answer": "_abc",
         "explanation": "标识符由字母、数字、下划线组成且不能以数字开头；int 是关键字不能作标识符，a-b 含连字符非法。",
         "source_text": ""},
        {"qtype": "choice",
         "question": "在 VC 6.0 环境下，int 类型数据通常占（）个字节",
         "options": ["4", "2", "1", "8"],
         "answer": "4",
         "explanation": "32 位环境下 int 占 4 个字节，取值范围约 -21 亿到 21 亿；char 占 1 字节。",
         "source_text": ""},
        {"qtype": "choice",
         "question": "下列定义符号常量正确的是（）",
         "options": ["#define PI 3.14", "PI = 3.14", "int PI = 3.14;", "float PI(3.14)"],
         "answer": "#define PI 3.14",
         "explanation": "符号常量用 #define 定义，编译期直接替换；const 定义只读变量但不叫符号常量。",
         "source_text": ""},
        # ── 运算符（5）──
        {"qtype": "choice",
         "question": "表达式 5 / 2 的值是（）",
         "options": ["2", "2.5", "3", "1"],
         "answer": "2",
         "explanation": "两个整数相除结果为整数（截断小数），5/2 = 2；要得 2.5 需写成 5.0/2。",
         "source_text": ""},
        {"qtype": "choice",
         "question": "表达式 7 % 3 的值是（）",
         "options": ["1", "2", "3", "0"],
         "answer": "1",
         "explanation": "% 是取余运算符，7 除以 3 余 1。",
         "source_text": ""},
        {"qtype": "choice",
         "question": "已知 int i = 5; 执行 printf(\"%d\", ++i); 后输出的值是（）",
         "options": ["6", "5", "4", "不确定"],
         "answer": "6",
         "explanation": "++i 先自增再取用，i 变为 6 后输出；i++ 是先取用再自增。",
         "source_text": ""},
        {"qtype": "choice",
         "question": "已知 int a = 1, b = 2; 表达式 !a && b 的值是（）",
         "options": ["0", "1", "2", "-1"],
         "answer": "0",
         "explanation": "!a = !1 = 0，0 && b = 0；逻辑运算的结果只有 0 或 1。",
         "source_text": ""},
        {"qtype": "choice",
         "question": "C 语言中，关系表达式的值是（）",
         "options": ["0 或 1", "任意整数", "浮点数", "true 或 false 两个关键字"],
         "answer": "0 或 1",
         "explanation": "关系表达式结果为真得 1、假得 0（int 型），而不是 true/false 关键字。",
         "source_text": ""},
        # ── 输入输出（3）──
        {"qtype": "choice",
         "question": "使用 scanf 给整型变量 a 赋值，下列写法正确的是（）",
         "options": ["scanf(\"%d\", &a);", "scanf(\"%d\", a);", "scanf(\"%d\", &a)", "scanf a;"],
         "answer": "scanf(\"%d\", &a);",
         "explanation": "scanf 必须传变量的地址（加 &），且语句末尾要有分号；漏 & 是改错题高频错误。",
         "source_text": ""},
        {"qtype": "choice",
         "question": "getchar() 函数的功能是（）",
         "options": ["从键盘读入一个字符", "从键盘读入一个整数", "向屏幕输出一个字符", "读入一个字符串"],
         "answer": "从键盘读入一个字符",
         "explanation": "getchar() 从标准输入读入一个字符并返回；putchar() 输出一个字符。",
         "source_text": ""},
        {"qtype": "choice",
         "question": "C 语言中，转义字符 '\\n' 表示（）",
         "options": ["换行", "制表符", "回车", "空格"],
         "answer": "换行",
         "explanation": "'\\n' 是换行符，光标移到下一行行首；'\\t' 是制表符。",
         "source_text": ""},
        # ── 选择/循环（5）──
        {"qtype": "choice",
         "question": "下列关于 if-else 的叙述，正确的是（）",
         "options": ["else 总是与最近的未匹配的 if 配对", "else 与第一个 if 配对", "else 与最后一个 if 配对", "一个 if 可以与多个 else 配对"],
         "answer": "else 总是与最近的未匹配的 if 配对",
         "explanation": "else 与前面最近的未配对的 if 结合，这是「悬空 else」问题。",
         "source_text": ""},
        {"qtype": "choice",
         "question": "switch 语句中，若某个 case 后没有 break，则（）",
         "options": ["继续执行下一个 case 的语句", "立即跳出 switch", "立即结束程序", "编译报错"],
         "answer": "继续执行下一个 case 的语句",
         "explanation": "switch 具有「穿透」特性：case 后无 break 会继续执行后续 case 的语句，直到遇到 break。",
         "source_text": ""},
        {"qtype": "choice",
         "question": "下列 for 循环体会执行（）次：for(i = 0; i < 5; i++)",
         "options": ["5", "6", "4", "不确定"],
         "answer": "5",
         "explanation": "i 取 0、1、2、3、4 共 5 次，i=5 时不满足条件 i<5 退出。",
         "source_text": ""},
        {"qtype": "choice",
         "question": "下列关于 do-while 与 while 的叙述，正确的是（）",
         "options": ["do-while 至少执行一次循环体", "while 至少执行一次循环体", "do-while 可能一次都不执行", "两者完全等价"],
         "answer": "do-while 至少执行一次循环体",
         "explanation": "do-while 先执行循环体再判断条件，所以至少执行一次；while 可能一次都不执行。",
         "source_text": ""},
        {"qtype": "choice",
         "question": "循环中 continue 语句的作用是（）",
         "options": ["结束本次循环，进入下一次循环", "终止整个循环", "结束当前函数", "退出程序"],
         "answer": "结束本次循环，进入下一次循环",
         "explanation": "continue 跳过本次循环体剩余语句直接进入下一次；break 才是终止整个循环。",
         "source_text": ""},
        # ── 数组（4）──
        {"qtype": "choice",
         "question": "已知 int a[5]; 数组 a 的下标（索引）取值范围是（）",
         "options": ["0 到 4", "1 到 5", "0 到 5", "1 到 4"],
         "answer": "0 到 4",
         "explanation": "C 数组下标从 0 开始，a[5] 的下标是 0~4；访问 a[5] 属越界错误。",
         "source_text": ""},
        {"qtype": "choice",
         "question": "已知 int a[] = {1, 2, 3}; 数组 a 的长度（元素个数）是（）",
         "options": ["3", "2", "4", "不确定"],
         "answer": "3",
         "explanation": "不写长度的数组由初始化列表决定长度，{1,2,3} 对应 3 个元素。",
         "source_text": ""},
        {"qtype": "choice",
         "question": "已知 char s[] = \"hi\"; 数组 s 占（）个字节",
         "options": ["3", "2", "4", "5"],
         "answer": "3",
         "explanation": "字符串 \"hi\" 有 2 个字符 + 结尾的 '\\0'，共 3 个字节。",
         "source_text": ""},
        {"qtype": "choice",
         "question": "C 语言中，字符串以（）字符结尾",
         "options": ["'\\0'", "'\\n'", "空格", "句号"],
         "answer": "'\\0'",
         "explanation": "字符串以空字符 '\\0' 结尾，遍历字符串通常用 s[i] != '\\0' 作循环条件。",
         "source_text": ""},
        # ── 函数（4）──
        {"qtype": "choice",
         "question": "下列叙述正确的是（）",
         "options": ["函数形参接收实参的值，形参的修改不影响实参", "函数形参的修改会直接改变实参", "函数不能有返回值", "函数必须定义在主函数之前"],
         "answer": "函数形参接收实参的值，形参的修改不影响实参",
         "explanation": "C 默认按值传递：形参是实参的副本，函数内修改形参不影响实参；要改实参需用指针。",
         "source_text": ""},
        {"qtype": "choice",
         "question": "若函数定义时未指定返回值类型，其默认返回类型是（）",
         "options": ["int", "void", "float", "char"],
         "answer": "int",
         "explanation": "C 语言中省略返回值类型时默认是 int（老式写法），现代建议显式写出。",
         "source_text": ""},
        {"qtype": "choice",
         "question": "下列关于局部变量的叙述，正确的是（）",
         "options": ["局部变量的作用域只在其所在的函数（块）内", "局部变量作用域是整个程序", "局部变量与全局变量不能同名", "局部变量未初始化时默认值为 0"],
         "answer": "局部变量的作用域只在其所在的函数（块）内",
         "explanation": "局部变量作用域从定义处到所在块结束；未初始化的局部变量值不确定，不是默认 0。",
         "source_text": ""},
        {"qtype": "choice",
         "question": "strlen(\"abc\") 的返回值是（）",
         "options": ["3", "4", "2", "5"],
         "answer": "3",
         "explanation": "strlen 统计字符串长度，不含结尾的 '\\0'，\"abc\" 长度为 3。",
         "source_text": ""},
        {"qtype": "choice",
         "question": "数组名作为函数实参传递给函数时，下列说法正确的是（）",
         "options": ["传递的是数组首地址，函数内可修改原数组元素", "传递的是数组元素的副本", "数组不能作为函数参数", "传递的是数组的长度"],
         "answer": "传递的是数组首地址，函数内可修改原数组元素",
         "explanation": "数组名作实参传递的是首地址（等价指针），函数内通过下标即可修改原数组；这与基本类型按值传递不同。",
         "source_text": ""},
        # ── 指针（3）──
        {"qtype": "choice",
         "question": "下列声明指针变量正确的是（）",
         "options": ["int *p;", "int p*;", "p int*;", "int &p;"],
         "answer": "int *p;",
         "explanation": "指针声明写法是 类型 + * + 变量名：int *p 表示 p 是指向 int 的指针；& 是取地址不是指针声明。",
         "source_text": ""},
        {"qtype": "choice",
         "question": "已知 int a[5]; 则 a[i] 与（）等价",
         "options": ["*(a + i)", "&a[i]", "a + i", "*a + i"],
         "answer": "*(a + i)",
         "explanation": "a 是首地址，a[i] 等价于 *(a+i)，即地址 a+i 处的内容。",
         "source_text": ""},
        {"qtype": "choice",
         "question": "已知 int a[5], *p = a; 执行 p++; 后，p 指向（）",
         "options": ["数组的下一个元素 a[1]", "数组的首地址", "数组的最后一个元素", "未知地址"],
         "answer": "数组的下一个元素 a[1]",
         "explanation": "指针 +1 按所指类型的大小后移一个元素，p 从 a[0] 移到 a[1]，不是 1 字节。",
         "source_text": ""},
        # ── 结构体/typedef（3）──
        {"qtype": "choice",
         "question": "下列定义结构体类型正确的是（）",
         "options": ["struct Student { int id; char name[20]; };", "struct Student { int id; char name[20]; }", "int struct Student;", "struct Student int { id; }"],
         "answer": "struct Student { int id; char name[20]; };",
         "explanation": "结构体类型定义以分号结尾：struct 类型名 { 成员 }; 漏分号是常见错误。",
         "source_text": ""},
        {"qtype": "choice",
         "question": "已知 struct Point { int x, y; } p, *q = &p; 下列访问 p.x 正确的是（）",
         "options": ["q->x", "q.x", "*q.x", "p->x"],
         "answer": "q->x",
         "explanation": "结构体指针访问成员用 ->（q->x），普通变量用 .（p.x）；q.x 和 p->x 用法错误。",
         "source_text": ""},
        {"qtype": "choice",
         "question": "typedef int INTEGER; 的作用是（）",
         "options": ["为 int 取一个别名 INTEGER，之后可用 INTEGER 定义整型变量", "定义一个整型变量", "定义一个宏", "定义一个新类型，与 int 无关"],
         "answer": "为 int 取一个别名 INTEGER，之后可用 INTEGER 定义整型变量",
         "explanation": "typedef 为已有类型起别名，如 typedef int INTEGER; 后 INTEGER x; 等价于 int x;。",
         "source_text": ""},
        # ── 文件/动态内存（3）──
        {"qtype": "choice",
         "question": "下列以「只读」方式打开文件 a.txt 的是（）",
         "options": ["fopen(\"a.txt\", \"r\");", "fopen(\"a.txt\", \"w\");", "fopen(\"a.txt\", \"a\");", "fopen(\"a.txt\", \"w+\");"],
         "answer": "fopen(\"a.txt\", \"r\");",
         "explanation": "\"r\" 只读（文件须存在）、\"w\" 只写（清空重建）、\"a\" 追加；文件打不开时返回 NULL。",
         "source_text": ""},
        {"qtype": "choice",
         "question": "文件使用完毕后，应调用（）关闭",
         "options": ["fclose(fp);", "fopen(fp);", "scanf(fp);", "printf(fp);"],
         "answer": "fclose(fp);",
         "explanation": "fclose(fp) 关闭文件，释放资源；fopen 是打开不是关闭。",
         "source_text": ""},
        {"qtype": "choice",
         "question": "malloc 函数用于动态分配内存，其返回值类型是（）",
         "options": ["void*", "int*", "char*", "float*"],
         "answer": "void*",
         "explanation": "malloc 返回 void* 指针（指向未定类型），使用时通常转成目标类型，用完要 free 释放。",
         "source_text": ""},
    ],
    "📝 题库 · C操作题（60 分）": [
        # ── 程序填空（4）──
        {"qtype": "essay",
         "question": "程序填空：下面的程序计算 1 到 n 的累加和，请补全 for 循环中的两处空。\nint main(){ int i, n, sum = 0; scanf(\"%d\", &n); for(i = 1; i <= n; ____) sum += ____; printf(\"%d\", sum); return 0; }",
         "answer": "第一处空填 i++，让循环变量每次加一；第二处空填 i，把当前 i 累加到 sum。注意 sum 已初始化为 0，循环条件 i <= n 包含 n 本身。",
         "explanation": "参考实现：\nfor (i = 1; i <= n; i++)\n    sum += i;\n累加和是填空高频题，循环边界和增量一定要看仔细。",
         "source_text": ""},
        {"qtype": "essay",
         "question": "程序填空：下面的程序求数组 a[10] 中的最大值并输出，请补全。\nint a[10], i, max; for(i = 0; i < 10; i++) scanf(\"%d\", &a[i]); max = ____; for(i = 1; i < 10; i++) if(a[i] > max) max = a[i]; printf(\"%d\", max);",
         "answer": "第一个循环读入 10 个数后，max 应初始化为 a[0]，即填空处填 a[0]；第二个循环从 i=1 开始逐个比较，比 max 大就更新 max。",
         "explanation": "参考实现：\nmax = a[0];\nfor (i = 1; i < 10; i++)\n    if (a[i] > max) max = a[i];\n求最大值套路：先假设第一个是最大，再逐个比较更新。",
         "source_text": ""},
        {"qtype": "essay",
         "question": "程序填空：下面的程序统计字符串 s 中数字字符的个数，请补全循环条件。\nchar s[100]; int i = 0, count = 0; gets(s); while(s[i] ____ '\\0'){ if(s[i] >= '0' && s[i] <= '9') ____; i++; } printf(\"%d\", count);",
         "answer": "循环条件是 s[i] != '\\0'，即遇到字符串结尾就停止；数字判断成立时 count 要加一，即填 count++。",
         "explanation": "参考实现：\nwhile (s[i] != '\\0') {\n    if (s[i] >= '0' && s[i] <= '9') count++;\n    i++;\n}\n字符串遍历以 '\\0' 结束，是操作题最常用的循环条件。",
         "source_text": ""},
        {"qtype": "essay",
         "question": "程序填空：下面的程序判断年份 year 是否为闰年（能被 4 整除且不能被 100 整除，或能被 400 整除），请补全条件。\nif((year % 4 == 0 ____ year % 100 != 0) || ____ == 0) printf(\"闰年\"); else printf(\"平年\");",
         "answer": "第一个空填 &&，表示两个条件同时成立；第二个空填 year % 400，即能被 400 整除。闰年判断是经典逻辑题。",
         "explanation": "参考实现：\nif ((year % 4 == 0 && year % 100 != 0) || year % 400 == 0)\n    printf(\"闰年\");\n闰年 = 能被4整除且不能被100整除，或能被400整除。",
         "source_text": ""},
        # ── 程序改错（3）──
        {"qtype": "essay",
         "question": "程序改错：下面的函数求两个数的较大值，编译不报错但运行结果不对，请改正。\nint max(int a, int b){ int m; if(a > b) m = a; else m = b; }",
         "answer": "函数缺少 return 语句，m 计算后没有返回给调用者。应改为：函数结束前加 return m;，否则返回的随机值是垃圾数据。",
         "explanation": "改正后：\nint max(int a, int b){\n    int m;\n    if (a > b) m = a; else m = b;\n    return m;\n}\n改错高频点：函数漏 return。",
         "source_text": ""},
        {"qtype": "essay",
         "question": "程序改错：下面的程序求 1 到 10 的和，结果却不对，请改正。\nint main(){ int i, sum; for(i = 1; i <= 10; i++) sum += i; printf(\"%d\", sum); return 0; }",
         "answer": "求和变量 sum 没有初始化，会从不确定的垃圾值开始累加。应改为 int sum = 0;，累加前先清零。",
         "explanation": "改正后：\nint i, sum = 0;\nfor (i = 1; i <= 10; i++) sum += i;\n改错高频点：累加/计数变量忘记初始化。",
         "source_text": ""},
        {"qtype": "essay",
         "question": "程序改错：下面的程序想判断两个字符串是否相等，运行结果却不对，请改正。\nchar s1[] = \"abc\", s2[] = \"abc\"; if(s1 == s2) printf(\"相等\"); else printf(\"不相等\");",
         "answer": "两个字符数组不能用 == 直接比较，那样比较的是首地址而不是内容。应使用 strcmp(s1, s2) == 0 判断字符串相等。",
         "explanation": "改正后：\nif (strcmp(s1, s2) == 0) printf(\"相等\");\n字符串比较必须用 strcmp，返回值 0 表示相等。改错高频点。",
         "source_text": ""},
        # ── 程序设计（2）──
        {"qtype": "essay",
         "question": "程序设计题：编写函数 int count_digit(char s[])，统计字符串 s 中数字字符（'0'~'9'）的个数并返回。",
         "answer": "用循环遍历字符串直到 '\\0'，对每个字符用 s[i] >= '0' && s[i] <= '9' 判断是否为数字，是则计数器加一，循环结束后返回计数器。",
         "explanation": "参考实现：\nint count_digit(char s[]) {\n    int count = 0, i = 0;\n    while (s[i] != '\\0') {\n        if (s[i] >= '0' && s[i] <= '9') count++;\n        i++;\n    }\n    return count;\n}\n数字字符判断、字符串遍历是设计题最经典的套路。",
         "source_text": ""},
        {"qtype": "essay",
         "question": "程序设计题：编写函数 float average(int a[], int n)，求数组 a 前 n 个元素的平均值并返回。",
         "answer": "用 for 循环累加数组元素到 sum，最后除以 n 得到平均值；注意返回 float，要用 (float)sum / n 避免整数相除截断。",
         "explanation": "参考实现：\nfloat average(int a[], int n) {\n    int sum = 0, i;\n    for (i = 0; i < n; i++) sum += a[i];\n    return (float)sum / n;\n}\n整型除整型会截断小数，转成 float 再除才能得到平均值。",
         "source_text": ""},
    ],
}

# 操作题子型：fill=程序填空 / correct=程序改错 / design=程序设计
ESSAY_SUBTYPE_MAP: dict[str, str] = {
    "程序填空：下面的程序计算 1 到 n 的累加和": "fill",
    "程序填空：下面的程序求数组 a[10] 中的最大值": "fill",
    "程序填空：下面的程序统计字符串 s 中数字字符": "fill",
    "程序填空：下面的程序判断年份 year 是否为闰年": "fill",
    "程序改错：下面的函数求两个数的较大值": "correct",
    "程序改错：下面的程序求 1 到 10 的和": "correct",
    "程序改错：下面的程序想判断两个字符串是否相等": "correct",
    "程序设计题：编写函数 int count_digit": "design",
    "程序设计题：编写函数 float average": "design",
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


async def ensure_ncre_c() -> None:
    """幂等种入「计算机二级 · C 语言程序设计」课程书 + 题库。"""
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
                subject="C语言程序设计",
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

        await _sync_questions(db, course)
        await db.commit()
        if added:
            logger.info("课程「%s」新增 %d 章（共 %d 章）", COURSE_TITLE, added, len(CHAPTERS))
        else:
            logger.info("课程「%s」已完整（%d 章），跳过", COURSE_TITLE, len(CHAPTERS))


async def _add_chapter(db: AsyncSession, course: Project, ch: dict, idx: int) -> None:
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

    text, hints = parse_file(file_path)
    for seq, c in enumerate(chunk_text(text, hints)):
        db.add(Chunk(
            document_id=doc.id,
            seq=seq,
            content=c["content"],
            heading=c["heading"] or ch["title"],
        ))


async def _sync_questions(db: AsyncSession, course: Project) -> None:
    """题目级幂等同步：补齐缺失的题，并为操作题回填 subtype。"""
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
            if row is None:
                db.add(Question(
                    document_id=doc.id,
                    qtype=q["qtype"],
                    question=q["question"],
                    options=json.dumps(q.get("options") or [], ensure_ascii=False),
                    answer=q["answer"],
                    explanation=q.get("explanation", ""),
                    source_text=q.get("source_text", ""),
                    subtype=essay_subtype(q["question"]) if q["qtype"] != "choice" else "",
                ))
                added += 1
            elif q["qtype"] != "choice" and not row.subtype:
                sub = essay_subtype(q["question"])
                if sub:
                    row.subtype = sub
                    filled += 1
    if added or filled:
        logger.info("C 题库同步：新增 %d 题，回填 subtype %d 题", added, filled)
