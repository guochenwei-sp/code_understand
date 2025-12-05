# Architecture Analysis Guide

## 目录

1. [DSM Matrix（依赖结构矩阵）](#dsm-matrix依赖结构矩阵)
2. [Architecture Analysis（架构分析）](#architecture-analysis架构分析)
3. [综合分析工作流](#综合分析工作流)
4. [实际案例：重构指导](#实际案例重构指导)
5. [最佳实践](#最佳实践)

---

## DSM Matrix（依赖结构矩阵）

### 定义

DSM (Dependency Structure Matrix) 是一个方阵，用于可视化代码文件之间的依赖关系。矩阵中的每一行和每一列代表一个文件，交叉点的数字表示依赖关系的数量。

### 实现原理

**位置：** `backend/app/main.py:165-195`

DSM 基于 `#include` 关系构建：
- **行**：依赖源（哪个文件包含了其他文件）
- **列**：被依赖目标（被哪个文件包含）
- **值**：`#include` 语句的数量

### 矩阵示例

```
           file1  file2  file3  file4
file1        -      0      0      1     ← file1 包含 file4
file2        2      -      1      0     ← file2 包含 file1(2次) 和 file3(1次)
file3        1      3      -      2     ← file3 包含 file1, file2(3次), file4(2次)
file4        0      0      0      -     ← file4 不包含其他文件（基础文件）
```

### 如何帮助分析架构

#### 1. 识别循环依赖

**特征：** 矩阵中红色单元格（i依赖j且j依赖i）

```
循环依赖示例：
           auth.h  session.h
auth.h       -        1        ← auth.h 包含 session.h
session.h    2        -        ← session.h 包含 auth.h (循环!)
```

**问题：**
- 编译顺序难以确定
- 增加代码耦合度
- 难以单独测试模块
- 重构困难

#### 2. 识别模块耦合度

**特征：** 蓝色单元格的数量和分布

- **高耦合**：矩阵中大量非零值，分布杂乱
- **低耦合**：大部分为0，非零值集中在对角线附近

```
高耦合（不好）：
           A  B  C  D  E
A          -  2  1  3  1
B          1  -  2  1  2
C          2  3  -  2  1
D          1  1  1  -  2
E          2  1  2  1  -

低耦合（好）：
           A  B  C  D  E
A          -  1  0  0  0
B          0  -  2  0  0
C          0  0  -  1  0
D          0  0  0  -  1
E          0  0  0  0  -
```

#### 3. 评估代码组织质量

**理想形态：** 矩阵应该接近**上三角形**或**下三角形**

```
上三角形（分层架构）：
           L0  L1  L2  L3
Layer0(基础) -   0   0   0   ← 不依赖任何文件
Layer1       2   -   0   0   ← 只依赖Layer0
Layer2       1   3   -   0   ← 依赖Layer0和Layer1
Layer3       0   2   1   -   ← 依赖Layer1和Layer2
```

**对角线形态：** 表示清晰的分层，高层依赖低层，低层不依赖高层

### 使用建议

1. **查看整体形状**
   - 接近三角形 → ✅ 架构清晰
   - 散乱分布 → ❌ 架构混乱

2. **检查红色单元格**
   - 0个 → ✅ 无循环依赖
   - 有红色 → ❌ 必须解决循环依赖

3. **评估数值大小**
   - 小数字(1-2) → ✅ 正常依赖
   - 大数字(>5) → ⚠️ 可能过度依赖

---

## Architecture Analysis（架构分析）

架构分析提供三个核心功能，帮助深入理解代码结构：

### 1. Hotspots（复杂度热点）

#### 定义

识别圈复杂度最高的文件，这些文件最需要重构。

**实现位置：** `backend/app/core/arch_analyzer.py:74-102`

```python
def get_hotspot_files(self, top_n=10):
    """
    计算每个文件的：
    - 总圈复杂度（所有函数复杂度之和）
    - 平均圈复杂度
    - 函数数量
    - 符号数量
    """
```

#### 圈复杂度指标

| 复杂度 | 风险等级 | 建议 |
|--------|---------|------|
| 1-5    | 🟢 低   | 简单代码，易于维护 |
| 6-10   | 🟡 中   | 较复杂，需要注意 |
| 11-20  | 🟠 高   | 复杂，建议重构 |
| 21+    | 🔴 极高 | 极度复杂，必须重构 |

#### 如何帮助

**1. 定位技术债务**
```
Hotspot分析结果：
====================
1. network_stack.c
   - 总复杂度: 245
   - 平均复杂度: 15.3
   - 函数数量: 16
   - 符号数量: 48

2. parser.c
   - 总复杂度: 189
   - 平均复杂度: 12.6
   - 函数数量: 15
   - 符号数量: 52
```

**重构优先级：**
1. network_stack.c - 平均复杂度15.3，需要拆分大函数
2. parser.c - 平均复杂度12.6，需要简化逻辑

**2. 预防Bug**

研究表明：**圈复杂度与Bug密度正相关**

```
复杂度 > 10 的函数出Bug概率是复杂度 < 5 的函数的 5-10 倍
```

**3. 代码审查重点**

```
审查策略：
- 复杂度 > 15 → 必须审查，要求重构计划
- 复杂度 10-15 → 重点审查，添加单元测试
- 复杂度 < 10 → 常规审查
```

### 2. Circular Dependencies（循环依赖检测）

#### 定义

使用 **Tarjan算法** 检测强连通分量（SCC），找出所有循环依赖环。

**实现位置：** `backend/app/core/arch_analyzer.py:13-40`

```python
def detect_circular_dependencies(self):
    """
    1. 基于 #include 关系构建有向图
    2. 使用Tarjan算法查找强连通分量
    3. 返回所有包含2个以上文件的环
    """
```

#### 循环依赖类型

**类型1：双向依赖**
```c
// auth.h
#include "session.h"

// session.h
#include "auth.h"
```
→ **最常见，最容易解决**

**类型2：三角依赖**
```c
// A.h
#include "B.h"

// B.h
#include "C.h"

// C.h
#include "A.h"
```
→ **较复杂，需要仔细分析**

**类型3：多文件环**
```
A.h → B.h → C.h → D.h → E.h → A.h
```
→ **最复杂，通常表示架构问题**

#### 危害

1. **编译问题**
   - 头文件保护失效
   - 无限递归包含
   - 编译顺序混乱

2. **维护问题**
   - 模块无法独立修改
   - 难以理解代码流程
   - 增加认知负担

3. **测试问题**
   - 无法单元测试（循环依赖的模块必须一起测试）
   - Mock困难

#### 解决方案

**方案1：前向声明**
```c
// 问题代码
// auth.h
#include "session.h"
typedef struct {
    Session* session;
} Auth;

// 解决方案
// auth.h
typedef struct Session Session;  // 前向声明
typedef struct {
    Session* session;
} Auth;
```

**方案2：接口抽象**
```c
// 问题：auth.c ↔ session.c 循环依赖

// 解决：引入接口层
auth_interface.h (接口定义)
    ├── auth.c (实现接口)
    └── session.c (使用接口，不依赖具体实现)
```

**方案3：提取共用部分**
```c
// 问题：A.h ↔ B.h 循环依赖，因为共享类型定义

// 解决：提取到common.h
common.h (共享类型)
    ├── A.h (包含 common.h)
    └── B.h (包含 common.h)
```

### 3. Levelization（分层分析）

#### 定义

基于拓扑排序计算文件的依赖层级，评估架构分层质量。

**实现位置：** `backend/app/core/arch_analyzer.py:42-72`

```python
def compute_levelization(self):
    """
    算法：
    1. Layer 0：不依赖任何其他文件（基础文件）
    2. Layer N：依赖的最高层级 + 1
    3. 循环依赖的文件标记为 -1
    """
```

#### 分层示例

```
优秀的分层结构：
====================
Layer 0 (基础层) - 7 files
  ├── types.h
  ├── constants.h
  ├── macros.h
  ├── error_codes.h
  └── ...

Layer 1 (工具层) - 12 files
  ├── string_utils.c
  ├── memory.c
  ├── logger.c
  └── ...

Layer 2 (核心逻辑层) - 8 files
  ├── parser.c
  ├── compiler.c
  ├── optimizer.c
  └── ...

Layer 3 (应用层) - 3 files
  ├── main.c
  ├── cli.c
  └── config.c
```

#### 评估标准

**1. 层数合理性**
```
小项目 (< 50 files):  3-5 层 ✅
中项目 (50-200 files): 5-8 层 ✅
大项目 (> 200 files):  8-12 层 ✅

层数过多 (> 15): ⚠️ 可能过度设计
层数过少 (< 3):  ⚠️ 可能缺乏分层
```

**2. 层间跳跃**
```
✅ 好：Layer 3 依赖 Layer 2, 1, 0
❌ 坏：Layer 5 直接依赖 Layer 0 (跨越了3层)
```

**3. 文件分布**
```
✅ 好：金字塔型分布
    Layer 0: 20 files (基础层最多)
    Layer 1: 15 files
    Layer 2: 10 files
    Layer 3: 5 files

❌ 坏：倒金字塔
    Layer 0: 5 files
    Layer 1: 10 files
    Layer 2: 20 files (高层文件太多)
```

#### 如何帮助

**1. 验证设计原则**

检查是否遵循"高层依赖低层"原则：
```
依赖方向应该是：
应用层 → 业务逻辑层 → 工具层 → 基础层

不应该出现：
基础层 → 应用层 (反向依赖)
```

**2. 识别架构违规**

```
示例：发现问题
==================
types.h (Layer 0) 被标记为 Layer 3

原因分析：
types.h 包含了 config.h (Layer 2)
→ 这是错误的！基础类型不应该依赖配置

解决：
将配置相关类型从 types.h 移到 config_types.h
```

**3. 指导模块划分**

```
如果 Layer 2 有30个文件：
→ 考虑进一步划分
    Layer 2a: 数据结构
    Layer 2b: 算法
    Layer 2c: I/O操作
```

---

## 综合分析工作流

### Step 1: 查看 Levelization（分层）

**目标：** 了解项目的整体架构层次

```
检查清单：
□ 是否有清晰的层次结构？
□ 层数是否合理？
□ 文件分布是否合理（金字塔型）？
□ 是否有反向依赖？
```

**示例分析：**
```
分层结果：
- 总层数: 6 层
- Layer 0: 15 files (25%)
- Layer 1: 18 files (30%)
- Layer 2: 12 files (20%)
- Layer 3: 8 files (13%)
- Layer 4: 5 files (8%)
- Layer 5: 2 files (3%)

评估：✅ 金字塔型分布，架构清晰
```

### Step 2: 检查 Circular Dependencies（循环依赖）

**目标：** 发现架构致命问题

```
检查清单：
□ 循环依赖数量？
□ 每个循环涉及多少文件？
□ 循环依赖是否在同一模块内？
□ 是否有简单的解决方案？
```

**示例分析：**
```
循环依赖检测结果：
==================
发现 2 个循环：

Cycle 1 (简单): 2 files
  auth.h ↔ session.h

  评估：✅ 可以用前向声明轻松解决

Cycle 2 (复杂): 5 files
  network.c → parser.c → protocol.c → buffer.c → network.c

  评估：❌ 严重问题，需要架构重构
```

### Step 3: 分析 Hotspots（热点）

**目标：** 识别重构优先级

```
检查清单：
□ Top 10 热点文件的复杂度？
□ 是否有极高复杂度（>20）的文件？
□ 热点文件在哪些层？
□ 是否可以拆分？
```

**示例分析：**
```
复杂度热点：
==================
1. network_stack.c
   - 总复杂度: 245
   - 平均复杂度: 15.3
   - Layer: 2 (核心逻辑层)

   评估：⚠️ 需要重构，拆分为多个小文件

2. main.c
   - 总复杂度: 89
   - 平均复杂度: 8.9
   - Layer: 5 (应用层)

   评估：✅ 复杂度合理
```

### Step 4: 查看 DSM Matrix

**目标：** 可视化依赖关系

```
检查清单：
□ 矩阵是否接近三角形？
□ 是否有红色单元格（循环）？
□ 是否有远离对角线的大数字（跨层依赖）？
□ 同一模块的文件是否聚集？
```

**示例分析：**
```
DSM观察：
==================
1. ✅ 整体呈上三角形，分层清晰
2. ❌ 发现2个红色单元格（与Cycle检测一致）
3. ⚠️ file_a.c (Layer 4) 依赖 file_b.c (Layer 1)
   → 跨越了3层，需要检查是否合理
```

---

## 实际案例：重构指导

### 案例背景

分析一个中型C项目（150个文件），发现多个架构问题：

```
项目分析报告：
====================
文件总数: 150
循环依赖: 3 个
最大层级: 8 层
热点文件: 12 个（复杂度 > 100）
```

### 问题1：循环依赖

**检测结果：**
```
Cycle 1: auth.c ↔ session.c
  - auth.c 包含 session.h
  - session.c 包含 auth.h

Cycle 2: network.c → parser.c → protocol.c → network.c
  - 3个文件形成环

Cycle 3: ui_main.c ↔ ui_dialog.c ↔ ui_widget.c
  - UI模块内部循环
```

**解决方案：**

#### Cycle 1: 使用前向声明
```c
// 修改前
// auth.h
#include "session.h"
typedef struct {
    Session* current_session;
    int user_id;
} AuthContext;

// 修改后
// auth.h
typedef struct Session Session;  // 前向声明
typedef struct {
    Session* current_session;
    int user_id;
} AuthContext;
```

#### Cycle 2: 引入接口层
```c
// 修改前的依赖
network.c → parser.c → protocol.c → network.c

// 修改后
protocol_interface.h (接口定义)
    ├── network.c (实现接口)
    ├── parser.c (实现接口)
    └── protocol.c (使用接口)
```

#### Cycle 3: 提取公共基础
```c
// 修改前
ui_main.c ↔ ui_dialog.c ↔ ui_widget.c
(互相依赖，因为共享widget类型和事件)

// 修改后
ui_types.h (基础类型)
ui_events.h (事件定义)
    ├── ui_main.c
    ├── ui_dialog.c
    └── ui_widget.c
```

### 问题2：分层混乱

**检测结果：**
```
Levelization分析：
==================
Layer 0: 10 files
Layer 1: 15 files
Layer 2: 18 files
Layer 3: 25 files  ← 文件太多
Layer 4: 30 files  ← 文件太多
Layer 5: 22 files
Layer 6: 15 files
Layer 7: 10 files
Layer 8: 5 files

问题：
1. 层数过多（8层）
2. 中间层文件过多
3. 不是金字塔型分布
```

**DSM Matrix显示：**
```
发现问题：
- Layer 7 的文件依赖 Layer 2 (跨5层)
- Layer 4 的文件直接依赖 Layer 0 (跨3层)
```

**解决方案：**

1. **合并相似层**
```
Layer 3 和 Layer 4 功能相似
→ 合并为 Layer 3 (业务逻辑层)

修改后：
Layer 0: 基础层 (10 files)
Layer 1: 工具层 (15 files)
Layer 2: 数据层 (18 files)
Layer 3: 业务逻辑层 (55 files) ← 合并后
Layer 4: 服务层 (22 files)
Layer 5: 应用层 (30 files)
```

2. **消除跨层依赖**
```c
// 问题：ui_manager.c (Layer 7) 依赖 memory.c (Layer 2)

// 解决：通过中间层
ui_manager.c (Layer 7)
    ↓
resource_manager.c (Layer 4) ← 引入中间层
    ↓
memory.c (Layer 2)
```

### 问题3：复杂度热点

**检测结果：**
```
Top 5 Hotspots:
==================
1. network_stack.c
   - 总复杂度: 289
   - 函数数: 18
   - 平均复杂度: 16.1
   - 最复杂函数: handle_packet() 复杂度 45

2. parser.c
   - 总复杂度: 213
   - 函数数: 12
   - 平均复杂度: 17.8
   - 最复杂函数: parse_expression() 复杂度 38

3. scheduler.c
   - 总复杂度: 167
   - 函数数: 15
   - 平均复杂度: 11.1
```

**解决方案：**

#### 热点1: network_stack.c 拆分

```c
// 拆分前：network_stack.c (289复杂度)

// 拆分后：
network_tcp.c (复杂度: 95)
  - TCP相关函数

network_udp.c (复杂度: 87)
  - UDP相关函数

network_common.c (复杂度: 45)
  - 公共工具函数

network_buffer.c (复杂度: 62)
  - 缓冲区管理

总复杂度不变，但每个文件可维护性提升
```

#### 热点2: parser.c 简化复杂函数

```c
// 修改前：parse_expression() 复杂度 38
int parse_expression() {
    if (...) {
        if (...) {
            while (...) {
                if (...) {
                    switch (...) {
                        // 大量嵌套逻辑
                    }
                }
            }
        }
    }
}

// 修改后：拆分为小函数
int parse_expression() {
    Token* token = get_next_token();

    if (is_binary_op(token)) {
        return parse_binary_expression(token);
    }
    if (is_unary_op(token)) {
        return parse_unary_expression(token);
    }
    return parse_primary_expression(token);
}

// parse_binary_expression() 复杂度: 8
// parse_unary_expression() 复杂度: 5
// parse_primary_expression() 复杂度: 6
// 总复杂度: 19 (降低了50%)
```

### 重构前后对比

```
重构前：
==================
循环依赖: 3 个
层级: 8 层
热点文件: 12 个（复杂度 > 100）
平均复杂度: 9.8
DSM三角度: 45%

重构后：
==================
循环依赖: 0 个 ✅
层级: 6 层 ✅
热点文件: 3 个（复杂度 > 100）✅
平均复杂度: 7.2 ✅
DSM三角度: 78% ✅

改善：
- 消除了所有循环依赖
- 简化了层级结构
- 降低了75%的热点文件
- 整体复杂度降低26%
- 架构清晰度提升73%
```

---

## 最佳实践

### 1. 定期架构检查

建议频率：
- **每周**：检查新增的循环依赖
- **每月**：分析热点文件变化
- **每季度**：完整的架构评估

### 2. 设定架构目标

```
项目架构KPI：
==================
□ 循环依赖数量: 0
□ 平均复杂度: < 8
□ 最大复杂度: < 20
□ DSM三角度: > 70%
□ 层级深度: 4-6 层
```

### 3. Code Review检查点

```
代码审查时检查：
==================
□ 新增的#include是否引入循环依赖？
□ 新增函数的圈复杂度是否 < 10？
□ 是否遵循现有的分层结构？
□ 是否有跨层依赖？
```

### 4. 重构优先级

```
优先级排序：
==================
P0 (立即处理):
  - 循环依赖
  - 复杂度 > 20 的函数

P1 (本月处理):
  - 复杂度 15-20 的函数
  - 跨3层以上的依赖

P2 (本季度处理):
  - 复杂度 10-15 的函数
  - DSM优化

P3 (技术债务):
  - 代码风格统一
  - 文档完善
```

### 5. 工具使用建议

```
日常开发流程：
==================
1. 开发新功能前
   → 查看 Levelization，确定应该在哪一层

2. 添加新文件时
   → 检查 DSM，确保不引入循环

3. 修改现有文件后
   → 查看 Hotspots，确保复杂度不增加

4. 提交代码前
   → 运行完整架构分析，确保没有破坏架构
```

### 6. 团队协作

```
角色分工：
==================
架构师：
  - 每月审查架构分析报告
  - 制定重构计划
  - 设定架构标准

Tech Lead：
  - 每周检查新增的架构违规
  - Code Review时关注架构问题
  - 协调重构任务

开发人员：
  - 编码前查看分层结构
  - 遵循架构标准
  - 及时报告发现的架构问题
```

---

## 工具总结

| 工具 | 主要作用 | 关键指标 | 使用时机 |
|------|---------|---------|---------|
| **DSM Matrix** | 可视化依赖关系 | 红色单元格、三角度、数值分布 | 评估整体架构质量 |
| **Circular Dependencies** | 发现循环依赖 | 循环数量、环的大小 | 重构前的必查项 |
| **Levelization** | 评估分层质量 | 层数、分布、跨层依赖 | 设计新模块时参考 |
| **Hotspots** | 识别重构目标 | 复杂度、函数数量 | 制定重构计划 |

### 组合使用的价值

```
单独使用：
- DSM → 知道"哪里有问题"
- Circular → 知道"什么问题"
- Levelization → 知道"结构是否合理"
- Hotspots → 知道"优先修什么"

组合使用：
→ 从"迷失在代码细节中"
→ 到"站在架构全局视角做决策"
→ 从"救火式修bug"
→ 到"主动式架构优化"
```

---

## 附录：常见问题

### Q1: DSM中数字很大（>10）正常吗？

**A:** 通常不正常。数字表示 `#include` 的次数：
- 1-2：正常
- 3-5：可能有重复包含，检查是否需要
- >5：不正常，可能是：
  - 同一个头文件被多次包含（检查头文件保护）
  - 应该使用前向声明而不是 `#include`

### Q2: 为什么我的项目没有Layer 0？

**A:** 所有文件都可能处于循环依赖中：
```
如果所有文件都在循环依赖中，则没有文件可以是Layer 0
→ 必须先打破循环依赖
```

### Q3: 复杂度多少算高？

**A:** 参考标准：
```
函数级别：
- < 10: ✅ 优秀
- 10-15: ⚠️ 可接受
- > 15: ❌ 需要重构

文件级别（平均复杂度）：
- < 8: ✅ 优秀
- 8-12: ⚠️ 可接受
- > 12: ❌ 需要重构
```

### Q4: 如何降低圈复杂度？

**A:** 常用方法：
1. **提取函数** - 将复杂逻辑拆分为小函数
2. **表驱动** - 用查找表替代复杂的 if-else/switch
3. **策略模式** - 用函数指针替代复杂分支
4. **简化条件** - 提取条件判断为布尔函数

### Q5: 循环依赖一定要解决吗？

**A:** 是的，必须解决。循环依赖是架构腐化的标志：
- 短期：可能编译通过
- 中期：增加维护难度
- 长期：导致代码无法理解和测试

---

## 相关文档

- [CLAUDE.md](./CLAUDE.md) - 项目开发指南
- [architecture.md](./docs/architecture.md) - 项目架构设计（中文）
- [IMPLEMENTATION_SUMMARY.md](./IMPLEMENTATION_SUMMARY.md) - 实现细节

---

**文档版本：** 1.0
**最后更新：** 2025-12-04
**适用版本：** CodeUnderstand v1.0+
