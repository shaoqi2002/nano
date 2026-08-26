# Nano Multi-Agent Research Assistant

Nano 是一个可恢复、可观测、可评测的 LangGraph multi-agent 研究助手。它不仅调用 LLM，
还把任务规划、角色分派、并行执行、工具权限、审核修订和运行追踪组成了一条完整的工程链路。

如果希望从 Agent 基础概念开始理解请求链路、工作流、RAG、工具治理、恢复与评测实现，参阅
[`docs/NANO_AGENT_PROJECT_GUIDE.md`](docs/NANO_AGENT_PROJECT_GUIDE.md)。

## Multi-agent 架构

```text
用户请求
   │
Supervisor（拆解任务并选择 specialist）
   ├── Web Researcher ────── web_search / web_extract
   ├── Document Analyst ──── 本地 RAG 证据
   └── General Researcher ── 文档 + 受控 Web 工具
             │（并行 fan-out / fan-in）
           Writer
             │
          Reviewer ──不通过──> Reviser ──> Reviewer
             │通过
           最终回答
```

每个 specialist 都有独立系统提示词和服务端工具白名单。Supervisor 给出的
`preferred_tools` 只能缩小权限，不能绕过白名单扩大权限。单个 specialist 失败时会有限重试；
重试耗尽后，失败会作为结构化研究结果进入汇总，不会直接中断其他并行任务。

## 工程能力

- LangGraph `StateGraph`、`Send` 并行分发和 PostgreSQL checkpoint 恢复
- Supervisor-worker 路由、角色化提示词和 least-privilege 工具策略
- SSE 流式回答、节点进度、工具调用与 multi-agent handoff 事件
- 聊天内选择、拖放或粘贴文本、图片、PDF、DOCX 附件；附件随消息发送，不进入 RAG 文档库
- 进入应用前选择或创建 workspace；对话、文档、运行记录、评测和投递数据按 workspace 隔离
- 可取消/恢复的 Agent Run，以及持久化 trace、耗时和失败指标
- 本地文档 RAG、网页搜索/提取和来源展示
- 版本化 golden dataset、规则评分和 LLM-as-a-judge 评测
- Form.io schema 驱动的自定义评测用例，以及安全 Markdown 评分/输出
- 可追溯 URL 引用评分，以及 multi-agent 瞬时/持续故障注入回归用例
- 浏览器端 DeepSeek、Tavily 与百炼 Embedding Key 配置及服务状态检查
- 通用 Tool Registry，统一管理工具版本、权限、风险、超时、重试与审计元数据
- 受限本地工作区读写、系统状态查询，以及安全文档产物自动写入
- 结构化生成/版本化编辑 Word，LibreOffice 转换 PDF，并提供临时浏览器下载
- Eval 历史运行 baseline 对比，支持总分与逐用例回归差值
- FastAPI + SQLAlchemy + PostgreSQL/pgvector 后端，Vue 3 前端
- CI 测试门禁、完整 Compose 冒烟测试、SBOM 和 Git SHA 不可变镜像

## 本地启动

1. 启动基础服务：`docker compose up -d`
2. 安装后端依赖：`pip install -r backend/requirements.txt`
3. 启动后端：在 `backend` 目录运行 `uvicorn app.main:app --reload`
4. 安装并启动前端：在 `frontend` 目录运行 `npm install` 和 `npm run dev`

DeepSeek 和 Tavily API Key 由前端请求头传入，不会写入 Agent trace。部署配置见
[`DEPLOYMENT.md`](DEPLOYMENT.md) 和 [`.env.production.example`](.env.production.example)。

首次启动会创建 `ch4` workspace，并把升级前已有的对话、文档、Agent Run、Eval 和求职投递
记录迁移到其中。进入 Nano 前必须选择或创建 workspace；退出后可重新选择。普通 workspace
只显示聊天和文档库，Agent Eval 与求职投递仅在 `ch4` 中显示，并由后端同步限制访问。入口页
只列出当前浏览器成功进入过的 workspace；也可以输入准确名称进入已有 workspace。普通 workspace
可从侧栏永久删除，`ch4` 作为系统迁移 workspace 不允许删除。

聊天附件每条最多 8 个：单个文本文件上限 200 KB，单张图片上限 5 MB，PDF/DOCX/PPTX 单个上限
10 MB，总上限 15 MB。文本、PDF、DOCX 和 PPTX 会在本次聊天请求中直接解析为用户上下文，不创建
文档库记录，也不进入 RAG；扫描版 PDF 需要 OCR，当前只能读取其中已有的文本层。图片会转换
为 OpenAI 兼容的 `image_url` 内容块并随聊天
历史保存。包含图片的上下文会自动路由到 `deepseek-v4-flash-vision-exp`，纯文本对话仍使用
`DEEPSEEK_MODEL`。可通过 `DEEPSEEK_VISION_MODEL` 覆盖视觉模型名称。

## 验证

```powershell
cd backend
python -m unittest discover -s tests

cd ..\frontend
npm test
npm run build
```

研究请求可选择 `auto`、`chat` 或 `research` 模式。运行完成后可在界面的“运行详情”中查看
Supervisor 分派、Agent 重试/完成、工具调用、审核结果与完整时间线。

## 本地工具与文档产物

`AGENT_WORKSPACE_PATH` 会挂载为 Agent 唯一可访问的本地工作区。文件工具会解析并校验
所有路径，拒绝路径穿越和越界访问。根据用户的直接请求生成 Word、另存编辑版本或转换 PDF
会自动允许，并始终创建新产物；文本覆盖和文件移动仍需要 API 请求显式授权。

Word 工具支持标题、正文、多级标题、项目符号、编号列表、引用、表格和分页。编辑操作始终
生成新的 DOCX 版本，不覆盖来源文档。聊天生成物不进入文档库，而是提供默认 24 小时有效的
浏览器下载链接；默认只生成 DOCX，只有用户明确要求时才同时生成 PDF。PDF 转换依赖后端镜像
内的 LibreOffice，并使用 Poppler 做部署环境中的页面渲染检查。

PPT 工具支持在聊天中直接生成 16:9 PPTX，也支持把 PPTX 作为聊天附件上传后进行文字替换、
删除幻灯片和追加幻灯片。编辑结果始终作为新的临时下载产物返回，不进入文档库，也不覆盖上传的源文件。
新建 PPTX 默认使用内容驱动的动态主题系统，根据整份演示生成协调色板和明暗模式，不受有限模板数量约束；
同时保留 `business`、`modern` 和 `tech` 作为向后兼容预设。调用方也可通过开放式 `design` 配置传入视觉语气、
明暗模式和品牌颜色。系统会根据内容结构以及
“核心结论”“关键指标”“实施步骤”等页面语义选择观点、大数字或流程版式；用户明确指定主题或版式时优先采用用户设置。
