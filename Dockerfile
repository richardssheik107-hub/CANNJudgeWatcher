FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && useradd --uid 10001 --create-home watcher && mkdir /data && chown watcher /data
COPY watcher ./watcher
COPY web ./web
COPY config ./config
USER watcher
ENV PYTHONUNBUFFERED=1
VOLUME ["/data"]
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health',timeout=4)"
CMD ["python","-m","watcher","--db","/data/live.sqlite3","serve","--host","0.0.0.0","--port","8080","--poll"]
