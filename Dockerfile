FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && useradd --uid 10001 --create-home arena \
    && mkdir /app/data && chown arena:arena /app/data
COPY arena ./arena
COPY static ./static
USER arena
EXPOSE 5200
HEALTHCHECK --interval=15s --timeout=3s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:5200/health',timeout=2)"
CMD ["python","-m","uvicorn","arena.app:create_app","--factory","--host","0.0.0.0","--port","5200","--no-access-log"]
