import json
import os
import shutil
import subprocess
import tempfile
import time
from typing import Optional

from curl_cffi import AsyncSession, Response
from fastapi import FastAPI, Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from loguru import logger

from app.config import SCRIPT_URL, FP, API_KEY, MODELS
from app.errors import CursorWebError
from app.models import ChatCompletionRequest, Message, ModelsResponse, Model
from app.utils import error_wrapper, to_async, generate_random_string, non_stream_chat_completion, \
    stream_chat_completion, safe_stream_wrapper

main_code = open('./jscode/main.js', 'r', encoding='utf-8').read()
env_code = open('./jscode/env.js', 'r', encoding='utf-8').read()
app = FastAPI()

security = HTTPBearer()


@app.post("/v1/chat/completions")
async def chat_completions(
        request: ChatCompletionRequest,
        credentials: HTTPAuthorizationCredentials = Depends(security),
):
    """处理聊天完成请求"""

    if credentials.credentials != API_KEY:
        raise HTTPException(401, 'api key 错误')

    chat_generator = cursor_chat(request)
    # async for c in chat_generator:
    #     logger.debug(c)

    if request.stream:
        return await error_wrapper(safe_stream_wrapper, stream_chat_completion, request, chat_generator)
    else:
        return await error_wrapper(non_stream_chat_completion, request, chat_generator)


@app.get("/v1/models")
async def list_models(credentials: HTTPAuthorizationCredentials = Depends(security)):
    models = MODELS.split(',')
    model_list = []

    for model_id in models:
        model_list.append(
            Model(
                id=model_id,  # 使用model name作为对外的id
                object="model",
                created=int(time.time()),
                owned_by='',
            )
        )

    return ModelsResponse(object="list", data=model_list)


def to_cursor_messages(list_openai_message: list[Message]):
    if list_openai_message is None:
        list_openai_message = []

    result = []
    for m in list_openai_message:
        if not m:
            continue
        text = ''
        if isinstance(m.content, str):
            text = m.content
        else:
            for content in m.content:
                if not content.text:
                    continue
                text = text + content.text
        message = {
            'role': m.role,
            'parts': [{
                'type': 'text',
                'text': text
            }]
        }
        result.append(message)

    return result


def parse_sse_line(line: str) -> Optional[str]:
    """解析SSE数据行"""
    line = line.strip()
    if line.startswith("data: "):
        return line[6:]  # 去掉 'data: ' 前缀
    return None


async def cursor_chat(request: ChatCompletionRequest):
    json_data = {
        "context": [

        ],
        "model": request.model,
        "id": generate_random_string(16),
        "messages": to_cursor_messages(request.messages),
        "trigger": "submit-message"
    }

    # 添加工具相关参数
    if request.tools is not None:
        json_data["tools"] = [tool.dict() for tool in request.tools]
    if request.tool_choice is not None:
        json_data["tool_choice"] = request.tool_choice
    async with AsyncSession(impersonate='chrome') as session:
        x_is_human = await get_x_is_human(session)
        logger.debug(x_is_human)
        headers = {
            'User-Agent': FP.get("userAgent"),
            # 'Accept-Encoding': 'gzip, deflate, br, zstd',
            'Content-Type': 'application/json',
            'sec-ch-ua-platform': '"Windows"',
            'x-path': '/api/chat',
            'sec-ch-ua': '"Chromium";v="140", "Not=A?Brand";v="24", "Google Chrome";v="140"',
            'x-method': 'POST',
            'sec-ch-ua-bitness': '"64"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-arch': '"x86"',
            'x-is-human': x_is_human,
            'sec-ch-ua-platform-version': '"19.0.0"',
            'origin': 'https://cursor.com',
            'sec-fetch-site': 'same-origin',
            'sec-fetch-mode': 'cors',
            'sec-fetch-dest': 'empty',
            'referer': 'https://cursor.com/en-US/learn/how-ai-models-work',
            'accept-language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'priority': 'u=1, i',
        }
        async with session.stream("POST", 'https://cursor.com/api/chat', headers=headers, json=json_data,
                                  impersonate='chrome') as response:
            response: Response
            if response.status_code != 200:
                text = await response.atext()
                if 'Attention Required! | Cloudflare' in text:
                    text = 'Cloudflare 403'
                raise CursorWebError(response.status_code, text)
            async for line in response.aiter_lines():
                line = line.decode("utf-8")
                data = parse_sse_line(line)
                if not data:
                    continue
                if data and data.strip():
                    try:
                        event_data = json.loads(data)
                        delta = event_data.get('delta')
                        # logger.debug(delta)
                        if not delta:
                            continue
                        yield delta
                    except json.JSONDecodeError:
                        continue


async def get_x_is_human(session: AsyncSession):
    headers = {
        'User-Agent': FP.get("userAgent"),
        # 'Accept-Encoding': 'gzip, deflate, br, zstd',
        'sec-ch-ua-arch': '"x86"',
        'sec-ch-ua-platform': '"Windows"',
        'sec-ch-ua': '"Chromium";v="140", "Not=A?Brand";v="24", "Google Chrome";v="140"',
        'sec-ch-ua-bitness': '"64"',
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform-version': '"19.0.0"',
        'sec-fetch-site': 'same-origin',
        'sec-fetch-mode': 'no-cors',
        'sec-fetch-dest': 'script',
        'referer': 'https://cursor.com/en-US/learn/how-ai-models-work',
        'accept-language': 'zh-CN,zh;q=0.9,en;q=0.8',
    }

    response = await session.get(SCRIPT_URL,
                                 headers=headers,
                                 impersonate='chrome')
    cursor_js = response.text

    # 替换指纹
    main = (main_code.replace("$$currentScriptSrc$$", SCRIPT_URL)
            .replace("$$UNMASKED_VENDOR_WEBGL$$", FP.get("UNMASKED_VENDOR_WEBGL"))
            .replace("$$UNMASKED_RENDERER_WEBGL$$", FP.get("UNMASKED_RENDERER_WEBGL"))
            .replace("$$userAgent$$", FP.get("userAgent")))

    # 替换代码
    main = main.replace('$$env_jscode$$', env_code)
    main = main.replace("$$cursor_jscode$$", cursor_js)
    return await runjs(main)


@to_async
def runjs(jscode: str) -> str:
    """
    执行 JavaScript 代码并返回标准输出内容。

    Args:
        jscode: 要执行的 JavaScript 代码字符串

    Returns:
        Node.js 程序的标准输出内容

    Raises:
        FileNotFoundError: Node.js 未安装或不在系统 PATH 中
        subprocess.CalledProcessError: Node.js 程序执行失败，异常信息包含 stdout 和 stderr
    """
    temp_dir = tempfile.mkdtemp()
    try:
        js_file_path = os.path.join(temp_dir, "script.js")
        with open(js_file_path, "w", encoding="utf-8") as f:
            f.write(jscode)

        result = subprocess.run(
            ['node', js_file_path],
            capture_output=True,
            text=True,
            encoding="utf-8"
        )

        if result.returncode != 0:
            error_msg = f"Node.js 执行失败 (退出码: {result.returncode})\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
            logger.error(error_msg)
            raise subprocess.CalledProcessError(result.returncode, ['node', js_file_path], result.stdout, result.stderr)

        return result.stdout.strip()
    finally:
        shutil.rmtree(temp_dir)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
        log_level="info",
    )
