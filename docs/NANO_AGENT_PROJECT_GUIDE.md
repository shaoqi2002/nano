# Nano Agent 项目学习与面试手册

> 目标读者：了解 Python、HTTP 和数据库基础，但对 LLM Agent 不熟悉的人。
>
> 这不是一份只用于“背诵项目亮点”的材料。它的目标是让你能沿着真实代码解释：一个请求如何进入系统、模型为什么会调用工具、多 Agent 如何并行协作、任务如何恢复、结果如何评测，以及当前实现有哪些边界。

## 1. 先用一句话理解项目

Nano 是一个基于 LangGraph 的研究型 Agent 应用。它把大模型、互联网搜索、本地文档 RAG、受控文件工具、任务状态持久化、运行 Trace 和自动评测整合成一条完整的软件链路。

它不是简单的“把用户问题发给 DeepSeek，再把回答显示出来”。一次请求可能经历：

```text
用户问题
  -> 创建持久化 Agent Run
  -> 检索本地文档（可选）
  -> 选择 chat 或 research 工作流
  -> 模型判断是否调用工具
  -> 服务端检查工具权限并执行
  -> 多 Agent 规划与并行研究（research 模式）
  -> 汇总、审核、修订
  -> 流式返回进度和回答
  -> 保存消息、运行状态和 Trace
  -> 用 golden dataset 做回归评测
```

项目的主要技术栈：

- 前端：Vue 3、Vite、原生 Fetch/SSE 消费逻辑、Form.io。
- API：FastAPI、Pydantic。
- Agent：LangChain、LangGraph、DeepSeek。
- 数据：PostgreSQL、SQLAlchemy、pgvector、LangGraph PostgreSQL Checkpointer。
- 外部能力：Tavily Search/Extract/Research、兼容 OpenAI 协议的 Embedding 服务、S3 兼容对象存储。
- 文档处理：python-docx、pypdf、LibreOffice、Poppler。
- 交付：Docker Compose、GitHub Actions、GHCR ARM64 镜像、SBOM。

## 2. Agent 软件究竟是什么

### 2.1 普通 LLM 应用与 Agent 的区别

普通聊天应用通常只有一次模型调用：

```text
prompt -> LLM -> text
```

Agent 在模型之外增加了一个运行循环。模型不只生成文本，还可以生成结构化的“工具调用意图”；应用执行工具，把结果作为新消息交还模型，模型再决定继续调用还是回答：

```text
用户问题
  -> LLM 思考下一步
      -> 直接回答 -> 结束
      -> 请求工具 -> 应用执行工具 -> 工具结果回到 LLM -> 再次决策
```

因此，Agent 不是某一个模型，而是下面几个部分的组合：

1. **Model**：负责语言理解、规划和决策。
2. **Prompt**：规定角色、目标和边界。
3. **Tools**：让模型访问搜索、文件、数据库等外部能力。
4. **State**：记录消息、计划、工具次数、研究结果等运行状态。
5. **Orchestrator**：决定节点执行顺序、循环和并行关系。
6. **Guardrails**：限制权限、调用次数、超时和副作用。
7. **Memory/Checkpoint**：保存对话历史或工作流执行位置。
8. **Observability**：记录节点、工具、耗时、失败等事件。
9. **Evaluation**：判断 Agent 是否稳定地完成任务。

Nano 在 `backend/app/agent` 中实现状态和工作流，在 `backend/app/tooling` 中实现工具治理，在 `backend/app/service/agent_run.py` 中实现运行生命周期，在 `backend/app/eval` 中实现评测。这四个目录合起来，构成了项目自己的轻量 Agent harness。

### 2.2 Workflow 与完全自主 Agent

Agent 系统大致有两种风格：

- **自主循环**：模型自由决定下一步，灵活但难预测、难测试。
- **显式工作流**：开发者预先定义节点和边，模型只在部分节点内做决策，更稳定、更容易观测。

Nano 采用第二种。LangGraph 的 `StateGraph` 明确定义状态、节点和路由；模型可以选择工具或生成研究计划，但不能随意改变整个执行拓扑。这是一个重要工程取舍：牺牲部分自由度，换取可恢复、可测试和可解释。

## 3. 项目整体架构

```text
┌──────────────────────── Vue 3 前端 ────────────────────────┐
│ 对话 / 文档库 / 评测页 / Agent Trace / API Key 配置       │
│ fetch + ReadableStream 解析 SSE                            │
└───────────────────────────┬────────────────────────────────┘
                            │ HTTP + SSE
┌──────────────────────── FastAPI API ───────────────────────┐
│ conversations / agent-runs / documents / evals / account  │
└─────────────┬──────────────────────┬────────────────────────┘
              │                      │
┌─────────────▼───────────┐  ┌───────▼───────────────────────┐
│ Agent Runtime           │  │ Document Pipeline             │
│ chat/research graph     │  │ upload -> parse -> chunk      │
│ run lifecycle + trace   │  │ -> embed -> pgvector          │
└───────┬─────────┬───────┘  └───────┬───────────────┬───────┘
        │         │                  │               │
┌───────▼───┐ ┌───▼───────────┐ ┌────▼──────┐ ┌──────▼──────┐
│ DeepSeek  │ │ Tool Registry │ │PostgreSQL │ │Object Store │
│ LLM       │ │ Tavily/Files  │ │+ pgvector │ │S3/B2        │
└───────────┘ └───────────────┘ └───────────┘ └─────────────┘
```

