import inspect

from loguru import logger


class CursorWebError(Exception):
    def __init__(self, status_code: int, message: str, response_status_code: int = 500):
        self.status_code = status_code
        self.message = message
        self.response_status_code = response_status_code
        # 获取调用者信息
        frame = inspect.currentframe()
        try:
            caller_frame = frame.f_back  # 上一层调用栈
            if caller_frame:
                filename = caller_frame.f_code.co_filename
                line_number = caller_frame.f_lineno
                function_name = caller_frame.f_code.co_name
                logger.error(f"{self.__str__()} - Called from {filename}:{line_number} in {function_name}")
            else:
                logger.error(self.__str__())
        finally:
            del frame  # 避免循环引用

    def __str__(self) -> str:
        return f"CursorWebError: {self.status_code}, {self.message}"

    def to_openai_error(self) -> dict[str, dict[str, str]]:
        return {
            "error": {
                "message": self.__str__(),
                "type": "cursorweb_error",
                "code": "cursorweb_error"
            }
        }
