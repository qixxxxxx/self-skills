# Slot 原版数值对齐：大白话首页

这个 Skill 做的事情可以概括成一句话：

> 先弄清楚原版游戏到底怎么玩，再决定应该对齐哪些数据，最后用独立样本证明候选游戏真的对齐了。

## 一眼看懂完整流程

```text
原版规则、协议、Runtime、服务端、模拟脚本
                ↓
提取玩法事实：盘面怎么生成、怎么中奖、怎么触发Feature
                ↓
匹配标准玩法画像：这到底属于Ways、Cascade、Free Spin还是其他玩法
                ↓
根据画像加载指标包：这类玩法应该检查哪些数据
                ↓
根据具体属性筛选指标：只保留这个游戏真正适用的指标
                ↓
按Base、Feature、状态和盘面阶段展开指标实例
                ↓
去除重复指标，确定每个数据的唯一Owner
                ↓
从原版样本生成目标，密封容差、权重和样本计划
                ↓
测量当前候选，诊断差距并只调整获准的数值参数
                ↓
使用独立FORMAL样本验收
                ↓
生成机器结果、中文报告和最终Runtime
```

## 四个最重要的概念

### 1. 玩法事实

玩法事实是从规格、原版协议、Runtime和实现中直接确认的规则，例如：

```text
盘面有6个轴。
每个轴显示高度会变化。
中奖后会清除符号并继续补充。
4个BONUS触发免费旋转。
```

事实必须有证据，不能看到游戏名字后自行猜测。

### 2. 玩法画像

玩法画像是把游戏事实翻译成统一的标准语义。例如：

```text
动态轴高     → board.variable-grid
Ways中奖     → settlement.ways
中奖后补位   → evolution.cascade
免费旋转     → feature.free-spin
```

标准画像定义在[玩法画像](references/玩法画像/)目录。

### 3. 指标包

指标包是一组专门检查某类玩法的数据。例如：

```text
board.variable-grid
    → atomic.variable-grid
    → 检查完整轴高布局、容量以及不同容量下的回报
```

指标包和全部指标定义在[指标目录](references/指标目录/)中，中文总览见[指标汇总.md](references/指标目录/指标汇总.md)。

### 4. 指标实例

同一个指标可能需要在不同位置分别统计。例如“单盘符号数量分布”要拆成：

```text
Base初始盘
Base Cascade补位后的完整盘
Free Spin初始盘
Free Spin Cascade补位后的完整盘
```

一个指标实例的唯一身份是：

```text
metric_id + source_node_ids + instance_dimensions
```

拆出多个实例是为了不混样本，但不会因此增加该指标的评分权重。

## 简单示例：Buffalo的可变轴高

### 第一步：看到真实玩法

Buffalo每局有6个轴，各轴显示高度会变化。

### 第二步：建立玩法画像

```json
{
  "node_id": "board.variable",
  "mechanic_id": "board.variable-grid",
  "attributes": {
    "reels": 6,
    "reel_height_variation": true,
    "height_domain_by_reel": "各轴真实可达高度范围"
  }
}
```

大白话：这不是用“Megaways”品牌名匹配，而是明确告诉系统“这是一个轴高会变化的盘面”。

### 第三步：画像找到指标包

```text
board.variable-grid
    ├── atomic.board-diversity
    └── atomic.variable-grid
```

前者检查盘面符号是否过于重复，后者检查可变轴高本身。

### 第四步：指标包筛选具体指标

`variable_grid.reel_height_layout_distribution`要求：

```text
存在board.variable-grid画像
reels已经定义
height_domain_by_reel已经定义
reel_height_variation=true
```

Buffalo全部满足，因此加载“完整轴高布局模式分布”。

### 第五步：展开实际作用域

```text
指标：variable_grid.reel_height_layout_distribution
来源画像：board.variable
作用域：base × basegame × initial
```

Free Spin和Cascade补位盘会生成各自独立的作用域实例，不能与Base初始盘混在一起。

### 第六步：避免重复评分

轴高布局可以确定性算出几何Ways容量：

```text
[2,3,4,5,3,2] → 2×3×4×5×3×2 = 720 Ways
```

因此：

```text
完整轴高布局分布 → 主评分指标
几何Ways容量分布 → 确定性派生，只作审计阅读
```

同一件事情不能换个名字评分两次。

## 五阶段分别做什么

1. **资料确认与玩法画像**：确认输入、模式、投注口径和玩法事实，生成`game_profile.json`。
2. **指标匹配**：从画像确定性生成指标合同，密封目标、Owner、容差、权重和样本计划。
3. **基线评分**：测量当前候选，先判断硬指标，再计算100分评分并诊断差距。
4. **自动对齐与FORMAL**：只调整已授权参数，冻结候选后用独立样本正式验收。
5. **交付**：封存机器结果、中文报告和Runtime，交付完成即结束流程。

## 最重要的原则

```text
先证明玩法是什么，再决定测什么。
先密封目标和规则，再查看候选结果。
一个语义变量只能有一个评分Owner。
不能用RTP相近代替盘面、中奖构成和玩法过程对齐。
不能为了通过验收修改玩法规则或临时放宽标准。
```

需要执行正式任务时，从[SKILL.md](SKILL.md)开始，并按[阶段1：资料确认与玩法画像](references/01-资料确认与玩法画像.md)进入固定五阶段流程。
