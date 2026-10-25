# OpenOCD with the Holtek HT32F165x flash driver (hansemro/openocd-ht32, ht32f165x-dev).
# bcm2835gpio is ARM-host only in this OpenOCD version, so it is not built here.
# Build: docker build -t mk-typist/openocd-ht32 -f docker/openocd-ht32.Dockerfile docker
FROM ubuntu:22.04 AS build

ARG OPENOCD_REPO=https://github.com/hansemro/openocd-ht32.git
ARG OPENOCD_COMMIT=1f3300ccae2ed7e7f5c9d783ce5cdfac8bb5e6d4

RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        ca-certificates git build-essential autoconf automake libtool pkg-config texinfo \
        libusb-1.0-0-dev libhidapi-dev libftdi1-dev libjaylink-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /src
RUN git clone "$OPENOCD_REPO" openocd \
    && cd openocd \
    && git checkout "$OPENOCD_COMMIT" \
    && git submodule update --init jimtcl

WORKDIR /src/openocd
RUN ./bootstrap nosubmodule \
    && ./configure --prefix=/opt/openocd --disable-werror --disable-internal-libjaylink \
        --enable-cmsis-dap --enable-jlink --enable-ftdi --enable-stlink \
    && make -j"$(nproc)" \
    && make install

FROM ubuntu:22.04
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        libusb-1.0-0 libhidapi-hidraw0 libhidapi-libusb0 libftdi1-2 libjaylink0 \
    && rm -rf /var/lib/apt/lists/*
COPY --from=build /opt/openocd /opt/openocd
ENV PATH=/opt/openocd/bin:$PATH
WORKDIR /work
ENTRYPOINT ["openocd"]
