FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt && useradd --uid 10001 --create-home gridraft
COPY gridraft ./gridraft
COPY public ./public
COPY scripts/check_openbroker.py scripts/check_connections.py ./scripts/
RUN mkdir -p /app/data && chown -R gridraft:gridraft /app/data
USER gridraft
EXPOSE 8000
CMD ["python","-m","uvicorn","gridraft.main:app","--host","0.0.0.0","--port","8000","--workers","1","--no-access-log","--no-proxy-headers"]