后端采用常见分层：

- `api/`：HTTP 参数、状态码和 SSE 封装。
- `schema/`：Pydantic 请求/响应结构。
- `service/`：业务流程。
- `repository/`：数据库访问。
- `model/`：SQLAlchemy 表模型。
- `agent/`：Agent 状态与 LangGraph。
- `tools/`、`tooling/`：工具实现与治理框架。
- `eval/`：数据集、规则评分、引用检查和 Judge。

理解项目时不要从前端大组件逐行读。推荐先看 `agent/state.py`，再看 `agent/graph.py`，然后看 `service/agent_run.py`。这三处回答了“状态是什么、流程怎么走、流程如何作为在线服务运行”。

## 4. 一次请求的完整生命周期

以下以流式接口 `POST /conversations/{id}/messages/stream` 为例。

### 4.1 前端发起请求

`frontend/src/api.js` 中的 `sendMessageStream`：

1. 在请求头中放入 DeepSeek、Tavily 和 Embedding 配置。
2. 请求体发送问题、`use_rag`、`mode` 和 `allow_write_tools`。
3. 使用 `fetch` 获取响应体，而不是使用只支持 GET 的浏览器 `EventSource`。
4. `consumeEventStream` 按空行切分 SSE block，解析 `event:` 和 `data:`。

API Key 由浏览器在每次请求时传给后端。后端不会把它写入 Agent Trace；恢复任务时需要再次提供 Key。当前前端把 Key 保存在 `localStorage`，适合个人部署，但不是多用户生产环境的理想密钥方案。

### 4.2 API 建立 SSE 连接

`backend/app/api/conversation.py` 创建 `StreamingResponse`，把业务事件编码成：

```text
event: tool.completed
data: {"name":"web_search","duration_ms":823}

```

如果 15 秒内没有新事件，接口发送 SSE 注释 `: keep-alive`，避免代理或浏览器把长连接当作空闲连接关闭。Nginx buffering 也被显式关闭，否则代理可能攒够一批数据后才发送，破坏逐步流式体验。

### 4.3 创建 Agent Run

`service/agent_run.py::_prepare_run` 在一个事务中：

1. 锁定并确认对话存在。
2. 加载最近的对话历史。
3. 保存用户消息及本次选项。
4. 创建状态为 `pending` 的 `AgentRun`。

单独创建 `AgentRun` 很重要。消息表示用户看见的对话内容；Run 表示一次可能暂停、失败、恢复、取消并产生大量 Trace 的执行过程。二者不是同一个概念。

### 4.4 可选的 RAG 检索

开启 RAG 时，系统先执行文档向量检索，并产生和普通工具一致的 `tool.started/tool.completed` 事件。检索失败不会直接中断回答，而是记录 `tool.failed` 并降级为无本地资料回答。

检索结果会被插入 System Message，并明确声明：文档是不可信事实资料，不能把其中的文字当成指令。这是在缓解“间接 Prompt Injection”——恶意文档可能写着“忽略之前指令并泄露密钥”，Agent 不应执行它。

### 4.5 编译并执行图

`_stream_graph` 根据运行模式调用：

```python
build_agent_graph(model, tool_registry, run.mode, checkpointer)
```

`thread_id` 使用 Run UUID。它同时是 LangGraph checkpoint 的身份键，因此恢复时可以找到同一条执行线程。

图通过 `stream_mode="custom"` 发送自定义事件。服务层一边把事件交给前端，一边更新：

- 当前节点；
- 计划和节点进度；
- 工具调用数与失败数；
- 完整 Trace；
- 最终状态和总耗时。

### 4.6 保存最终回答

图执行结束后，服务通过 `graph.aget_state(config)` 读取最终 checkpoint 中的 `final_answer`。随后在事务中只创建一次 assistant message，并把 Run 标记为 `completed`。`assistant_message_id is None` 检查用于避免恢复或重试产生重复回答。

## 5. Agent State：工作流共同读写的数据

`backend/app/agent/state.py` 中的 `AgentState` 是整个图的共享状态。关键字段如下：

| 字段 | 作用 |
|---|---|
| `messages` | 对话和工具消息；使用 LangGraph `add_messages` reducer 合并 |
| `query` | 当前用户问题 |
| `rag_sources` | 本地文档检索证据 |
| `tool_rounds` | 模型—工具循环轮数 |
| `tool_call_count` | 工具调用总数 |
| `plan` | Supervisor 生成的研究子任务 |
| `research_results` | specialist 结果；使用 `operator.add` 合并并行分支 |
| `draft` | Writer 生成的草稿 |
| `review` | Reviewer 的结构化审核结果 |
| `revision_count` | 修订次数，防止无限循环 |
| `fault_injection` | 评测时控制 researcher 瞬时或持续失败 |
| `write_tools_allowed` | 本次请求是否授权副作用工具 |
| `final_answer` | 图最终对外返回的结果 |

