ARG BASE_IMAGE=djrmcp-user-inference:v0
FROM ${BASE_IMAGE}

ARG DJRMCP_UID=1000
ARG DJRMCP_GID=1000

# V0.1 deliberately reuses the already validated V0 CUDA/PyTorch/NumPy and
# ESM-C environment. Only the incompatible ESM-2 Transformers distribution is
# added in a small overlay venv; its .pth entry shares the V0 core libraries.
USER root

# Triton compiles a small CUDA launcher on the first ESM-2 forward pass.
# The compiler and Python headers are runtime requirements, not build-only
# conveniences, so keep them in the final derived image.
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential python3-dev \
    && rm -rf /var/lib/apt/lists/*

ENV DJRMCP_ESM2_PYTHON=/opt/djrmcp-esm2/bin/python \
    DJRMCP_ESMC_PYTHON=/opt/djrmcp-venv/bin/python \
    HOME=/work \
    PATH=/opt/djrmcp-esm2/bin:${PATH}

WORKDIR /opt/djrmcp-v01
COPY pyproject.toml README.md ./

RUN python3 -m venv /opt/djrmcp-esm2 \
    && printf '%s\n' '/opt/djrmcp-venv/lib/python3.12/site-packages' \
        > /opt/djrmcp-esm2/lib/python3.12/site-packages/djrmcp-core.pth \
    && /opt/djrmcp-esm2/bin/python -c \
        'import setuptools, wheel; assert setuptools.__version__ == "83.0.0"; assert wheel.__version__ == "0.47.0"' \
    && /opt/djrmcp-esm2/bin/python -m pip install \
        "annotated-doc==0.0.5" \
        "anyio==4.14.2" \
        "click==8.4.2" \
        "h11==0.16.0" \
        "httpcore==1.0.9" \
        "httpx==0.28.1" \
        "huggingface-hub==1.25.1" \
        "markdown-it-py==4.2.0" \
        "mdurl==0.1.2" \
        "pygments==2.20.0" \
        "rich==15.0.0" \
        "shellingham==1.5.4" \
        "transformers==5.14.1" \
        "typer==0.27.0"

COPY src ./src

RUN /opt/djrmcp-esm2/bin/python -m pip install --no-build-isolation --no-deps . \
    && /opt/djrmcp-venv/bin/python -m pip install --no-build-isolation --no-deps . \
    && /opt/djrmcp-esm2/bin/python -m pip check \
    && /opt/djrmcp-venv/bin/python -m pip check \
    && /opt/djrmcp-esm2/bin/python -c \
        'import numpy, torch, transformers; assert numpy.__version__ == "2.5.1"; assert torch.__version__.split("+")[0] == "2.13.0"; assert torch.version.cuda == "13.0"; assert transformers.__version__ == "5.14.1"; assert transformers.__file__.startswith("/opt/djrmcp-esm2/"); assert numpy.__file__.startswith("/opt/djrmcp-venv/"); assert torch.__file__.startswith("/opt/djrmcp-venv/")' \
    && /opt/djrmcp-venv/bin/python -c \
        'import json; from importlib import metadata; import numpy, torch, transformers; assert numpy.__version__ == "2.5.1"; assert torch.__version__.split("+")[0] == "2.13.0"; assert torch.version.cuda == "13.0"; assert transformers.__version__ == "4.57.6"; assert numpy.__file__.startswith("/opt/djrmcp-venv/"); assert torch.__file__.startswith("/opt/djrmcp-venv/"); assert transformers.__file__.startswith("/opt/djrmcp-venv/"); payload=json.loads(metadata.distribution("transformers").read_text("direct_url.json")); assert payload["vcs_info"]["commit_id"] == "ef32577f55da19a4989cd7b22e004dc43a4998cb"' \
    && /opt/djrmcp-esm2/bin/djrmcp-predict-v01 model-info >/dev/null \
    && mkdir -p /models/huggingface /work \
    && chown -R "${DJRMCP_UID}:${DJRMCP_GID}" /models/huggingface /work

USER ${DJRMCP_UID}:${DJRMCP_GID}

ENTRYPOINT ["/opt/djrmcp-esm2/bin/djrmcp-predict-v01"]
CMD ["--help"]
