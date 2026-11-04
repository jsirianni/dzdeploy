ARG BASE=debian:12-slim
FROM ${BASE}
RUN if command -v apt-get >/dev/null; then \
      apt-get update && apt-get install -y --no-install-recommends git ca-certificates file binutils diffutils && rm -rf /var/lib/apt/lists/*; \
    else \
      dnf install -y git ca-certificates file binutils diffutils cpio findutils && dnf clean all; \
    fi
COPY package-integration.sh /package-integration.sh
ENTRYPOINT ["bash", "/package-integration.sh"]