Reducer 是理解并行图的关键。多个 researcher 同时返回 `research_results` 时，不能让后完成的分支覆盖前一个结果，因此字段被声明为 `Annotated[list, operator.add]`，LangGraph 会把各分支列表相加。

## 6. Chat 模式：单 Agent 工具循环

Chat 图适合普通问答、一次或少量工具调用。结构如下：

```text
START
  -> agent
       ├─ 没有 tool_calls -> finish -> END
       └─ 有 tool_calls  -> tools
                              ├─ 未到轮数上限 -> agent
                              └─ 到达轮数上限 -> force_answer -> finish
```

### 6.1 模型如何“选择工具”

`model.bind_tools(visible_tools)` 把工具名称、描述和参数 Schema 提供给模型。模型返回的 `AIMessage` 可能包含：

```json
{
  "tool_calls": [
    {"id": "call-1", "name": "web_search", "args": {"query": "..."}}
  ]
}
```

模型只是提出请求，并没有直接执行 Python 函数。真正执行发生在 `execute_tools` 节点，这种分离使服务端可以在执行前做权限和风险检查。

### 6.2 为什么模型输出有时要 reset

某些模型会先流出一段前言，然后才返回 tool call，例如“我来搜索一下”。如果前端直接保留这段内容，工具完成后的最终回答会和前言混在一起。因此当响应同时出现已流出的文本和工具调用时，图发送 `message.reset`，前端清空临时回答，等待下一轮正式输出。

### 6.3 为什么需要硬限制

模型可能因工具失败或错误规划不断调用。Nano 同时限制：

- `AGENT_MAX_TOOL_CALLS`：一次 Run 的工具调用总数。
- `AGENT_MAX_TOOL_ROUNDS`：模型—工具往返轮数。
- 每个工具自己的 timeout 和 retry。

达到轮数上限后，`force_answer` 不再绑定工具，强制模型基于已有信息作答，从而保证图最终可终止。生产 Agent 必须有预算和终止条件，否则会产生无限循环、不可控延迟和费用。

### 6.4 并行工具执行

同一轮中的多个 tool call 使用 `asyncio.create_task` 和 `gather` 并发执行。比如模型同时搜索两个独立主题，耗时接近较慢的那次请求，而不是两次请求耗时之和。

## 7. Research 模式：多 Agent 工作流

Research 图用于深入研究、多角度分析和对比任务：

```text
START
  -> planner / Supervisor
  -> Send 并行分发 2~5 个 researcher
       ├─ web_researcher
       ├─ document_analyst
       └─ general_researcher
  -> synthesize / Writer
  -> reviewer
       ├─ passed -> finish -> END
       └─ failed -> revise -> reviewer
                       └─ 达到修订上限 -> finish
```

### 7.1 Supervisor 做什么

Planner 使用 Pydantic `ResearchPlan` 要求模型返回结构化数据，而不是一段自然语言计划。每个 `ResearchTask` 包含 ID、问题、角色和建议工具。结构化输出的好处是：

- 后续代码可以稳定读取字段；
- Pydantic 能校验任务数量和角色枚举；
- 避免用正则从自然语言中猜计划；
- 便于把计划直接显示到前端和写入 Trace。

如果结构化调用失败，代码会退化为一个 `general_researcher` 任务，保证工作流仍能继续。这里体现的是 graceful degradation，但也意味着失败后的研究广度会下降。

### 7.2 多 Agent 到底是不是多个模型

这里的 specialist 不是多个独立部署的模型服务。它们共享同一个模型实例，但具有不同：

- System Prompt；
- 子任务上下文；
- 工具白名单；
- 并行执行分支。

“多 Agent”的核心是角色、上下文、权限和执行流隔离，不要求使用不同厂商或不同模型。如果面试官问，应明确说明这一点。

### 7.3 `Send` 如何实现 fan-out/fan-in

Planner 之后的条件边返回多个 `Send("researcher", state)`。LangGraph 为每个子任务启动 researcher 分支。所有分支完成后，`research_results` reducer 合并结果，Writer 再统一处理，这就是：

- fan-out：一个计划分发成多个并行任务；
- fan-in：多个证据结果汇聚到一个 Writer。

### 7.4 specialist 的最小权限

- `web_researcher`：只能使用 `web_search` 和 `web_extract`。
- `document_analyst`：不使用网络工具，只看传入的本地文档证据。
- `general_researcher`：可以综合文档和 Web。

Supervisor 的 `preferred_tools` 只是进一步缩小工具集合，不能扩大服务端 allowlist。即使模型在计划里给 document analyst 指定了 Web 工具，Registry 仍会拒绝暴露。这条“模型建议不能覆盖服务端策略”的原则很重要。

Research 图主动排除了 `deep_research` 工具，因为当前多 Agent 图本身已经执行研究拆分；如果 specialist 再启动另一个长时间深度研究任务，会形成嵌套编排，增加时延、费用和不可控性。`deep_research` 主要供 chat agent 在合适场景调用。

