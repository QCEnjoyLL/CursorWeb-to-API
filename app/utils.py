import asyncio
import base64
import json
import random
import re
import string
import time
import uuid
from functools import wraps
from typing import Union, Callable, Any, AsyncGenerator, Dict, Optional, List

from curl_cffi.requests.exceptions import RequestException
from sse_starlette import EventSourceResponse
from starlette.responses import JSONResponse

from app.errors import CursorWebError
from app.models import ChatCompletionRequest, OpenAIToolCallFunction


async def safe_stream_wrapper(
        generator_func, *args, **kwargs
) -> Union[EventSourceResponse, JSONResponse]:
    """
    安全的流响应包装器
    先执行生成器获取第一个值，如果成功才创建流响应
    """
    # 创建生成器实例
    generator = generator_func(*args, **kwargs)

    # 尝试获取第一个值
    first_item = await generator.__anext__()

    # 如果成功获取第一个值，创建新的生成器包装原生成器
    async def wrapped_generator():
        # 先yield第一个值
        yield first_item
        # 然后yield剩余的值
        async for item in generator:
            yield item

    # 创建流响应
    return EventSourceResponse(
        wrapped_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


async def error_wrapper(func: Callable, *args, **kwargs) -> Any:
    from .config import MAX_RETRIES
    for attempt in range(MAX_RETRIES + 1):  # 包含初始尝试，所以是 MAX_RETRIES + 1
        try:
            return await func(*args, **kwargs)
        except (CursorWebError, RequestException) as e:

            # 如果已经达到最大重试次数，返回错误响应
            if attempt == MAX_RETRIES:
                if isinstance(e, CursorWebError):
                    return JSONResponse(
                        e.to_openai_error(),
                        status_code=e.response_status_code
                    )
                elif isinstance(e, RequestException):
                    return JSONResponse(
                        {
                            'error': {
                                'message': str(e),
                                "type": "http_error",
                                "code": "http_error"
                            }
                        },
                        status_code=500
                    )

            if attempt < MAX_RETRIES:
                continue
    return None


def decode_base64url_safe(data):
    """使用安全的base64url解码"""
    # 添加必要的填充
    missing_padding = len(data) % 4
    if missing_padding:
        data += '=' * (4 - missing_padding)

    return base64.urlsafe_b64decode(data)


def to_async(sync_func):
    @wraps(sync_func)
    async def async_wrapper(*args):
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, sync_func, *args)

    return async_wrapper


def generate_random_string(length):
    """
    生成一个指定长度的随机字符串，包含大小写字母和数字。
    """
    # 定义所有可能的字符：大小写字母和数字
    characters = string.ascii_letters + string.digits

    # 使用 random.choice 从字符集中随机选择字符，重复 length 次，然后拼接起来
    random_string = ''.join(random.choice(characters) for _ in range(length))
    return random_string


async def non_stream_chat_completion(
        request: ChatCompletionRequest,
        generator: AsyncGenerator[str, None]
) -> Dict[str, Any]:
    """
    非流式响应：接受外部异步生成器，收集所有输出返回完整响应
    """
    # 收集所有流式输出
    full_content = ""
    full_delta = ""  # 用于累积SSE数据来检测工具调用

    async for chunk in generator:
        full_content += chunk
        full_delta += chunk if chunk else ""

    # 检查是否包含工具调用
    tool_calls = extract_tool_calls_from_response(full_delta)

    if tool_calls:
        # 返回工具调用格式响应
        response = create_tool_call_response({
            "model": request.model,
            "input_tokens": 0,
            "output_tokens": 0
        }, tool_calls)
    else:
        # 构造OpenAI格式的普通响应
        response = {
            "id": f"chatcmpl-{uuid.uuid4().hex[:29]}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": request.model,
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": full_content
                    },
                    "finish_reason": "stop"
                }
            ],
            "usage": {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0
            }
        }

    return response


async def stream_chat_completion(
        request: ChatCompletionRequest,
        generator: AsyncGenerator[str, None]
) -> AsyncGenerator[Dict[str, Any], None]:
    """
    流式响应：接受外部异步生成器，包装成OpenAI SSE格式
    """
    chat_id = f"chatcmpl-{uuid.uuid4().hex[:29]}"
    created_time = int(time.time())

    is_send_init = False

    # 初始化工具调用内容
    full_delta = ""

    # 检查是否有工具调用内容，但不立即发送初始响应
    async for chunk in generator:
        full_delta += chunk if chunk else ""

        # 检查是否有工具调用内容
        tool_calls = extract_tool_calls_from_response(full_delta)

        if tool_calls:
            # 如果检测到工具调用，则发送工具调用的流式响应
            for i, tool_call in enumerate(tool_calls):
                # 发送工具调用数据，索引对应tools列表中的索引
                tool_chunk = create_sse_tool_call_chunk(i, tool_call, is_complete=(i == len(tool_calls) - 1))
                yield tool_chunk

            # 发送结束标记
            final_response = {
                "id": chat_id,
                "object": "chat.completion.chunk",
                "created": created_time,
                "model": request.model,
                "choices": [
                    {
                        "index": 0,
                        "delta": {},
                        "finish_reason": "tool_calls"
                    }
                ]
            }
            yield {"data": json.dumps(final_response, ensure_ascii=False)}
            yield {"data": "[DONE]"}
            return

        # 如果不是工具调用，发送普通内容
        if not is_send_init:
            initial_response = {
                "id": chat_id,
                "object": "chat.completion.chunk",
                "created": created_time,
                "model": request.model,
                "choices": [
                    {
                        "index": 0,
                        "delta": {"role": "assistant", "content": ""},
                        "finish_reason": None
                    }
                ]
            }
            yield {
                "data": json.dumps(initial_response, ensure_ascii=False)
            }
            is_send_init = True

        chunk_response = {
            "id": chat_id,
            "object": "chat.completion.chunk",
            "created": created_time,
            "model": request.model,
            "choices": [
                {
                    "index": 0,
                    "delta": {"content": chunk},
                    "finish_reason": None
                }
            ]
        }
        yield {"data": json.dumps(chunk_response, ensure_ascii=False)}

    # 发送结束标记
    final_response = {
        "id": chat_id,
        "object": "chat.completion.chunk",
        "created": created_time,
        "model": request.model,
        "choices": [
            {
                "index": 0,
                "delta": {},
                "finish_reason": "stop"
            }
        ]
    }
    yield {"data": json.dumps(final_response, ensure_ascii=False)}
    yield {"data": "[DONE]"}


