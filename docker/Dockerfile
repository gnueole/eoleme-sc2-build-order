FROM python:3.12-slim

WORKDIR /app

# Les dépendances d'abord : elles changent bien moins souvent que le code,
# et cette couche reste alors en cache d'un build à l'autre.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY sc2bo ./sc2bo
COPY server.py .
COPY public ./public
COPY VERSION .

# Le service ne lit et n'écrit que des fichiers temporaires : il tourne sans privilèges.
RUN useradd --create-home --uid 10001 forge && chown -R forge:forge /app
USER forge

EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=4s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:3000/api/health', timeout=3).status == 200 else 1)"

CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "3000"]