### 7.5 Writer、Reviewer 与 Reviser

Writer 读取所有结构化研究结果，生成带来源的报告。Reviewer 使用 `ReviewResult` 返回：是否通过、不受支持的断言、缺失主题和修订指令。未通过时 Reviser 只允许基于已有证据修改，不能凭空增加事实。

修订次数由 `AGENT_MAX_REVISIONS` 限制。达到上限后即使仍不完美，也会结束，避免 Reviewer—Reviser 无限循环。

当前实现有一个需要你诚实说明的边界：如果 Reviewer 的结构化输出调用本身异常，fallback 会把结果设为通过。这保证可用性，但偏向 fail-open；对高风险场景更合理的策略可能是 fail-closed、降低置信度或要求人工审核。

## 8. 工具体系：让模型安全地影响外部世界

### 8.1 Tool、ToolSpec、Registry、Policy、Executor

这四层不要混淆：

| 层 | 职责 |
|---|---|
| Tool | 真实业务函数，例如搜索网页或创建 Word |
| ToolSpec | 服务端元数据：版本、风险、超时、重试、允许角色 |
| ToolRegistry | 注册、查找并按角色筛选工具 |
| ToolPolicy | 根据 Run 上下文决定允许、拒绝或需要审批 |
| ToolExecutor | 执行策略检查、timeout、retry，并返回审计元数据 |

`ToolContext` 把本次 Run、对话、Agent 角色、写授权和已审批 call ID 传给策略层。权限属于具体请求，而不是让模型通过 prompt 自己保证安全。

### 8.2 当前工具

- Web：`web_search`、`web_extract`、`deep_research`。
- 本地只读：目录列举、文件读取、文件搜索、系统状态等。
- 本地写入：文件创建/移动、Word 创建/编辑、PDF 转换等。

Web Search 只返回受长度限制的摘要；需要核对细节时再用 Web Extract 读取原文。Extract 校验 HTTP(S)、拒绝凭据、本地地址和非公网 IP，用于降低 SSRF 风险。Deep Research 是 Tavily 异步任务：先创建任务，再轮询状态，受总超时和最大返回长度限制。

本地文件工具把所有路径解析到 `AGENT_WORKSPACE_DIR` 下，拒绝绝对路径和路径穿越。写工具默认关闭，只有前端为本次请求开启 `allow_write_tools` 才允许执行；前端发送后会重置开关，减少用户忘记关闭的风险。

### 8.3 风险模型仍可继续完善

当前支持 `read/write/high` 风险以及高风险 call ID 审批，但 UI/API 还没有完整的人在回路审批恢复流程。也就是说，框架层已经表达 `ToolApprovalRequired`，产品层尚未形成“暂停—展示参数—用户确认—从 checkpoint 恢复”的完整闭环。这是很好的后续扩展方向。

## 9. RAG：让 Agent 使用私有文档

### 9.1 为什么需要 RAG

模型参数中的知识无法覆盖用户刚上传的文件，也不应每次把整份长文档塞进上下文。RAG（Retrieval-Augmented Generation）把过程拆成：

```text
离线/异步索引：文档 -> 解析 -> 切块 -> 向量化 -> 向量库
在线检索：问题 -> 向量化 -> 相似度查询 -> 相关片段 -> LLM
```

Embedding 把文本映射为高维向量。语义相近文本的向量距离通常更近，因此可以通过 pgvector 找到与问题相关的段落。

### 9.2 Nano 的文档链路

1. 上传接口校验文件大小和类型。
2. 原文件进入私有 S3 兼容对象存储；数据库保存元数据和对象 key。
3. 本地缓存保存常用文件并按校验和验证，超过容量后按访问时间淘汰。
4. 后台 indexing worker 领取待索引文档。
5. 解析 PDF、DOCX、Markdown、文本、CSV、JSON、日志和常见图片等格式。
6. 文本按配置的 chunk size/overlap 切块。
7. 批量调用 Embedding 服务。
8. chunk、页码/章节元数据和向量写入 PostgreSQL/pgvector。
9. 查询时先向量召回，再用最低相似度、查询阈值和最大分数落差过滤。

Chunk overlap 用于避免一句话刚好跨越两个切块边界而丢失上下文。Chunk 过小会缺少语境，过大则降低检索精度并浪费模型上下文，需要通过评测调参。

### 9.3 RAG 不等于长期记忆

- 对话历史：最近若干条 user/assistant message，属于 conversation memory。
- RAG：从文档知识库检索事实片段。
- Checkpoint：保存工作流执行状态和节点位置。

三者解决不同问题，面试时不要统称为“记忆”。

## 10. 持久化、暂停与恢复

系统同时保存两类状态：

1. **业务状态**：`agent_runs`、`agent_run_events`、messages 中保存状态、进度、Trace 和最终回答。
2. **执行状态**：LangGraph PostgreSQL Checkpointer 保存每个节点后的图状态。

当客户端断开导致协程收到 `CancelledError` 时，服务将仍在运行的 Run 标为 `paused`，然后继续向上抛取消异常。恢复接口重新构建同一种图，以同一个 `thread_id` 调用并传入 `state=None`，LangGraph 从 checkpoint 继续，而不是从头重新创建用户消息。