def parse_tool_call_from_content(content: str) -> Optional[Dict]:
    """
    从响应内容中识别和解析工具调用
    支持JSON代码块格式及直接工具调用格式
    """
    try:
        # 检查JSON代码块格式的工具调用（更快，先检查）
        if '```' in content:
            # 匹配更具体，查找工具调用相关的JSON代码块
            json_match = re.search(
                r'```(?:json|JSON)?\s*\n*(\{.*?"name".*?"arguments".*?\})\s*\n*```',
                content,
                re.DOTALL
            )
            if json_match:
                try:
                    tool_data = json.loads(json_match.group(1))
                    if isinstance(tool_data, dict) and 'name' in tool_data and 'arguments' in tool_data:
                        return tool_data
                except (json.JSONDecodeError, IndexError):
                    pass

        # 检查内联JSON格式（只在有基本关键词时检查以提高性能）
        # 更精确地匹配工具调用结构
        if ('"name"' in content and '"arguments"' in content):
            # 尝试查找第一个可能的完整JSON对象（带合理的大小限制，防止正则复杂度过高）
            # 在工具调用中通常JSON结构不会太复杂，所以限制搜索范围
            start_pos = content.find('{"name"')
            if start_pos != -1:
                # 找到可能的起始点，尝试查找对应的结束
                end_pos = start_pos
                level = 0
                in_string = False
                escape_next = False

                # 自行解析对象边界，而不用复杂的正则
                for i in range(start_pos, min(start_pos + 1000, len(content))):  # 限制搜索范围
                    char = content[i]
                    if escape_next:
                        escape_next = False
                        continue
                    if char == '\\':
                        escape_next = True
                    elif char == '"' and not escape_next:
                        in_string = not in_string
                    elif not in_string:
                        if char == '{':
                            level += 1
                        elif char == '}':
                            level -= 1
                            if level == 0:
                                end_pos = i + 1
                                break

                if end_pos > start_pos:
                    potential_json = content[start_pos:end_pos]
                    try:
                        tool_data = json.loads(potential_json)
                        if isinstance(tool_data, dict) and 'name' in tool_data and 'arguments' in tool_data:
                            return tool_data
                    except json.JSONDecodeError:
                        pass
    except Exception:
        # 如果解析过程中出现任何错误，返回None
        pass

    return None


def extract_tool_calls_from_response(content: str) -> Optional[List[Dict]]:
    """
    从响应内容中提取工具调用信息
    按照OpenAI标准格式返回
    """
    try:
        # 快速检查是否可能存在工具调用（避免不必要的处理）
        if not ('function_call' in content or ('name' in content and 'arguments' in content)):
            return None

        tool_calls = []

        tool_data = parse_tool_call_from_content(content)
        if tool_data and 'name' in tool_data:
            try:
                tool_call_id = f"call_{str(uuid.uuid4())[:8]}"
                arguments = tool_data.get('arguments', {})
                # 确保arguments是字符串，如果不是则序列化
                if not isinstance(arguments, str):
                    arguments = json.dumps(arguments)

                tool_call = {
                    "id": tool_call_id,
                    "type": "function",
                    "function": {
                        "name": tool_data['name'],
                        "arguments": arguments
                    }
                }
                tool_calls.append(tool_call)
            except Exception:
                # 如果在构建工具调用时发生错误，跳过这个工具调用
                pass

        return tool_calls if tool_calls else None
    except Exception:
        # 如果在处理过程中出现任何错误，返回None
        return None


def create_tool_call_response(message_data: Dict, tool_calls: List[Dict]) -> Dict:
    """
    创建符合OpenAI标准的工具调用响应格式
    """
    return {
        "id": f"chatcmpl-{str(uuid.uuid4())[:8]}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": message_data.get("model", "default-model"),
        "choices": [{
            "index": 0,
            "message": {
                "role": "assistant",
                "content": None,
                "tool_calls": tool_calls
            },
            "finish_reason": "tool_calls"
        }],
        "usage": {
            "prompt_tokens": message_data.get("input_tokens", 0),
            "completion_tokens": message_data.get("output_tokens", 0),
            "total_tokens": message_data.get("input_tokens", 0) +
                           message_data.get("output_tokens", 0)
        }
    }


def create_sse_tool_call_chunk(index: int, tool_call_data: Dict, is_complete: bool = False) -> Dict:
    """
    创建符合OpenAI标准的SSE工具调用响应格式
    """
    chunk = {
        "id": f"chatcmpl-{str(uuid.uuid4())[:8]}",
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": "default-model",
        "choices": [{
            "index": index,
            "delta": {
                "tool_calls": [{
                    "index": 0,
                    "id": tool_call_data.get("id"),
                    "function": {
                        "name": tool_call_data.get("name"),
                        "arguments": tool_call_data.get("arguments", "")
                    },
                    "type": "function"
                }]
            },
            "finish_reason": "tool_calls" if is_complete else None
        }]
    }
    return {"data": json.dumps(chunk, ensure_ascii=False)}
