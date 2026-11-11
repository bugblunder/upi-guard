FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 OMP_NUM_THREADS=1
WORKDIR /app
COPY requirements.lock .
RUN pip install --no-cache-dir -r requirements.lock && useradd --create-home --uid 10001 guard
COPY --chown=guard:guard . .
RUN mkdir -p /app/instance && chown guard:guard /app/instance
USER guard
EXPOSE 5000
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:5000/health/ready',timeout=3)"
CMD ["gunicorn","--bind","0.0.0.0:5000","--workers","2","--timeout","60","--access-logfile","-","wsgi:app"]