这就是“可恢复”的核心。只在业务表里保存 `current_node` 不足以恢复，因为还缺少 messages、工具结果、并行分支结果等完整图状态；只保存 checkpoint 也不足以做产品界面，因为不方便查询耗时、计划和 Trace。因此项目同时保留两套数据。

取消与暂停也不同：

- paused：执行意外中断，允许恢复。
- cancelled：用户明确取消，不允许恢复。
- failed：图抛出错误并记录 error。
- completed：最终消息已经持久化。

## 11. 流式事件与可观测性

Token 流只能回答“模型正在输出什么”，不能回答“系统当前在做什么”。Nano 定义了更丰富的事件：

- Run：`run.started/paused/cancelled/failed`。
- Node：`node.started/completed/failed`。
- Tool：`tool.started/completed/failed`。
- Multi-agent：`plan.ready`、`agent.delegated/retrying/completed/failed`。
- Review：`review.completed`。
- Message：`message.delta/reset/completed`。

服务端只持久化白名单中的 Trace 类型，并递归限制字符串、数组、对象大小。字段名包含 api_key、authorization、secret、token 等内容时会被替换为 `[redacted]`，降低秘密进入日志的风险。

前端运行详情展示总耗时、工具调用/失败数、当前节点和时间线。因此“可观测”不是只打印日志，而是从 Agent 内部事件到数据库再到 UI 的完整产品能力。

当前 Trace 仍不是 OpenTelemetry 分布式追踪：没有跨服务 trace/span 标准、token/cost 指标和集中式指标告警。简历上适合写“持久化 Agent Trace”，不应夸大为完整 APM 平台。

## 12. Agent 评测：为什么普通单元测试不够

LLM 输出具有非确定性。普通测试可以验证函数和路由，但不能充分回答：

- Agent 是否选择了正确工具？
- 多 Agent 是否真的完成委派和审核？
- 引用是否来自工具看到过的 URL？
- Prompt 或模型升级后质量是否回退？
- researcher 失败后系统是否还能完成任务？

### 12.1 Golden Dataset

`golden_v2.json` 当前包含 12 个用例：7 个 chat、5 个 research。用例可以规定：

- 必须/禁止出现的关键词；
- 期望调用的工具；
- 期望完成的节点、角色和事件；
- 最少引用数和引用来源要求；
- 最大延迟；
- 通过阈值；
- Judge rubric；
- 故障注入方式。

### 12.2 确定性评分

`score_agent_output` 从答案和事件中计算布尔 checks，再用通过项占比作为分数。它同时验证最终内容和执行轨迹。例如回答看起来正确，但要求联网核验的 case 没有调用搜索，也可以被判定失败。

引用检查会：

1. 从最终回答提取 URL；
2. 从成功工具事件收集来源 URL；
3. 规范化 scheme、host、path 和 query；
4. 区分 invalid、grounded 和 ungrounded URL。

这比“回答里有 http 就算引用”更可靠，可以发现模型凭空生成链接。

### 12.3 LLM-as-a-Judge

可选 Judge 从正确性、完整性、依据性和指令遵循四个维度各打 1–5 分，并标记 critical error。最终分数是确定性分数与 Judge 分数的加权组合。

Judge 适合判断语义质量，但存在模型偏见、重复运行波动和成本。当前 Judge 与主 Agent 使用同一模型家族，也可能存在自我偏好。因此确定性规则仍然保留，且更成熟的方案应加入少量人工标注集、多 Judge 校准或统计置信区间。

### 12.4 Baseline 与故障注入

Baseline 不只是显示当前得分，还按相同 case ID 比较每项和整套分数差值，用于发现版本回归。

`researcher_once` 让第一次 specialist 执行失败，验证自动重试；`researcher_always` 让它持续失败，验证单个分支失败后 Writer/Reviewer 仍能产生诚实的降级回答。这属于 resilience testing。

## 13. 数据模型

核心实体关系可以简化为：

```text
Conversation
  ├─ Message (user/assistant, sources, options)
  └─ AgentRun
       ├─ user_message_id
       ├─ assistant_message_id
       └─ AgentRunEvent

Document
  └─ DocumentChunk (text, metadata, embedding vector)

AgentEvalRun
  └─ AgentEvalResult
```

值得注意的数据库设计：

- UUID 用于对外暴露的主要实体，消息和事件使用递增 ID。
- JSONB 保存 sources、options、plan、progress、payload 和评测 metrics，适合结构经常演进的 Agent 元数据。
- 外键把 Run 与输入/输出消息关联，避免只靠字符串猜一次执行属于哪条消息。
- pgvector 让向量检索与业务数据共用 PostgreSQL，简化个人项目部署。

当前启动时使用 `Base.metadata.create_all` 和若干 `ALTER TABLE ... IF NOT EXISTS` 做兼容升级。这对个人部署简单，但生产项目应引入 Alembic，记录可审计、可回滚的 schema migration。

## 14. 前端如何呈现 Agent

