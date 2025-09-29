# CursorWeb-to-API

[![Python](https://img.shields.io/badge/Python-3.12%2B-blue)](https://www.python.org/)
[![Docker](https://img.shields.io/badge/Docker-Ready-blue)](https://www.docker.com/)
[![License](https://img.shields.io/badge/License-MIT-green)](./LICENSE)

将 Cursor 官网的 Web 聊天接口转换为与 OpenAI API 完全兼容的接口，让你可以在任何支持 OpenAI 的应用中使用 Cursor 的强大模型。

> **Note**: 本项目基于 [jhhgiyv/cursorweb2api](https://github.com/jhhgiyv/cursorweb2api) 进行二次开发，进行添加了工具调用及功能增强和优化。

## ✨ 功能特性

- ✅ **完全兼容 OpenAI**: 无缝集成现有 OpenAI 生态，支持各种客户端和库。
- ✅ **支持流式响应**: 实时获取模型输出，体验如官方网站般流畅。
- ✅ **支持工具调用**: 完整支持 OpenAI 的 Tool Calling (Function Calling) 功能。
- ✅ **多模型支持**: 支持包括 `Claude 3.5 Sonnet`, `GPT-4o` 在内的多种前沿模型。
- ✅ **Docker 部署**: 提供开箱即用的 Docker 配置，一键启动服务。

---

## 🚀 快速开始

本项目推荐使用 Docker 进行部署，方便快捷。

**1. 配置环境变量 (可选)**

你可以直接使用项目提供的默认配置。如果需要自定义，请复制 `.env.example` 文件为 `.env` 并修改其内容。

```bash
cp .env.example .env
```
> **注意**: 默认配置已包含必要的浏览器指纹 (`FP`) 和动态脚本 URL (`SCRIPT_URL`)，通常无需修改即可运行。

**2. 使用 Docker Compose 启动**

```bash
docker-compose up -d
```

服务现在已在 `http://localhost:8000` 上运行。你可以通过修改 `docker-compose.yml` 来更改端口。

---

## 🔧 配置 (环境变量)

你可以在 `docker-compose.yml` 或 `.env` 文件中配置以下环境变量：

| 环境变量 | 说明 | 默认值 (示例) |
| :--- | :--- | :--- |
| `API_KEY` | 用于保护你的 API 接口的认证密钥。**强烈建议修改为一个安全的随机字符串**。 | `aaa` |
| `MODELS` | 指定 API 支持的模型列表，以逗号分隔。 | `gpt-4o,claude-3.5-sonnet,...` |
| `FP` | Base64 编码的浏览器指纹。用于绕过 Cloudflare 检测。 | 一个预设的 Base64 字符串 |
| `SCRIPT_URL`| Cursor 用于生成 `x-is-human` 头的动态 JS 文件 URL。此 URL 可能会变动。| 一个预设的 URL |

### 如何更新 `FP` 和 `SCRIPT_URL`?

如果项目因 Cloudflare 防护更新而无法工作，你可能需要手动更新 `FP` 和 `SCRIPT_URL`。

1.  **获取 `FP` (浏览器指纹)**:
    *   在 Chrome 或 Edge 浏览器中访问 `https://cursor.com`。
    *   打开开发者工具 (F12)，在控制台 (Console) 中粘贴并执行以下代码。
    *   将输出的 Base64 字符串设置为 `FP` 的值。

    ```javascript
    function getBrowserFingerprint() {
        const canvas = document.createElement('canvas');
        const gl = canvas.getContext('webgl') || canvas.getContext('experimental-webgl');
        let unmaskedVendor = '', unmaskedRenderer = '';
        if (gl) {
            const debugInfo = gl.getExtension('WEBGL_debug_renderer_info');
            if (debugInfo) {
                unmaskedVendor = gl.getParameter(debugInfo.UNMASKED_VENDOR_WEBGL) || '';
                unmaskedRenderer = gl.getParameter(debugInfo.UNMASKED_RENDERER_WEBGL) || '';
            }
        }
        const fingerprint = {
            "UNMASKED_VENDOR_WEBGL": unmaskedVendor,
            "UNMASKED_RENDERER_WEBGL": unmaskedRenderer,
            "userAgent": navigator.userAgent
        };
        return btoa(JSON.stringify(fingerprint));
    }
    console.log(getBrowserFingerprint());
    ```

2.  **获取 `SCRIPT_URL`**:
    *   在 Chrome 或 Edge 浏览器中访问 `https://cursor.com`。
    *   打开开发者工具 (F12)，切换到网络 (Network) 标签页。
    *   刷新页面，在筛选框中输入 `c.js` 或类似的关键词，找到一个类似 `.../a-4-a/c.js?i=0&v=3...` 的请求，复制其完整的 URL。

---

## ▶️ 使用示例

### 基础聊天 (Python)

```python
import openai

client = openai.OpenAI(
    base_url="http://localhost:8000/v1",
    api_key="aaa"  # 替换为你的 API_KEY
)

completion = client.chat.completions.create(
    model="claude-3.5-sonnet", # 选择一个支持的模型
    messages=[
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "你好，请用中文介绍一下你自己。"}
    ]
)

print(completion.choices[0].message.content)
```

### 工具调用 (Tool Calling)

```python
import openai
import json

client = openai.OpenAI(
    base_url="http://localhost:8000/v1",
    api_key="aaa"  # 替换为你的 API_KEY
)

tools = [
    {
        "type": "function",
        "function": {
            "name": "get_current_weather",
            "description": "Get the current weather in a given location",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {"type": "string", "description": "The city and state, e.g. San Francisco, CA"},
                    "unit": {"type": "string", "enum": ["celsius", "fahrenheit"]}
                },
                "required": ["location"]
            }
        }
    }
]

response = client.chat.completions.create(
    model="gpt-4o",
    messages=[{"role": "user", "content": "波士顿现在天气怎么样？"}],
    tools=tools,
    tool_choice="auto"
)

# 检查模型是否决定调用工具
tool_calls = response.choices[0].message.tool_calls
if tool_calls:
    print("模型建议调用工具：")
    for tool_call in tool_calls:
        function_name = tool_call.function.name
        function_args = json.loads(tool_call.function.arguments)
        print(f"- 函数: {function_name}")
        print(f"- 参数: {function_args}")
```

---

## 🤖 支持的模型

本项目通过 `MODELS` 环境变量来配置支持的模型列表。默认已包含以下常用模型，你可以按需增删：

- `gpt-5`, `gpt-5-codex`
- `gpt-4o`, `gpt-4.1`
- `claude-3.5-sonnet`, `claude-3.5-haiku`
- `claude-4-sonnet`, `claude-4-opus`
- `gemini-2.5-pro`
- `deepseek-r1`, `deepseek-v3.1`
- `grok-3`, `grok-4`
- ... 以及更多

你可以通过 `GET /v1/models` 端点查询当前服务支持的所有模型。

---

## 📄 许可证

本项目采用 MIT 许可证 - 查看 [LICENSE](./LICENSE) 文件了解详情。

---

## ⚠️ 免责声明

- 本项目与 Cursor AI 提供商官方无关
- 使用前请确保遵守各提供商的服务条款
- 请勿用于商业用途或违反使用条款的场景
- 项目仅供学习和研究使用
- 用户需自行承担使用风险