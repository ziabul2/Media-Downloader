FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 --shell /usr/sbin/nologin zim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN chmod +x /app/deployment/entrypoint.sh \
    && mkdir -p /var/lib/zim \
    && chown -R zim:zim /app /var/lib/zim

USER zim
EXPOSE 8000
ENTRYPOINT ["/app/deployment/entrypoint.sh"]
