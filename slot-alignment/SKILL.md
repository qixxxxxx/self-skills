---
name: slot-alignment
description: 基于Slot原版样本、Runtime和用户认证Python脚本，建立完整N数值、J中奖结算、P玩法过程、B盘面呈现合同，自动生成候选并执行独立FORMAL对齐和中文交付。用于老虎机原版数值或体验对齐、基线诊断、指标规划、自动调参、候选排序、FORMAL验收及Runtime交付；实现事实源只包含Runtime与用户认证脚本，不验证服务端。
---

# Slot 原版体验对齐 7.0.0

## 目标

在不改变玩法语义的前提下，用原版样本冻结玩家可感知目标，通过Runtime授权参数自动对齐，并交付同一认证脚本独立FORMAL验证过的Runtime、机器结果和中文报告。

## 必读文件

按任务范围读取，不要每次加载无关内容：

| 任务 | 必读文件 |
|---|---|
| 建立画像或指标 | [指标与画像](references/01-指标框架.md) |
| 编译合同或解释评分 | [评价合同](references/02-评价合同.md) |
| 执行对齐或交付 | [轻量执行流程](references/03-执行与报告.md) |
| 创建或校验任务目录 | [工作区结构](references/04-工作区目录结构.md) |
| 规划候选或FORMAL样本 | [样本与执行](references/05-性能与执行预算.md) |
| 规划参数和候选结构 | [调参建议](references/06-调参建议.md) |

机器事实源优先级固定为：政策JSON与指标目录JSON → Schema → 冻结合同 → 脚本结果 → Markdown解释 → 模板。

## 实现事实源

只使用以下两项确定本次可实现能力：

1. 密封Runtime四件套；
2. 用户明确认证的Python脚本。

候选、基线和FORMAL必须调用同一认证脚本核心。优化器只生成Runtime参数，不得重新实现RNG、盘面生成、状态机、Feature或结算。

不读取或验证服务端实现，不建立多层能力矩阵，不证明认证脚本与其他实现一致。Runtime中存在但认证脚本不能读取或执行的字段，本次视为不可调；需要扩展时先取得新的用户认证。

## 参数释放原则

在`parameter_authority`已授权、认证脚本能够正确读取和模拟、且不改变玩法语义的范围内，默认充分释放Runtime调参能力。

优化器可以自行调整参数值、权重、顺序、支持项和配置项数量，也可以增加或删除认证脚本支持的参数项。基线中的数量、顺序、支持项和权重总和只是当前状态，不自动视为约束。

只有用户明确要求、Schema明确限制或认证脚本实际校验的规则，才能作为硬约束。固定总权重、等比例放大、保留全部支持项等计算做法属于搜索方案，不得写成硬约束。

> 核心原则：授权范围内，脚本支持且不改变玩法语义的参数默认放开调整；基线现状不是约束，没有明确依据不得自行增加限制。

### RSPR完整参数包

`Reel Set Profile Routing`（中文：`Reel Set 参数包路由模式`，简称`RSPR`）以`profiles_by_rtp`为识别标志。仅当Runtime使用RSPR且认证脚本按该结构读取时启用：每个`ReelSet × rtp_group`都视为一套完整随机参数包，而不是单独的Reel Strip。优化器动态读取包内全部受支持字段，可以自行新增、删除、克隆、拆分、合并和重新路由参数包，也可以调整包的数量、顺序、支持项、选择权重及包内配置；当前A/B命名、包数量、Reel长度、权重总和和refill层数都不是限制。

一次路由按Runtime声明的选择作用域选中参数包后，该作用域内必须统一使用同一包的全部随机参数，不得在运行中跨包拼接。具体调参顺序、搜索方法和参数包结构由优化器根据冻结合同与候选结果自行决定；Skill不设置额外的扩展门槛。详细规则见[调参建议](references/06-调参建议.md)。

## 红线