前端包含三个主要视图：

- Chat：对话、模式选择、RAG/写工具开关、流式进度、来源和 Trace。
- Documents：上传、预览、删除、索引状态和重新索引。
- Evaluations：用例选择/编辑、Judge 和 baseline 配置、运行进度及结果比较。

`App.vue` 的事件处理器把后端事件映射为临时 UI 状态。例如 tool.started 显示工具执行中，message.delta 追加文本，message.reset 清空临时文本，message.completed 替换为数据库返回的最终消息。

当前前端的主要工程债是组件偏大，`App.vue` 超过千行，评测和文档视图也较重；Form.io 使生产构建出现较大的 chunk。后续可把事件状态机、Key 管理、Trace、composer 和消息列表拆成 composables/components，并对评测页动态 import。

## 15. 部署与 CI/CD

生产 Compose 包含：

- PostgreSQL/pgvector；
- FastAPI 后端；
- Nginx 托管的 Vue 静态页面并反向代理 API；
- 文档缓存和 Agent workspace 持久卷；
- 服务健康检查和依赖顺序。

CI 的质量门禁依次执行：

1. 安装并运行后端测试，验证应用可 import。
2. 前端 `npm ci`、测试和生产构建。
3. 启动完整 Compose，访问前后端健康接口，并验证 LibreOffice/Poppler。
4. 质量门禁通过后，在原生 ARM runner 构建并推送 GHCR 镜像。
5. 同时生成 `latest` 和完整 Git SHA tag，并附带 provenance 与 SBOM。

SHA tag 支持可重复发布和回滚，比只发布 `latest` 更可靠。

当前系统没有用户账户和文档授权层，只应部署在 LAN、Tailscale 或带认证的反向代理之后。不能把现状描述为支持互联网多租户。

## 16. 测试现状与边界

本地验证结果：

- 后端 79 项测试通过。
- 前端 15 项测试通过。
- Vite 生产构建成功。

测试覆盖 Agent 路由、并行研究、工具循环、RAG、文档、账户接口、SSE 解析、Markdown 安全、评测、引用、工具策略和本地文件边界等。

但“94 项测试通过”不等于所有生产风险都已解决：

- 大部分外部模型和网络调用使用 fake/mock，没有证明真实供应商长期稳定。
- 没有浏览器 E2E 测试完整覆盖上传—检索—回答—恢复路径。
- 没有代码覆盖率门槛、静态类型检查和 lint 门禁。
- 没有公开提交一轮真实 golden dataset 的量化结果。
- 没有负载、并发、长时间运行和数据库故障恢复测试。

面试中主动说出这些边界，通常比声称“生产级、没有问题”更可信。

## 17. 关键设计取舍

### 为什么用 LangGraph，而不是手写 while 循环

手写循环可以完成简单 tool calling，但复杂后会遇到并行、条件路由、状态合并、checkpoint 和恢复问题。LangGraph 把节点、边、state reducer 和 checkpointer 标准化，更适合显式工作流。

### 为什么分 chat 和 research 两个图

简单问题走多 Agent 会增加延迟和费用；复杂研究只用单 Agent 又容易遗漏角度。双模式让轻量路径和重型路径分别优化。`auto` 当前通过关键词启发式选择，简单透明，但可能误分类；后续可以用轻量分类器并保留用户显式覆盖。

### 为什么工具权限必须在服务端

Prompt 只是给模型的文字建议，模型输出不可信。只有服务端 Registry/Policy 才能形成不可绕过的边界。

### 为什么 API Key 不写入 Run

持久化 Key 会扩大泄漏面。Run 只保存必要状态，恢复时用户重新提供凭据。代价是浏览器需要管理 Key，且断开后无法在无人参与的后台继续依赖这些凭据。

### 为什么同时需要规则评分和 Judge

规则稳定、便宜、可解释，但看不懂复杂语义；Judge 能判断语义，但昂贵且有偏差。组合两者比只使用其中一种更平衡。

## 18. 当前项目可以如何继续演进

按优先级建议：

1. **展示与证据**：README 增加架构图、Trace GIF、真实评测结果、延迟和费用数据。
2. **数据库工程**：引入 Alembic，替代启动时手工 ALTER。
3. **安全与多用户**：认证、用户/文档 owner、对象级授权、限流、服务端密钥托管。
4. **审批闭环**：高风险工具暂停后，由 UI 展示工具参数，用户确认再从 checkpoint 恢复。
5. **可观测性**：OpenTelemetry、token/cost、模型和工具分位延迟、错误率告警。
6. **评测可信度**：保存标准评测报告，引入人工标注样本、多次运行统计和供应商回归矩阵。
7. **前端维护性**：拆分 App、composable 化 SSE 状态机、路由级 code splitting、Playwright E2E。
8. **并发控制**：后台任务队列、每用户配额、Run worker 与 API 进程解耦。

## 19. 面试时的项目介绍

### 30 秒版本

