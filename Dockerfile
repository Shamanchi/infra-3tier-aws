FROM python:3.11-slim AS base
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY examples ./examples
RUN useradd -m appuser && chown -R appuser:appuser /app
USER appuser
ENTRYPOINT ["python", "-m", "app.main"]
CMD ["validate", "--file", "examples/topology.json"]

FROM base AS dev
CMD ["validate", "--file", "examples/topology.json"]