- 原版资料、原始样本、密封Runtime和认证脚本只读。
- 只调整`preflight.json.parameter_authority`明确授权的Runtime参数。
- 轴数、盘面几何、符号域、玩法、状态机、触发、结算、RNG调用顺序、投注口径和封顶语义保持不变。
- 原版样本只用于目标、诊断和验收，不得作为候选或FORMAL的出盘数据。
- 每个随机步骤只抽取一次并立即生效。禁止结果导向重抽、拒绝采样、递归搜索、回溯、失败换seed或先定结果再生成。
- 允许按显式权重一次选择认证脚本支持的ReelSet、补符profile或条件类别；选择结果只能路由后续原生分布。
- 画像命中的指标必须在候选前冻结为活动、观察或不适用，候选结果不得改变角色。
- FORMAL使用冻结候选、同一认证脚本和新的独立seed；失败不得换seed重刷。
- 未经用户明确授权，不同步配置、不提交Git、不热更新、不发布。

## 必需输入

从用户输入、项目`AGENTS.md`和当前工作区解析：

```text
directory_map
runtime_environment
python_bin
game_code
game_name_zh
mode
task_id
target_rtp
certified_script
sample_plan
baseline_runtime
parameter_authority
game_profile
```

- Python只使用解析出的`python_bin`；本机默认`/Users/lq/slot_math_env/bin/python`。
- `rtp_group`固定为整数`1`。
- `task_id`缺失时生成`aln-<mode>-<YYYYMMDD>-<NNN>`，创建前确认目录不存在。
- `runtime_version`固定等于`task_id`。
- 唯一`target_rtp`必须由用户提供或明确确认，取值位于`(0,1]`。
- “用户明确确认”只表示目标值无需样本估算；N1仍使用硬门禁政策中的统计容差，不得转成零容差确定性规则。
- 脚本、样本计划、Runtime、调参权限、工作区或画像存在关键歧义时先询问，不自行猜测。

## 四阶段流程

### 1. 开工准备

一次确认认证脚本、样本数、Runtime、调参能力、工作区和游戏画像，密封Runtime四件套并生成`artifacts/preflight.json`。非消除盘面还要确认普通符号及每个特殊符号是否允许同列重复：规格书明确时直接记录，未说明时由用户确认；普通符号默认预选“允许”，但不得跳过确认。

只做最小可运行检查：Runtime可以被认证脚本加载；授权参数可以被脚本读取；固定seed可以完成小样本运行。存在禁止重复规则时，认证脚本输出或只读适配层还必须区分本次Spin/Respin新产生的格子与历史黏住、锁定格子。检查通过记为`READY_FOR_SAMPLES`。

### 2. 样本整理

只读扫描原版样本，统一聚合完整入口数、组件、Feature、结算、连续结算、特色机制和稳定盘面统计，生成`artifacts/source_summary.json`。

默认只保留聚合计数、目标值、证据路径和hash；只有排错时才保存少量事件样本。不得为每个指标拆分独立证据文件。

### 3. 指标与评分合同

使用玩法画像、`source_summary.json`、指标目录和评价政策生成`artifacts/metric_contract.json`，冻结全部N/J/P/B实例、角色、目标、分母、距离、C级通过值、评分和FORMAL样本要求。确认“不允许同列重复”的规则生成B1确定性硬约束，只比较同一次Spin/Respin中新落或替换产生的符号，历史黏住、锁定符号不参与；候选和FORMAL违规率必须为0。确认“允许”时不增加限制。

分布中有低样本档位时，先按玩家含义合并；无法合并时只将该档位和依赖完整分布的整体移动量转为观察，其他证据达标档位仍是活动指标。

合同通过Schema、实例完整性、目标证据和内部hash检查后记为`READY_FOR_ALIGNMENT`。合同冻结后，目标、画像、Runtime基线、认证脚本或参数权限变化会使已有候选失效；Worker和micro-batch等执行细节变化不改变业务合同。

### 4. 自动对齐、FORMAL与交付

