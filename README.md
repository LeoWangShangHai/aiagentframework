# Python 前后端代码结构（Web 前端 + FastAPI 后端）

本仓库包含：

- Web 前端（静态页面/JS/CSS）：[frontend/index.html](frontend/index.html)
- Web 后端（FastAPI API + 托管前端静态资源）：[backend/app/main.py](backend/app/main.py)

可选集成：

- Microsoft Agent Framework（Python 包 `agent-framework`）：提供一个最小的 Agent 调用 API（`POST /api/agent/run`）

## 目录结构建议

```text
testpython/
	backend/
		app/
			main.py              # FastAPI 应用入口
			api/
				router.py          # 聚合路由
				routes/
					health.py        # /api/health
					hello.py         # /api/hello
					agent.py         # /api/agent/run
			agents/
				af_client.py       # agent-framework 客户端/agent 创建
	frontend/
		index.html             # Web 首页
		app.js                 # 调用后端 API 的前端脚本
		styles.css             # 样式
	requirements.txt
	backend/requirements-agent.txt
	README.md
```

## 运行（Web 前后端）

安装依赖：

```powershell
cd c:\pythonproject\testpython
py -m pip install -r requirements.txt
```

启动服务：

```powershell
py -m uvicorn app.main:app --reload --app-dir c:\pythonproject\testpython\backend
```

访问：

- 页面：`http://127.0.0.1:8000/`
- 静态资源：`http://127.0.0.1:8000/static/app.js`
- 接口：`http://127.0.0.1:8000/api/health`
- 接口：`http://127.0.0.1:8000/api/hello?name=World`

### 知识库 / RAG (Chroma + Azure OpenAI Embedding)

- 依赖：`AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME`
- API：
  - `POST /api/knowledge/upload` (form-data `file`，支持 .txt/.md/.pdf)
  - `POST /api/knowledge/query` `{ "question": "...", "top_k": 4 }`
  - `GET /api/knowledge/stats`
- 数据：`data/uploads/` 保存原文件；`data/chroma/` 为 Chroma 持久化

## 后端对接 microsoft/agent-framework（Python）

本项目用的是该仓库的 Python 包：`agent-framework`（预发布版本通常需要 `--pre`）。

安装依赖：

```powershell
cd c:\pythonproject\testpython
py -m pip install -r backend\requirements-agent.txt
```

配置环境变量（示例见 [config/.env.example](config/.env.example)）：

- `AZURE_OPENAI_ENDPOINT`
- `AZURE_OPENAI_RESPONSES_DEPLOYMENT_NAME`
- （可选）`AZURE_OPENAI_API_VERSION`

认证方式：Entra ID（推荐）

- 先执行 `az login`
- 确保当前账号/服务主体对 Azure OpenAI 资源有权限（常见需要分配类似 “Cognitive Services OpenAI User” 的角色）

也支持 API Key 认证（可选）：

- 设置 `AZURE_OPENAI_API_KEY`
- 当 `AZURE_OPENAI_API_KEY` 有值时，后端会优先使用 key 认证；否则使用 Entra ID

也可以使用专门的配置文件（推荐，避免和其它环境变量混在一起）：

- 复制 [config/azure_openai.env.example](config/azure_openai.env.example) 为 `config/azure_openai.env`
- 填入你的连接信息（该文件已在 `.gitignore` 中忽略，不会被提交）

如果遇到 tenant 不匹配（类似 “Token tenant ... does not match resource tenant”），请在配置里填写：

- `AZURE_TENANT_ID`（资源所在租户的 Directory ID），并用 `az login --tenant <AZURE_TENANT_ID>` 重新登录

启动 FastAPI 后，即可调用：

- `POST http://127.0.0.1:8000/api/agent/run`
- `POST http://127.0.0.1:8000/api/agent/stream`（SSE 流式输出，Web 端使用）

请求体示例：

```json
{ "message": "Say hello" }
```

### 多轮对话 / Memory（基于 agent-framework thread）

`/api/agent/run` 现在支持多轮对话：

- 首次请求不需要传 `conversation_id`
- 服务端会创建一个 thread，并在响应里返回 `conversation_id`
- 后续请求带上同一个 `conversation_id`，即可在同一 thread 上继续对话（具备上下文记忆）

示例：

```json
{ "message": "My name is Bob" }
```

响应示例（截断）：

```json
{ "output": "...", "conversation_id": "<uuid>" }
```

后续：

```json
{ "message": "What is my name?", "conversation_id": "<uuid>" }
```

说明：当前会话状态存储在服务端内存里（进程重启会丢失）。

## 后端测试

安装测试依赖：

```powershell
py -m pip install -r backend\requirements-dev.txt
```

运行测试：

```powershell
py -m pytest -q
```

如果你要运行 Azure OpenAI 的 REST 集成测试（`backend/tests/test_azure_openai_rest_chat.py`），并且你的资源要求 `api-version`，可以配置：

- `AZURE_OPENAI_REST_API_VERSION`（仅 REST 测试使用，优先级高）
- 或 `AZURE_OPENAI_API_VERSION`

说明：

- `backend/tests/test_agent_conversation.py` 是集成测试，需要配置 Azure OpenAI 环境变量；否则会自动跳过。

## 流式输出（Web）

Web 页面默认走流式接口：`POST /api/agent/stream`，返回 `text/event-stream`（SSE）。

启动服务：

```powershell
py -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000 --reload
```

访问：

- 页面：`http://127.0.0.1:8000/`
