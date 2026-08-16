# Nano Multi-Agent Research Assistant

Nano 是一个可恢复、可观测、可评测的 LangGraph multi-agent 研究助手。它不仅调用 LLM，
还把任务规划、角色分派、并行执行、工具权限、审核修订和运行追踪组成了一条完整的工程链路。

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
- 可取消/恢复的 Agent Run，以及持久化 trace、耗时和失败指标
- 本地文档 RAG、网页搜索/提取和来源展示
- 版本化 golden dataset、规则评分和 LLM-as-a-judge 评测
- Form.io schema 驱动的自定义评测用例，以及安全 Markdown 评分/输出
- 可追溯 URL 引用评分，以及 multi-agent 瞬时/持续故障注入回归用例
- 浏览器端 DeepSeek、Tavily 与百炼 Embedding Key 配置及服务状态检查
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
