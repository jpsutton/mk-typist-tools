# Host tool for the Holtek HT32 ROM ISP loader over USB (hansemro/ht32-dfu-tool).
# Build: docker build -t mk-typist/ht32-dfu-tool -f docker/ht32-dfu-tool.Dockerfile docker
FROM rust:1-bookworm AS build

ARG TOOL_REPO=https://github.com/hansemro/ht32-dfu-tool.git
ARG TOOL_COMMIT=848fc07

RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        libusb-1.0-0-dev pkg-config \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /src
RUN git clone "$TOOL_REPO" ht32-dfu-tool \
    && cd ht32-dfu-tool \
    && git checkout "$TOOL_COMMIT" \
    && cargo build --release --locked

FROM debian:bookworm-slim
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        libusb-1.0-0 \
    && rm -rf /var/lib/apt/lists/*
COPY --from=build /src/ht32-dfu-tool/target/release/ht32-dfu-tool /usr/local/bin/
WORKDIR /work
ENTRYPOINT ["ht32-dfu-tool"]
