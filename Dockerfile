FROM python:3.12.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONPATH=/app/src

RUN groupadd --gid 10001 formulawitness \
    && useradd --uid 10001 --gid formulawitness --create-home formulawitness

WORKDIR /app
COPY requirements-runtime-lock.txt pyproject.toml README.md ./
RUN python -m pip install --no-cache-dir -r requirements-runtime-lock.txt

COPY src ./src
COPY artifacts/submission ./artifacts/submission
COPY evals/results.json ./evals/results.json
COPY policies ./policies
COPY workbooks ./workbooks
RUN python -m pip install --no-cache-dir --no-deps . \
    && mkdir -p /tmp/formulawitness \
    && chown -R formulawitness:formulawitness /tmp/formulawitness

USER 10001:10001
EXPOSE 10000

CMD ["python", "-m", "formulawitness.deploy"]
