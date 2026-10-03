FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
RUN useradd -m app
WORKDIR /home/app/src
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
USER app
RUN mkdir -p /home/app/.data
HEALTHCHECK --interval=60s --timeout=5s --start-period=60s \
  CMD python -c "import urllib.request,os;urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"HEALTH_PORT\",\"8080\")}/health',timeout=4)"
ENTRYPOINT ["python", "-m", "app"]
CMD ["run"]
