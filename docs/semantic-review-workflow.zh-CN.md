# Kimi K3 源义分析与 DeepSeek V4 Pro 独立复核

这套流程把“理解中文”和“写好英文”分成可审计的阶段。暂定由 Kimi K3
生成盲态中文源义框架，DeepSeek V4 Pro 独立复核中英准确性，最终英文始终由
英文成文角色负责。厂商分工不是预设结论；`semantic-model-benchmark.py` 会用同一
金标决定每条轨道的候选模型，结果相反时可以交换角色。

外部模型只分析或审核，不生成、改写或决定最终英文。因此，本流程不改变“Agent
本身是译者、禁止外部翻译 API”的原则。

## 1. 先声明来源、交付形态和隐私政策

`translation-project.yaml` 增加三个字段：

```json
{
  "source_origin": "oral_talk",
  "delivery_format": "publication_book",
  "external_semantic_review": "allow"
}
```

- `source_origin`：`oral_talk | written_text | mixed | unknown`；
- `delivery_format`：`publication_article | publication_book | transcript |
  subtitles | audio_script | guided_practice | other`；
- `external_semantic_review`：`allow | deny`，省略时兼容旧项目并按 `allow`
  处理。

来源和交付形态不能混为一谈。开示整理成文章或书籍后，英文采用温和、克制、清楚的
出版书面语：通常不用非引语缩写、俚语、聊天填充词或随意残句，同时保留法师原有的
第一人称、反问、推理层次、朴素比喻和温和语气。只有逐字稿、字幕、保留问答对话的
稿件和音频脚本才使用明显口语特征。`publication_article` 和
`publication_book` 不能配置 `register.formality: conversational`。

`release.level: sensitive` 总是等效于 `external_semantic_review: deny`。
此时两个外部阶段必须换成互相独立的内部角色，产物中的 `provider` 写为
`internal`，仍须保持相同的信息隔离、Schema 和哈希记录。

## 2. 凭据

脚本只按以下顺序读取凭据：

| 服务 | 环境变量 | macOS Keychain service | 模型与接口 |
|---|---|---|---|
| Kimi 中国区 | `KIMI_API_KEY` | `mpi-kimi-review` | `kimi-k3`，`https://api.moonshot.cn/v1` |
| DeepSeek | `DEEPSEEK_API_KEY` | `mpi-deepseek-review` | `deepseek-v4-pro`，`https://api.deepseek.com` |

Keychain account 使用当前 macOS 用户。建议通过“钥匙串访问”添加 generic password，
避免把密钥字面值写进命令、shell 历史或配置文件。两个脚本及评测脚本均拒绝命令行
key，不打印凭据，不写入仓库，也不回显可能带有原稿或请求内容的 API 错误正文。

曾出现在聊天、日志或截图中的 key 已经公开。它可以用于无保密要求的短期测试，但在
处理任何非公开稿件前必须撤销并轮换；仅仅把同一 key 放进 Keychain 不能恢复其保密性。

## 3. 四阶段执行

### 阶段一：全文内部审义 + K3 疑难段落升级

生产默认不再要求 K3 逐段分析全文。先由能够遵守同一 Schema、证据和盲态约束的
内部中文审义角色覆盖全文，生成 canonical `source-analysis.json`；再从中选择确有
歧义或被人工点名的段落交给 K3。这样保留 K3 在省略主语、语义角色、逻辑关系和
作用域上的价值，同时避免把标题、元数据和简单直陈句也逐段送入慢速深度推理。

选择器只依据完整且哈希新鲜的中文源义分析，不读取英文稿或译后 findings：

```sh
python3 scripts/select-kimi-focus.py /absolute/project-dir
python3 scripts/select-kimi-focus.py /absolute/project-dir --format args
```

默认升级条件是：`status: needs_human`、竞争解释，或角色、关系、作用域、指代/省略
被标为 `ambiguous`。译者或审校者发现另一处复杂命题时，可用
`--include L201` 人工升级；脚本不会仅凭句长或标点自动把大量普通长句判成疑难。

将第二条命令输出的重复参数传给 K3，例如：

```sh
python3 scripts/kimi-source-analysis.py /absolute/project-dir \
  --paragraph-id L51 --paragraph-id L57 --paragraph-id L147 \
  --timeout 600 --retries 1
```

聚焦模式默认写 `source-analysis-kimi-focused.json`。它仍提供完整中文全文作为只读
上下文，但只生成指定段落；脚本禁止它覆盖 canonical `source-analysis.json`。英文成文
角色可以同时读取完整的 canonical 分析与这份聚焦意见。两者冲突时保留双方记录并转
人工裁决，不自动合并，也不以多数票决定。严格发布门禁仍要求 canonical 分析完整覆盖
全文，因此部分 K3 结果无法冒充全文源义分析。