> Nano 是我实现的一个可恢复、可观测、可评测的多 Agent 研究助手。它基于 LangGraph 构建 chat 工具循环和 research Supervisor—Specialist 工作流，支持本地文档 RAG、Web 检索、受控文件工具、PostgreSQL checkpoint 恢复和 SSE 进度流。项目还实现了 12 类 golden cases、引用溯源、LLM Judge 和故障注入，并通过 Docker Compose 与 CI 发布 ARM64 镜像。

### 2 分钟版本

> 这个项目想解决的不是单纯接入大模型，而是 Agent 应用的工程化问题。在线请求先创建独立 Agent Run，再按 chat 或 research 模式编译 LangGraph。Chat 模式是有工具次数和轮数上限的模型—工具循环；Research 模式由 Supervisor 生成结构化计划，用 Send 并行分发给三类 specialist，然后由 Writer 汇总、Reviewer 审核，必要时 Reviser 有限次修订。
>
> 工具不是直接交给模型执行。我做了 Tool Registry、Policy 和 Executor，服务端控制角色白名单、副作用授权、超时和重试。本地文档经过对象存储、解析、切块、Embedding 和 pgvector 检索后作为不可信证据注入上下文。运行中产生节点、工具、委派和审核事件，经 SSE 展示并持久化为 Trace；网络中断时，LangGraph PostgreSQL checkpoint 可以基于 Run ID 恢复。
>
> 为了避免只凭 Demo 判断效果，我还做了版本化评测集，结合确定性轨迹检查、引用来源验证、可选 LLM Judge、baseline 对比和 researcher 故障注入。目前主要不足是没有多用户鉴权、正式数据库迁移、浏览器 E2E 和公开量化评测报告。

### 可写入简历的三条

- 基于 LangGraph 构建 Chat 工具循环及 Supervisor–Specialist 多 Agent 工作流，通过并行 fan-out/fan-in、Reviewer/Reviser 闭环和 PostgreSQL checkpoint 实现复杂研究任务拆解、故障隔离与中断恢复。
- 设计服务端 Tool Registry/Policy/Executor，支持角色白名单、副作用授权、超时重试与调用审计；打通 Web 检索、本地 RAG、对象存储及 DOCX/PDF 文档产物链路。
- 建立包含 12 类场景的版本化 Agent 评测体系，覆盖工具/节点路由、引用溯源、延迟预算、LLM Judge、baseline 与故障注入；完成 94 项自动化测试及 Compose/ARM64 镜像交付链路。

不要把尚未测量的数据写成成果。例如没有真实统计前，不要写“准确率提升 30%”或“支持千级并发”。

## 20. 高频面试问题与回答要点

### Q1：这个项目与普通聊天机器人最大的区别是什么？

有显式工作流、工具执行、状态持久化、恢复、Trace 和评测。模型只是决策组件，系统还负责权限、终止条件和数据一致性。

### Q2：为什么这算多 Agent？

Supervisor 将任务拆成独立子任务，多个具有不同 prompt、上下文和工具权限的 specialist 并行执行，再由 Writer/Reviewer 汇合。它们共享底层模型不影响多 Agent 的角色与运行隔离。

### Q3：模型怎么调用 Python 工具？

通过 function/tool calling Schema 返回结构化调用意图。应用解析 tool call，经过服务端策略后执行函数，再构造 ToolMessage 放回消息列表。

### Q4：如何防止无限循环？

限制 tool rounds、tool calls、tool timeout、retry 和 revision count；到达上限后进入不绑定工具的 force_answer 或结束节点。

### Q5：并行研究结果会不会互相覆盖？

`research_results` 使用 `operator.add` reducer，LangGraph 合并每个 Send 分支返回的列表，而不是 last-write-wins。

### Q6：断线恢复是怎么实现的？

Run UUID 作为 LangGraph thread ID。每个节点后的完整图状态写入 PostgreSQL checkpoint；断线把业务 Run 标为 paused，恢复时用同一 thread ID 和 `state=None` 继续。

### Q7：RAG 的数据流是什么？

上传到对象存储，后台解析切块并生成 embedding，向量写入 pgvector；查询也生成 embedding，按相似度召回并过滤，把片段以不可信资料 System Message 注入模型。

### Q8：如何处理 Prompt Injection？

文档被声明为不可信事实资料；工具权限由服务端而非文档或模型决定；本地路径被限制在 workspace；Web URL 拒绝本地/私网地址。但这不是完整防御，仍需内容隔离、输出检查和更严格审批。

### Q9：如何验证引用没有编造？

从工具完成事件收集真实来源 URL，从回答提取引用 URL，规范化后做集合匹配，把未在工具来源中出现的标为 ungrounded。

### Q10：为什么不用现成 Agent harness？

项目没有接入名为 Harness 的第三方框架，而是在 LangGraph 上组合了运行生命周期、工具治理、checkpoint、Trace 和 eval，形成适合本项目的轻量 runtime/evaluation harness。

### Q11：这个系统最明显的技术债是什么？

没有多用户权限和 Alembic；前端组件偏大；真实评测结果和 E2E 不足；Judge 与主模型同源；高风险工具审批只有框架表达，没有完整 UI 恢复闭环。

### Q12：如果要支持更多并发，先改哪里？

