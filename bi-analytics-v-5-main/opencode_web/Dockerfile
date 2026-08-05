FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive
ARG OPENCODE_VERSION=1.18.13
ENV PATH="/root/.opencode/bin:/opt/pytools/bin:${PATH}"

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl git bash unzip python3 python3-pip python3-venv \
  && ln -sf /usr/bin/python3 /usr/bin/python \
  && python3 -m venv /opt/pytools \
  && /opt/pytools/bin/pip install --no-cache-dir --upgrade pip \
  && /opt/pytools/bin/pip install --no-cache-dir pandas matplotlib \
  && rm -rf /var/lib/apt/lists/*

RUN curl -fsSL https://opencode.ai/install -o /tmp/install-opencode.sh \
  && bash /tmp/install-opencode.sh --version "${OPENCODE_VERSION}" \
  && opencode --version | grep -Fx "${OPENCODE_VERSION}" \
  && rm -f /tmp/install-opencode.sh

ENV OPENCODE_PORT=4096
ENV OPENCODE_HOST=0.0.0.0
ENV XCA_WORKSPACE_DIR=/workspace
ENV OPENCODE_CONFIG=/workspace/opencode.json
ENV OPENCODE_DISABLE_DEFAULT_PLUGINS=true

RUN mkdir -p /workspace /var/log

COPY opencode_entrypoint.sh /usr/local/bin/opencode_entrypoint.sh
RUN chmod +x /usr/local/bin/opencode_entrypoint.sh

WORKDIR /workspace
COPY workspace /workspace
COPY AI_ASSISTANT_RULES.md /workspace/AI_ASSISTANT_RULES.md

EXPOSE 4096
HEALTHCHECK --interval=15s --timeout=5s --start-period=30s --retries=5 \
  CMD curl -fsS http://127.0.0.1:4096/global/health || exit 1

CMD ["bash", "-lc", "opencode_entrypoint.sh"]