以下全文 K3 方式保留给金标对比、模型录用测试，或没有合格内部全文审义角色的项目，
不再作为日常默认：

先做无网络检查：

```sh
python3 scripts/kimi-source-analysis.py /absolute/project-dir --dry-run
```

全文正式运行：

```sh
python3 scripts/kimi-source-analysis.py /absolute/project-dir
```

脚本的文件读取白名单只有：

- `source.dj`；
- `translation-project.yaml`；
- `term-map.yaml`。

它不打开、不探测 `target.dj`。无论是全文还是聚焦模式，每批只要求分析指定段落，
但请求中提供带行号的完整
中文全文，以保留跨段指代；各批严格串行。生产默认 `reasoning_effort: high`，这是
因为现有实测中并发 `max` 三次均在 240 秒超时，而串行 `high` 成功。`max` 只用于
疑难段落仲裁或单独性能测试：

```sh
python3 scripts/kimi-source-analysis.py /absolute/project-dir \
  --reasoning-effort max --batch-size 1
```

K3 使用 `response_format.type: json_schema`、`strict: true`，输出上限参数使用当前
接口的 `max_completion_tokens`，不使用已弃用的 `max_tokens`。Schema 遵循提供商
支持的 MFJS 子集：网络请求中只保留 MFJS 明确支持的关键词，长度、数量、
原文证据等更严格约束仍由本地完整 Schema 校验。本地会再次检查类型、枚举、原文证据、空角色与
`evidence_status` 的一致性、段落覆盖率和顺序。全部批次通过后才原子替换
`source-analysis.json`。任何超时、空输出、截断、Schema 错误或覆盖缺失都会保留旧文件。
运行默认为单段、单路串行；每批验证后原子写入可恢复检查点，失败时只重新生成该批，
不修补、不剥离 Markdown 围栏、不将坏输出回喂给模型。

《出家与解脱》的实测中，K3 在约 64 分钟内完成 36/108 段，折合约 107 秒/完成段，
按该速度全文约需 3.2 小时；完整内部分析最终只标出 7/108 段需要保留歧义。聚焦路由
因此把 K3 调用量从 108 段降到 7 段（约减少 94%），估算约 12--15 分钟。这个数字是
本篇实测外推，不是供应商延迟承诺；生产仍记录实际耗时、超时和重试。

### Tier 1 限速策略

