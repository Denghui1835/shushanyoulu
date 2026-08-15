# Python 实战：跑通第一个模型

不需要会写代码，**复制 → 改数字 → 看结果** 就是备赛期的入门方式。以下三个例子覆盖"优化 / 预测 / 评价"三类模型。

## 0. 准备

安装依赖（终端执行一次）：

```bash
pip install numpy scipy pulp
```

## 1. 优化：奶茶店排产（线性规划）

```python
from pulp import LpProblem, LpMaximize, LpVariable, LpInteger, LpStatus

# 决策变量：A 做 x 杯，B 做 y 杯
x = LpVariable("x", lowBound=0, upBound=60, cat=LpInteger)
y = LpVariable("y", lowBound=0, upBound=50, cat=LpInteger)

prob = LpProblem("tea", LpMaximize)
prob += 3 * x + 5 * y          # 目标：利润最大
prob += x + y <= 100           # 约束：原料最多 100 杯

prob.solve()
print("状态:", LpStatus[prob.status])
print("A 杯数:", x.varValue, " B 杯数:", y.varValue, " 最大利润:", prob.objective.value())
```

把 `upBound`、利润、约束改成你题目的数字，就是你的第一个优化模型。

## 2. 预测：销量最小二乘拟合

```python
import numpy as np

# 过去 6 个月的销量
months = np.array([1, 2, 3, 4, 5, 6])
sales  = np.array([120, 150, 180, 210, 260, 300])

# 线性拟合：sales = k * months + b
k, b = np.polyfit(months, sales, 1)
print(f"趋势: 销量 = {k:.1f} * 月份 + {b:.1f}")

month7 = 7
print(f"第 7 个月预测销量: {k * month7 + b:.0f}")
```

画图前先描点（`matplotlib`），确认确实是线性趋势再用线性拟合；弯了就换二次/指数拟合。

## 3. 评价：AHP 权重计算（两准则示例）

```python
import numpy as np

# 判断矩阵：第 i 行第 j 列 = 准则 i 比准则 j 重要多少
# 示例只有 2 个准则：费用、风景（费用比风景重要 3 倍）
A = np.array([[1, 3],
              [1/3, 1]])

eigvals, eigvecs = np.linalg.eig(A)
max_idx = int(np.argmax(eigvals.real))
weight = np.abs(eigvecs[:, max_idx].real)
weight = weight / weight.sum()
print("权重:", np.round(weight, 3))   # 例如 [0.75, 0.25]
```

多准则时把矩阵扩成 3×3、4×4 即可；记得算一致性比例 CR，论文里要报告。

## 4. 三个"比赛级"习惯

1. **先想后写**：写代码前，先在纸上把"变量、目标、约束"列出来。
2. **留痕**：每个结果配上代码和参数，截图进附录。
3. **参数化**：把关键数字写成变量，方便做敏感性分析（改一个数重跑一遍）。

下一篇讲**论文写作**——模型再漂亮，写不出来等于白做。
