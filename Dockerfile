FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Build deps for native Python wheels that don't ship binaries for our
# platform. ``pycairo`` is pulled in transitively by xhtml2pdf →
# svglib → rlpycairo and needs gcc + libcairo2-dev to compile from source.
# The runtime image only needs the cairo runtime library (no -dev, no gcc).
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc \
        libcairo2-dev \
        pkg-config \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /build
COPY . .
# Install the project with [gui] extras (streamlit + markdown + xhtml2pdf).
# Pulling the GUI deps into the base image lets the same image serve both
# the CLI and the Streamlit GUI — only the entrypoint changes per service.
RUN pip install --no-cache-dir '.[gui]'

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Runtime needs libcairo2 (the .so) so pycairo can ``import _cairo``;
# the -dev headers and gcc don't need to leak into the final image.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libcairo2 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# UID/GID 1000 matches the default user on most Linux hosts and is what
# Synology bind-mounts permission-check against when you set the share
# owner via Control Panel → Shared Folder → permissions.
RUN groupadd --gid 1000 appuser \
 && useradd --uid 1000 --gid 1000 --create-home appuser
USER appuser
WORKDIR /home/appuser/app

COPY --from=builder --chown=appuser:appuser /build .

# CLI default — the docker-compose ``gui`` service overrides this with
# its own ``entrypoint: []`` + ``command: streamlit run gui/app.py``.
ENTRYPOINT ["tradingagents"]
