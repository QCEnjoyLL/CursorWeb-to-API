# 项目分析与功能扩展指南

## 1. 项目概述

本项目 (`cursorweb2api`) 是一个代理服务，其核心功能是将 Cursor AI 聊天功能的非公开 Web 接口，转换为一个与 OpenAI API 兼容的标准接口。

这使得任何支持 OpenAI API 格式的客户端、库或应用程序，都能够无缝接入并使用 Cursor 强大的 AI 模型能力，而无需关心其底层的复杂验证机制。

## 2. 核心实现细节

项目成功的关键在于模拟真实浏览器行为，以绕过 Cloudflare 的机器人检测并获得合法的访问凭证。

### 2.1 `x-is-human` 验证头生成

Cursor 的 API `https://cursor.com/api/chat` 受 Cloudflare 保护，它要求请求中包含一个名为 `x-is-human` 的 HTTP Header 来验证客户端是真实用户浏览器而非自动化脚本。

本项目的 `get_x_is_human` 函数完美地解决了这个问题：

1.  **获取动态 JS**: 函数首先请求 `https://cursor.com/ai-chat/……/_next/static/chunks/……-……_ssg.js`，这是一个动态生成的 JavaScript 文件，包含了生成验证信息所需的核心逻辑。

2.  **构建执行环境**: 它读取本地的 `jscode/main.js` 和 `jscode/env.js` 文件。这些文件共同构建了一个模拟的浏览器 `window` 和 `document` 环境。

3.  **动态注入与执行**:
    *   将上一步获取的动态 JS (`$$cursor_jscode$$`) 和预设的浏览器指纹信息（如 `userAgent`、`WebGL` 渲染信息等）注入到 `jscode/main.js` 模板中。
    *   使用 `subprocess` 调用 `node` 命令执行这个最终生成的 JavaScript 脚本。

4.  **获取结果**: Node.js 脚本执行后，会调用 Cursor 的内部函数（例如 `window.V_C[0]()`），计算出 `x-is-human` 所需的令牌（token），并通过 `console.log` 输出。Python 进程捕获此输出，从而获得与真实浏览器一致的验证凭证。

### 2.2 API 代理与数据转换

- **FastAPI 服务**: `main.py` 使用 FastAPI 框架创建了两个核心端点：
    - `GET /v1/models`: 模拟 OpenAI 的模型列表接口，返回 `app/config.py` 中预设的模型 ID。
    - `POST /v1/chat/completions`: 代理核心聊天接口。

- **请求转换**: 当此端点收到一个 OpenAI 格式的请求时，`cursor_chat` 函数会执行以下转换：
    - `messages` 格式转换: 将 OpenAI 的消息结构（`[{'role': 'user', 'content': '...'}]`）转换为 Cursor 所需的格式 (`[{'role': 'user', 'parts': [{'type': 'text', 'text': '...'}]}]`)。

## 3. 工具调用 (Tool Calling) 实现

本项目对 OpenAI 的工具调用功能提供了出色的兼容支持。

当你的请求中包含 `tools` 和 `tool_choice` 参数时，它们会被无缝地传递给 Cursor 的后端。

**实现流程**:

1.  **请求体定义**: `app/models.py` 中的 `ChatCompletionRequest` 模型已经包含了 `tools` 和 `tool_choice` 字段，完全兼容 OpenAI 格式。

2.  **参数传递**: 在 `main.py` 的 `cursor_chat` 函数中，代码检查请求体中是否存在 `tools` 和 `tool_choice`。
    ```python
    # 添加工具相关参数
    if request.tools is not None:
        json_data["tools"] = [tool.dict() for tool in request.tools]
    if request.tool_choice is not None:
        json_data["tool_choice"] = request.tool_choice
    ```
3.  **发送至 Cursor**: 这些参数被直接添加到发送给 `https://cursor.com/api/chat` 的 JSON 载荷中。Cursor 的后端会识别这些参数并执行相应的工具调用逻辑。返回的结果（无论是函数调用请求还是最终的文本回复）也会被正确地解析和返回。

这意味着，你可以像使用原生 OpenAI API 一样，定义你的工具、函数签名，并让模型决定何时调用它们。

## 4. 如何升级以支持 Claude 3.5 Sonnet 等新模型

Cursor 已经支持包括 Claude 3.5 Sonnet 在内的多种新模型。要通过本代理使用它们，只需两步：

### 步骤 1: 确定模型的内部 ID

首先，你需要知道 Cursor 内部用来标识这些模型的 ID。通常，这些 ID 遵循一个可预测的模式。根据社区的经验，Claude 3.5 Sonnet 的 ID 很可能是 `claude-3.5-sonnet`。

其他常见模型的 ID 可能包括：
- `claude-3-opus`
- `claude-3-haiku`
- `gpt-4o` (如果项目默认配置中没有)

### 步骤 2: 修改配置文件

1.  打开 `app/config.py` 文件。
2.  找到 `MODELS` 这个变量。
3.  将你想要添加的模型 ID 添加到这个字符串中，用逗号隔开。

**示例**:
假设 `config.py` 的原始内容是：
```python
MODELS = "gpt-4,gpt-3.5-turbo"
```

为了加入 Claude 3.5 Sonnet 和 GPT-4o，你可以修改为：
```python
MODELS = "gpt-4,gpt-3.5-turbo,claude-3.5-sonnet,gpt-4o"
```

### 步骤 3: 重启服务并调用

保存文件后，重启你的 Docker 容器或 Python 服务。

现在，你可以在 API 请求中直接指定使用新添加的模型了：
```json
{
  "model": "claude-3.5-sonnet",
  "messages": [
    {
      "role": "user",
      "content": "你好，请介绍一下你自己。"
    }
  ]
}
```

你的请求将会被正确地转发给 Cursor 后端，并由 Claude 3.5 Sonnet 模型处理。

---
文档编写完毕。