把长时间 Run 从 API 请求进程移到任务队列/worker；增加并发配额和取消信号；数据库连接池与索引任务分离；SSE 只订阅事件；对外部模型和工具做速率限制、熔断和成本预算。

## 21. 建议的代码阅读顺序

第一遍只建立主流程：

1. `backend/app/agent/state.py`
2. `backend/app/agent/graph.py`
3. `backend/app/service/agent_run.py`
4. `backend/app/api/conversation.py`
5. `frontend/src/api.js`

第二遍理解能力与边界：

6. `backend/app/tooling/spec.py`
7. `backend/app/tooling/registry.py`
8. `backend/app/tooling/policy.py`
9. `backend/app/tooling/executor.py`
10. `backend/app/tools/__init__.py`
11. `backend/app/service/rag.py`
12. `backend/app/service/document_indexer.py`

第三遍理解质量体系：

13. `backend/app/eval/dataset.py`
14. `backend/app/eval/scorer.py`
15. `backend/app/eval/citations.py`
16. `backend/app/eval/judge.py`
17. `backend/app/service/evaluation.py`
18. `backend/tests/test_agent_graph.py`
19. `backend/tests/test_tool_registry.py`

## 22. 真正掌握项目的练习

只读文档很容易产生“好像懂了”的错觉。建议按顺序完成：

1. 不看代码，画出 chat 和 research 两张图，再与 `graph.py` 对照。
2. 手动解释一次 `web_search` tool call 从模型输出到 ToolMessage 的全过程。
3. 在测试中添加一个 fake tool，验证无写授权时被 Policy 拒绝。
4. 给 ResearchPlan 新增一个字段，观察 Pydantic、Trace 和前端要改哪些位置。
5. 新增一个 golden case，要求必须调用 Web Extract 且引用有 provenance。
6. 让 `researcher_once` 失败，逐条说明预期 Trace 事件顺序。
7. 模拟 SSE 在任意字节位置分块，解释前端为什么需要 buffer。
8. 选择一份文档，记录 chunk size 改变前后的召回结果。
9. 给高风险工具设计“暂停—审批—恢复”的接口和状态变化，但先不实现。
10. 用自己的话录制一次 2 分钟项目介绍，确保不依赖本文逐字背诵。

如果你不能独立完成前五项，暂时不要在面试中把自己描述为“主导设计了全部架构”。更诚实也更安全的表述是：你使用 AI 编码助手完成了实现，并重点掌握、验证和迭代了工作流、工具治理或评测中的具体部分。之后随着你能独立修改和解释更多模块，再逐步扩大自己的 ownership 表述。

## 23. 术语速查

| 术语 | 在本项目中的含义 |
|---|---|
| Agent | 模型、工具、状态、编排和边界组成的运行系统 |
| Tool calling | 模型输出结构化工具调用意图，应用负责执行 |
| Workflow | 开发者定义的节点、边和终止条件 |
| StateGraph | LangGraph 的有状态工作流图 |
| Node | 一步处理，如 planner、tools、reviewer |
| Conditional edge | 根据 state 选择下一节点 |
| Reducer | 并行或多次更新同一字段时的合并规则 |
| Fan-out/fan-in | 一个任务并行拆分，再汇聚多个结果 |
| Structured output | 用 Pydantic Schema 约束模型返回结构 |
| RAG | 检索外部资料后增强生成 |
| Embedding | 文本的高维语义向量表示 |
| pgvector | PostgreSQL 的向量类型和相似度检索扩展 |
| Checkpoint | 可恢复的完整图执行状态 |
| Trace | 一次 Run 的节点、工具和状态事件记录 |
| SSE | 服务端通过单条 HTTP 长连接不断推送事件 |
| Guardrail | 权限、预算、校验、超时等确定性边界 |
| Golden dataset | 固定的版本化回归评测用例集 |
| LLM-as-a-Judge | 使用另一个模型按 rubric 评价输出 |
| Baseline | 用作质量回归比较的历史评测运行 |
| Fault injection | 主动制造故障以验证恢复与降级能力 |
| Harness | 包裹 Agent 的运行、工具、观测和评测基础设施 |

## 24. 最后需要形成的认识

这个项目最值得学习的不是某个 LangGraph API，而是下面五个工程原则：

1. **模型输出不可信**：结构要校验，工具要经过服务端策略，文档只能作为资料。
2. **所有循环必须有预算**：工具次数、轮数、重试、修订和超时都要有上限。
3. **状态必须可解释地持久化**：消息、业务 Run、Trace 和 checkpoint 各有职责。
4. **Agent 质量要看过程和结果**：不仅检查答案，还检查工具、节点、来源、延迟和失败恢复。
5. **可演示不等于可生产**：认证、迁移、并发、成本、监控和真实评测决定系统能否长期运行。

当你能从一次 HTTP 请求讲到最终 checkpoint、能解释为什么 specialist 工具不能由 Supervisor 越权、能说明 RAG 与 memory 的区别，并能指出 Reviewer fail-open 等真实边界时，你才算真正理解了 Nano，而不是只记住了“用了 LangGraph 和 RAG”。
