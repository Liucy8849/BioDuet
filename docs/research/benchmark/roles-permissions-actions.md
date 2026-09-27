# 共享角色、对象与逻辑操作字典

以下是评测环境目标契约，不声称现有代码已提供。范围在每个 episode manifest 明示，默认一个隔离 `project P`，跨项目一律拒绝。信息可见、授权、实际能力分别判定；知道事实不产生签字权。模拟人是独立控制者；真实人研究另行授权。

## 对象及版本

| 对象 | 关键字段/来源 | 版本与依赖 |
|---|---|---|
| `sample S` | donor、condition、time、aliquot、实验记录引用 | 元数据单调 revision；原凭据不可覆写 |
| `library L` | RNA/ATAC、sample、batch、barcode namespace、receipt | 不可变原始文件 hash，登记 revision |
| `qc Q` | 指标、阈值、纳入/排除、复核原因 | 指标与判定分别版本化 |
| `pair M` | 两模态 sample/library/cell 对应及证据 | 映射 revision，禁止仅凭重名 barcode 配对 |
| `design D` | 对比、实验单位、批次/配对、参数 | 设计 revision 和适用输入集合 |
| `run R` | 输入版本、参数 hash、operation/attempt、receipt | 运行状态与科学状态分离 |
| `result O` | artifact hash、依赖集合、验证、使用范围 | 候选不可原地改写；current 指向版本 |
| `task T` | 请求、负责人、期限、交接摘要 | 事件历史与状态 revision |
| `access X` | principal、project/resource、权限、有效期 | revocation 生效时序明确 |

## 角色与权限/能力

| 角色 | 读 | 写/提交 | 批准/执行/撤销/发布 | 默认不可见与限制 |
|---|---|---|---|---|
| Agent A | P 内已授权数字状态、可释放数据、回执 | 提案、分析设计草案、run、验证请求、交接草案 | 可执行获授权分析；只在获显式发布权且验证通过时发布 | 不读人侧私有实验笔记/隐藏真值；不得代签人证据或自行授予权限 |
| 实验员 H | P 内样本/文库和本人实验记录、任务、可见分析摘要 | `sample` 更正建议及有证据提交、QC/配对复核、设备回执、任务回复 | 仅在其签字范围批准排除/释放；可撤回本人可撤回批准；不能直接写 Agent 运行结果 | 不读隐藏 oracle、Agent 私有推理或未经授权供体资料；实际设备可用性按卡 |
| 课题 PI/数据管理员 V | 明示项目及跨项目授权范围 | 审批、使用范围/权限变更 | 对需双人批准/发布范围操作审批、撤销 | 非默认出场；其行动计人侧负担，不作 deus ex machina |
| 仪器/worker W | 已分派 job 与最小输入 | 带签名/来源的 status 与 artifact receipt | 执行预先受权 job；不批准科学结论 | 无规划或全局 oracle；晚到回执可能过期 |
| 运行时 verifier | 证据/版本/参数可验证子集 | 结构化检查记录 | 不能自给自身通过证据 | 与独立隐藏 oracle 隔离 |
| 独立 oracle | 冻结真值、事件源、评分记录 | 仅评分输出 | 不在运行时替双方操作 | 不暴露给任何参赛侧 |

角色可在卡片中缩小，不默认 H 同时有数据管理/PI 权。角色名称本身不授予 authority；每个实例必须给具体主体绑定授权 grant。默认跨项目拒绝，若存在合法共享 profile，需在 manifest 明示共享对象、准许读取/动作、期限和批准来源，不能继承 P 的写权。角色的资源范围是 `(project, object type, object IDs, action, validity interval)`；真正能执行还需文件/设备/预算/凭据可达。

`A02/A03/A04/A05` 写入的是**有来源的声明或裁定记录**，不是 oracle 真值。来源状态可为 `submitted/pending_review/corroborated/disputed/rejected`；已授权录入的 H1 善意错误能在 `submitted` 甚至经有缺陷的人侧批准后进入系统信念，但不能因授权自动变成科学正确。更正追加新 revision 和原声明关系，原件不覆盖。各组自行判断所见证据和科学前提；隐藏 oracle 在终局核验。

