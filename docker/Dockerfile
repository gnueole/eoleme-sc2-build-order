FROM python:3.12-slim

WORKDIR /app

# Dependencies first: they change far less often than the code, so this layer
# stays cached from one build to the next.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY sc2bo ./sc2bo
COPY server.py .
COPY public ./public
COPY VERSION .

# The service only reads and writes temporary files: it runs unprivileged.
RUN useradd --create-home --uid 10001 forge && chown -R forge:forge /app
USER forge

EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=4s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:3000/api/health', timeout=3).status == 200 else 1)"

CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "3000"]