先把基线作为`candidate_id=baseline`评价；通过时可直接进入FORMAL，不通过时进行参数敏感性和候选搜索。

候选默认使用`PROBE → SCREEN → REFINE → FINAL`累计阶梯，并按`candidate_batch_size`分批生成。批大小只是单轮工作量，不是候选总上限；没有候选通过FORMAL时必须基于已有账本继续生成不重复的新候选。允许按冻结规则提前淘汰、提前晋级或升级参数面，不要求每个参数层跑满全部档位。普通候选只写入`work/candidate_ledger.jsonl`；只有进入FORMAL的候选才物化完整Runtime。

FORMAL重新运行合同中的全部活动指标，不复用候选统计。默认`10000000/20000000/50000000`只是初始检查点，不是预算上限；达到检查点仍有活动指标样本不足时，必须按冻结规则沿同一候选、同一FORMAL seed序列继续累计，不得停任务、换seed或换候选。样本充分后仍不通过，才返回搜索并选择新的Runtime候选。只有FORMAL通过、授权参数空间按冻结精度穷尽、用户主动停止或技术故障时才能结束搜索。完成后生成：

```text
artifacts/alignment_manifest.json
artifacts/formal_result.json
artifacts/delivery_manifest.json
交付物/runtime/四件套
交付物/报告文档/对齐报告.md
```

授权参数空间按冻结精度确实穷尽仍无通过结果时，交付证据最完整的最优FORMAL失败记录和搜索证据，状态记为`EXHAUSTED_NOT_PASS`。

## 唯一评价规则

每个活动实例只按以下链路判定：

```text
D = 距离(冻结目标, 候选结果)
通过 = D <= C级通过值T
T > 0时，偏差倍数R = D / T
单项分 = max(0, 100 × (1 - R))
```

任一活动实例失败，整体不能通过；高分不能补偿失败项。观察项不参与通过和评分，但必须完整披露。最终状态只允许`通过`、`不通过`或`无法完整判定`。

## 确定性工具

```bash
<python_bin> scripts/validate_metric_library.py
<python_bin> scripts/validate_preflight.py --preflight <preflight.json>
<python_bin> scripts/validate_source_summary.py --summary <source_summary.json>
<python_bin> scripts/compile_metric_contract.py --preflight <preflight.json> --source-summary <source_summary.json> --output <metric_contract.json>
<python_bin> scripts/evaluate_alignment.py --contract <metric_contract.json> --measurements <measurements.json> --phase <BASELINE|CALIBRATION|FORMAL> --output <result.json>
<python_bin> scripts/validate_workspace_layout.py --task-root <任务根目录> --through-stage <1-4>
<python_bin> scripts/validate_delivery.py --task-root <任务根目录>
<python_bin> scripts/render_alignment_report.py --preflight <preflight.json> --contract <metric_contract.json> --result <formal_result.json> --output <对齐报告.md>
```

## 完成条件

- 六份权威JSON、交付Runtime和唯一中文报告存在并通过校验。
- 候选账本逐条绑定用户认证脚本和当前合同；FORMAL绑定同一认证脚本、唯一候选Runtime hash并使用独立seed。
- 候选按批持续生成且参数组合不重复；未通过FORMAL时不得因批次结束或候选数量达到某个固定值而停止。
- FORMAL不设固定样本上限；达到5000万或其他检查点仍样本不足时，必须通过checkpoint沿同一正式seed序列继续累计到可判定。
- 每个正式盘面作用域都有同列重复确认；全部特殊符号逐个覆盖，不允许重复的规则在候选和FORMAL中零违规。
- 全部活动N/J/P/B实例得到S/A/B/C、F或有证据的U；观察项和不适用项完整披露。
- 不存在未解决占位、合同漂移、未授权参数、结果导向重抽或经验盘面出盘。
- 交付Runtime与FORMAL实际使用的Runtime逐文件一致，`rtp_group=1`，版本字段等于`task_id`。