当前中国区 Tier 1 帐户按官方表执行：账户并发 50、200 RPM、2,000,000 TPM，TPD 不限。
[官方等级与限额表](https://platform.kimi.com/docs/pricing/limits)；
[官方限流计算说明](https://platform.kimi.com/docs/introduction)。
项目脚本进一步把有效并发固定为 1，并以“请求输入的 UTF-8 字节上界 +
`max_completion_tokens`”作为保守的每分钟预留量；在进程内达到 RPM 或 TPM 前自动等待。
对 429 仅使用数值且最多 60 秒的 `Retry-After`，否则采用有界指数退避；不读取、
不回显供应商错误正文。限速按用户而非 API key 计算，并在各模型间共享。

对当前的单篇文章串行分析，Tier 1 的并发、RPM 和 TPM 均不是瓶颈；升级 Tier
不会缩短单次 K3 深度推理时间，也不会消除结构化输出偶发违约。只有在多项目并行、
持续出现 `rate_limit_reached_error` 且本地调度仍不足时，才建议提升级别。
Tier 2 虽将账户并发、RPM、TPM 分别提高到 100、500、3,000,000，但对本流程固定的
单并发没有实际加速；不得把 `engine_overloaded` 或单次超时误判为账户等级不足
（见[官方错误说明](https://platform.kimi.com/docs/api/errors)）。

### Qwen3.8-Max 备用源义分析

当 K3 在同一段达到重试上限、或单篇总运行时间超过项目预算时，可改用
`scripts/qwen-source-analysis.py` 从头独立分析。本项目试验使用账户可调用的
`qwen3.8-max`；官方模型页也列出该精确 ID，但中国区推荐的 OpenAI 兼容
Base URL 包含账户的 `WorkspaceId`。因此在生产启用前，仍必须以该账户实际工作区、
套餐和端点重新验证，不得只凭模型 ID 就启用自动切换。凭据按项目约定从
`DASHSCOPE_API_KEY` 再到当前用户 Keychain service `mpi-qwen-review` 读取。
端点不再使用通用 DashScope 地址，也不提供隐式默认值。脚本先读取项目约定的
`QWEN_BASE_URL`；未设置时，才读取 `QWEN_WORKSPACE_ID` 并构造：

```text
https://{WorkspaceId}.cn-beijing.maas.aliyuncs.com/compatible-mode/v1
```

两者都未设置时直接失败。无论端点来自哪一项环境变量，本地都会在读取凭据前强制校验：
必须是 HTTPS，不得含用户信息、查询或片段，只允许默认 443 端口和固定
`/compatible-mode/v1` 路径，主机必须精确匹配单一、合法 Workspace DNS label 加
`.cn-beijing.maas.aliyuncs.com`。通用 `dashscope.aliyuncs.com`、其他地域、额外子域、
重定向式或任意第三方主机均被拒绝，避免把 Bearer 凭据发往非预期端点。API Key 与
Workspace 必须属于同一中国区账户；不得在失败后盲目跨区重试。

Base URL、Workspace ID 和 API key 均不接受命令行参数。可先运行 `--dry-run` 验证
中文侧输入、批次、模型、端点来源类别和已校验 host；dry-run 不读取 Keychain/环境
变量中的 key、不输出任何凭据，也不发网络请求。
Qwen 只读取与 K3 相同的三份中文侧输入，不读取 K3 检查点、英文稿或旧译；默认写入
`source-analysis-qwen.json`，整篇验证通过后才可单独晋升为 canonical artifact，禁止将
K3 与 Qwen 的段落拼接成一个不透明的混合结果。Qwen3.8-Max 系列按百炼官方能力使用
`json_object`，关闭 thinking 且不发送 completion token cap；服务端不宣称执行任意严格
JSON Schema，因而必须由本地完整 Schema、原文证据、覆盖与哈希门禁拒绝非法结果，
不得静默修复。
[百炼模型列表](https://help.aliyun.com/zh/model-studio/models)；
[百炼结构化输出（JSON Mode）](https://help.aliyun.com/zh/model-studio/qwen-structured-output)。

分析包含谓词、参与者与角色、分句关系、时体/情态/否定/数量/程度作用域、指代与
省略、竞争解释以及 `must_preserve`、`must_not_invent`。未知参与者允许 `null`；
只要尚有歧义，该段必须是 `needs_human`，不能为了填满 Schema 而虚构角色。

### 阶段二：英文模型成文

英文成文角色读取中文、冻结术语表和源文哈希一致的 `source-analysis.json`。分析是
意义约束，不是英文初稿。英文模型可以为自然表达改变语法主语或主动/被动语态，但
必须保留施事、体验者、受事等语义角色及其“明示/推断/歧义”状态。不得把省略角色
擅自补成 `we`、`people` 或任何确定主体。

成文及后续书面化只在 Agent 内完成，不调用 Kimi 或 DeepSeek 生成英文。

### 阶段三：V4 Pro 独立准确性复核

先检查请求隔离和凭据来源：

```sh
python3 scripts/deepseek-review.py /absolute/project-dir --dry-run
```

正式复核：

```sh
python3 scripts/deepseek-review.py /absolute/project-dir
```

V4 Pro 的读取白名单只有 `source.dj`、`target.dj`、`term-map.yaml` 和
`translation-project.yaml`；它不读取也不发送 `source-analysis.json`。提示词要求
独立检查谓词、语义角色、逻辑关系、作用域、时体、情态、遗漏、增加、术语及经文
错义，只输出中文 findings 和“意义修正约束”，不提供最终英文替换句，也不做通用
英文润色。

为避免整篇一次调用在长文中漏掉局部重大问题，脚本默认把非空段落分成每批 20 段的
聚焦请求；每批另带前后各一段只读上下文以消解指代。每个段落恰好在一批中可报告，
模型若对上下文段落生成 finding 会被本地拒绝。所有批次全部通过后才统一校验、合并并
原子写入历史和证书；任一批超时、非法或失败时，本轮不写任何结果。`--batch-size` 可在
1–50 内调整，但正式对比必须固定同一批大小。

标准 DeepSeek JSON Output 只保证 JSON 语法，不保证任意 JSON Schema。脚本因此会
拒绝空输出、截断、未知字段、错误枚举、无效段落 ID、非中文说明或不符合本地接口的
内容，不作静默修复。

验证后的记录由本地补入 `stage`、`provider`、`model`、`source_sha256` 和
`target_sha256`，再按稳定 `finding_id` 原子合并进 `review-findings.jsonl`：

- 既有字节和历史记录保留；
- 同 ID、同记录视为幂等重试；
- 同 ID、不同记录在落盘前失败；
- 默认行为绝不覆盖整份 findings 历史。

同时生成 `semantic-review.json`，记录本轮、源/译文/findings 哈希、全部历史中尚未
解决的 critical/major 数、具体 `blocking_finding_ids` 和状态。脚本始终合并到项目内
唯一的 `review-findings.jsonl`，拒绝自定义路径造成历史分叉。单个文件均原子替换；若
进程在两文件之间中断，严格门禁会因证书缺失或哈希过期而失败，不会错误放行。

### 阶段四：准确性修订、书面化与终检

英文模型先处理已确认的意义约束，并把相应 finding 更新为 `resolved`、`rejected` 或
经人工决定的其他状态，保留 `resolution_note`；随后按 `delivery_format` 一次性完成
书面化。不得为追求流畅重新改变已冻结的谓词、角色、逻辑或作用域。

润色后再次运行 `deepseek-review.py`。严格公开/敏感发布要求：

- `semantic-review.json.review_round >= 2`；
- `status: clear` 且 `blocking_findings: 0`；
- 证书中的 source、target 和 findings SHA-256 与当前文件逐字节一致。

第一个 blocking 复核周期后由英文 Agent 修订；下一个连续复核周期仍有 blocker 时，证书写为 `needs_human`。历史绝对轮次仍继续递增，但早先的 `clear` 不得被误算为一次失败修订。只要这些 blocker 仍是 `open` 或
`deferred`，脚本会在读取凭据和联网前拒绝第三次自动循环。人工必须保留证书列出的每个
具体 finding，将其设为 `resolved` 或 `rejected` 并写明非空 `resolution_note`；删除记录、
替换成另一条已解决问题或降低严重度都不能绕过门禁。完成后才允许最终复核。K3 与 V4
Pro 的意见冲突时保留双方证据，交人工裁决；不使用模型多数票。

## 4. 门禁

```sh
python3 scripts/check-translation.py /absolute/project-dir --strict --json \
  --output /absolute/project-dir/qa-report.json
```

门禁会验证：

- 出版交付形态没有误设成 conversational；
- findings 的可选溯源字段和 SHA-256 格式；
- `semantic-review.json` 的状态、轮次、finding IDs、全历史 blocker 数及精确 blocker IDs；
- source、target、findings 三个哈希的新鲜度；
- sensitive/deny 项目的分析、复核证书及带溯源信息的 findings，其 `provider`
  必须为 `internal`；
- public/sensitive 的 strict 发布必须有完整、符合 Schema 的
  `source-analysis.json`；其源文、项目元数据、术语表三个哈希以及非空段落覆盖和
  顺序都必须与当前冻结输入一致。草稿模式若存在该文件，也会执行这些完整性检查。

草稿模式不因缺少最终证书而阻断；public/sensitive 的 strict 模式要求终检证书。
机械门禁仍不能替代佛法义理和冲突解释的具名人工批准。

## 5. 同一金标双轨对比

公开金标在 `tests/fixtures/semantic-gold.json`，另有完整结构样例
`tests/fixtures/kimi-source-analysis/food-for-livelihood.json`。永久案例：

> 仅仅为了得到谋生的食粮，就有多少生命在忍受痛苦，甚至丧生。

金标要求：`得到` 的受事是“谋生的食粮”；获取者为 `null/ambiguous`；“多少生命”
是忍受痛苦者并承前成为丧生者；保留目的/代价和递进；不得补 `had to`、`could`
或确定过去时，也不得强制认定获取者与受苦生命同指或补成“人们”。

显式提供两家凭据后，运行每轨每模型三次的串行实测：

```sh
python3 scripts/semantic-model-benchmark.py \
  --live --runs 3 --timeout 300 \
  --output /tmp/semantic-model-benchmark.json
```

这会产生 2 条轨道 × 2 个模型 × 3 次，共 12 次请求，可能耗时且产生费用。常规 CI
不运行 live 模式。源义轨道中两个模型只看同一中文案例、提示和规范化 Schema；译后
轨道只看同一中英案例及元数据，均不看另一模型的输出。Kimi 用严格 JSON Schema，
DeepSeek 用 JSON object 后本地按同一规范校验。

报告计算谓词、角色、逻辑/作用域、歧义保留率、critical/major 召回、控制例误报、
字段级三次一致率、未经修复的 Schema 合法率、超时率和中位/最大延迟。若另行提供
当日核验的费率 JSON，还会按响应 usage 估算成本；脚本不内置易过期价格。

录用先过硬门槛：源义轨道不得把歧义伪装成明示事实；复核轨道先满足 blocker 召回和
控制例误报要求；非法 Schema 和超时按失败计。两家都不过门槛或排序指标完全并列时
selection 为 `null`，不按厂商顺序武断录用。评分报告只是暂定模型分工证据，人工仍需
检查金标和误报类型。

K3 的 1M 上下文、思考模式和 Structured Output 细节见
[K3 快速开始](https://platform.kimi.com/docs/guide/kimi-k3-quickstart) 与
[结构化输出](https://platform.kimi.com/docs/guide/response_format)。DeepSeek 的模型与
JSON 模式限制见[模型说明](https://api-docs.deepseek.com/quick_start/pricing/) 与
[JSON Output](https://api-docs.deepseek.com/guides/json_mode/)。
