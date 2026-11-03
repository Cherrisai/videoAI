FROM node:22-bookworm-slim AS mcp-runtime
RUN npm install --global @brave/brave-search-mcp-server@2.1.4

FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app
COPY --from=mcp-runtime /usr/local/bin/node /usr/local/bin/node
COPY --from=mcp-runtime /usr/local/bin/brave-search-mcp-server /usr/local/bin/brave-search-mcp-server
COPY --from=mcp-runtime /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
RUN useradd --create-home appuser && mkdir -p /data && chown -R appuser:appuser /app /data
USER appuser
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