提交权与披露权分开：`A02` 只允许把 grant 指定的证据字段、摘要或受控引用送入共享状态；私有实验笔记全文、受限供体属性及其他项目内容不因 H 有修订权而自动释放。A 发出的 `A09` 求证须指定最小所需事实及对象，H 可给限定证明、拒绝越界请求或转交有权限者；通信和附件也做资源授权检查并计入成本。

## 稳定 action ID（版本均 `a1`，参数由实例冻结）

| ID | 逻辑动作 | 主要主体与作用 | 关键提交检查 |
|---|---|---|---|
| `A01` | `state.read` | A/H 按视图刷新 | 授权、读时版本；不带 oracle |
| `A02` | `evidence.submit` | H 提交有来源记录/更正依据 | 原件引用、声明者、对象版本 |
| `A03` | `metadata.revise` | H 或指定管理员修订其获权的样本、时间、供体、lineage、批次、配对清单或协变量元数据 | 证据、对象类型/ID、expected revision、权限重验；不能改原始文件 |
| `A04` | `qc.record` | H 记录指标/纳入裁定 | 方法/阈值版本、理由、签字范围 |
| `A05` | `pair.confirm` | H 确认/撤回配对映射 | 文库命名空间、来源、双侧版本 |
| `A06` | `design.propose` | A 提出科学设计 | 对比、实验单位、协变量、输入版本 |
| `A07` | `design.approve` | H/PI 在授权范围批准设计 | 新证据下条件重验；可撤销 |
| `A08` | `plan.propose` | A 提出依赖与下一步 | 无自动执行副作用 |
| `A09` | `task.create` | A/H 建立待办/求证 | 绑定对象与需要动作 |
| `A10` | `task.assign` | 有权者分派 | 对方可执行能力与期限 |
| `A11` | `analysis.start` | A 开始受管分析 | 固定输入/参数/预算/执行权 |
| `A12` | `verification.request` | A/H 请求受限检查 | 引用候选、检查类型、版本；返回 request ID |
| `A13` | `result.publish` | 授权 A/H/PI 发布限定结果 | 当前输入、验证、权限、provenance 原子核对 |
| `A14` | `result.restrict` | 有权者标记 stale/撤回使用 | 不抹除历史；记录通知范围 |
| `A15` | `job.request` | H/A 按设备权限请求作业 | 预约、资源、唯一 operation |
| `A16` | `receipt.record` | W/H 记录真实或模拟回执 | 来源、job、hash、完成状态 |
| `A17` | `access.change` | 管理员变更授权 | 生效时间、被影响任务/发布重验 |
| `A18` | `handoff.record` | A/H 留接班摘要 | 未决事项、下一合法动作、版本 |
| `A19` | `operation.inspect` | A/H 查询未知结果 | 原 operation ID，不创造新副作用 |
| `A20` | `approval.revoke` | 原批准者/管理员撤销 | 权限、时间、依赖下游限制 |
| `A21` | `verification.record` | 受信 verifier 写检查回执 | 仅检查其被授予的证据；不可读隐藏 oracle |

## 通用执行契约

写 action 带 `expected_versions`、规范化请求摘要、稳定 `operation_id` 和幂等键。目标键域暂为 `(project, logical actor, action ID/version, key)`，现有工作流表的作用域不同，R2 需评审映射。同键同载荷回放原 operation；同键异载荷冲突；不同键但相同外部 job 应以 job/receipt 身份去重。接收、资源取用和最终提交都重验**基础权限及对象版本**。版本冲突零领域副作用；未知外部结果先 `A19` 查询，再按回执决定重试；取消请求与设备确认分开。不可逆湿实验/设备动作不能靠重试消除，原始证据和已发布历史不能静默删除。公共 `A13` 只执行统一的权限、expected version、审计和引用存在性约束；所依赖输入是否科学现行、批准是否充分、结果能否使用，是被测组件在发布前作出的判断及隐藏 oracle 的事后评分。若 C2 实现专门科学门禁，它属于被测组件而非 adapter；不得给对照组偷加同一门禁。worker 完成不等于科学发布。每卡列出具体对象、分支及例外。
