
FROM python:3.10-slim as base
LABEL maintainer="AI Innovation Team"
LABEL version="1.0.0"
LABEL description="AutoGen AI Code Correction Agent - Proprietary IP"
LABEL license="Proprietary"
LABEL vendor="Your Company"
WORKDIR /app
RUN useradd --create-home --shell /bin/bash appuser && \
    chown -R appuser:appuser /app

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    git \
    ca-certificates \
    curl \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

ENV GIT_PYTHON_GIT_EXECUTABLE=/usr/bin/git
COPY --chown=appuser:appuser requirements.txt /app/


RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt
COPY --chown=appuser:appuser . /app/
RUN mkdir -p /app/downloads /app/repo /app/logs && \
    chown -R appuser:appuser /app
RUN chmod +x /app/entrypoint.sh
USER appuser
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import autogen, openai; print('Agent dependencies OK')" || exit 1
EXPOSE 8080
ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["python", "autogen_agent.py"]