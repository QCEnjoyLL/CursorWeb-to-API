FROM ghcr.io/astral-sh/uv:python3.12-alpine

# 安装node
RUN apk add --no-cache nodejs npm

# 复制当前目录所有内容到 /app
COPY . /app

# 设置工作目录
WORKDIR /app

# 执行 uv sync 命令
RUN uv sync

EXPOSE 8000

# 启动 uv 运行 main.py
CMD ["uv", "run", "main.py"]