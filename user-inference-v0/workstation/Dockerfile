ARG DJRMCP_BASE_IMAGE=ubuntu:24.04
FROM ${DJRMCP_BASE_IMAGE}

ARG DJRMCP_UID=1000
ARG DJRMCP_GID=1000

ENV DEBIAN_FRONTEND=noninteractive \
    HOME=/work \
    PATH=/opt/djrmcp-venv/bin:${PATH} \
    HF_HOME=/models/huggingface \
    HF_HUB_DISABLE_TELEMETRY=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONUNBUFFERED=1 \
    TOKENIZERS_PARALLELISM=false

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        git \
        python3 \
        python3-pip \
        python3-venv \
    && rm -rf /var/lib/apt/lists/* \
    && python3 -m venv /opt/djrmcp-venv \
    && group_name="$(getent group "${DJRMCP_GID}" | cut -d: -f1 || true)" \
    && if [ -z "${group_name}" ]; then \
        group_name=djrmcp; \
        groupadd --gid "${DJRMCP_GID}" "${group_name}"; \
    fi \
    && if getent passwd "${DJRMCP_UID}" >/dev/null; then \
        echo "Reusing base-image account with UID ${DJRMCP_UID}"; \
    else \
        useradd --uid "${DJRMCP_UID}" --gid "${group_name}" --home-dir /work --no-create-home djrmcp; \
    fi \
    && mkdir -p /input /models/huggingface /work \
    && chown -R "${DJRMCP_UID}:${DJRMCP_GID}" /input /models /work

WORKDIR /opt/djrmcp

COPY pyproject.toml README.md ./

# These are the frozen workstation core versions. The Transformers git commit is
# also verified at runtime through its installed direct_url.json metadata.
RUN python -m pip install --upgrade "setuptools==83.0.0" "wheel==0.47.0" \
    && python -m pip install "numpy==2.5.1" "torch==2.13.0" \
    && python -m pip install \
        "git+https://github.com/Biohub/transformers.git@ef32577f55da19a4989cd7b22e004dc43a4998cb"

COPY src ./src

RUN python -m pip install --no-deps . \
    && python -m pip check \
    && djrmcp-predict model-info >/dev/null

USER ${DJRMCP_UID}:${DJRMCP_GID}

ENTRYPOINT ["djrmcp-predict"]
CMD ["--help"]
