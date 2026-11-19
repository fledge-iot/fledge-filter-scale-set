# Fledge + fledge-filter-scale-set test image, with the plugin built under
# AddressSanitizer so memory bugs show up deterministically.
#
# Stage "fledge": builds Fledge core from source (slow, cached after the first build).
# Final stage: builds this plugin from the working tree and installs it into Fledge.

FROM ubuntu:22.04 AS fledge

ENV DEBIAN_FRONTEND=noninteractive TZ=Etc/UTC
RUN apt-get update && apt-get install -y --no-install-recommends \
        git sudo curl ca-certificates rsyslog lsb-release apt-utils \
    && sed -i '/imklog/s/^/#/' /etc/rsyslog.conf

ARG FLEDGE_VERSION=v3.1.0
RUN git clone --depth 1 --branch "${FLEDGE_VERSION}" https://github.com/fledge-iot/fledge.git /fledge-src

WORKDIR /fledge-src
RUN apt-get update && ./requirements.sh && make && make install

ENV FLEDGE_ROOT=/usr/local/fledge

# Minimal Python south plugin producing asset "asd" with fixed datapoint values.
COPY docker/constant/ /usr/local/fledge/python/fledge/plugins/south/constant/

# An ASan-built plugin only loads into a process with the ASan runtime preloaded.
# Preload it into the two processes that load the plugin: the south service and
# get_plugin_info (used by core to read plugin_info). Preloading into all of
# Fledge hangs its startup. Reports go to /var/log/asan/ and the reporting
# process stops on the first error.
RUN set -e; mkdir -p /var/log/asan; \
    printf '#!/bin/sh\nexport LD_PRELOAD=%s\nexport ASAN_OPTIONS=detect_leaks=0:detect_stack_use_after_return=1:log_path=/var/log/asan/asan\nexec "$@"\n' \
        "$(readlink -f "$(gcc -print-file-name=libasan.so)")" > /usr/local/bin/asan-run; \
    chmod +x /usr/local/bin/asan-run; \
    cd /usr/local/fledge; \
    mv extras/C/get_plugin_info extras/C/get_plugin_info.bin; \
    printf '#!/bin/sh\nexec /usr/local/bin/asan-run /usr/local/fledge/extras/C/get_plugin_info.bin "$@"\n' > extras/C/get_plugin_info; \
    chmod +x extras/C/get_plugin_info; \
    sed -i 's|^  \./fledge\.services\.south "\$@"$|  /usr/local/bin/asan-run ./fledge.services.south "$@"|' scripts/services/south_c; \
    grep -q asan-run scripts/services/south_c

FROM fledge

COPY . /src/plugin
RUN set -e; cd /src/plugin; \
    sed -i 's/\r$//' mkversion VERSION fledge.version; chmod +x mkversion; \
    rm -rf build && mkdir build && cd build; \
    FLEDGE_ROOT=/fledge-src cmake -DFLEDGE_INSTALL=/usr/local/fledge \
        -DCMAKE_BUILD_TYPE=Release \
        "-DCMAKE_CXX_FLAGS_RELEASE=-g -fsanitize=address -fno-omit-frame-pointer" \
        -DCMAKE_SHARED_LINKER_FLAGS=-fsanitize=address ..; \
    make; make install

COPY docker/entrypoint.sh docker/test.py /test/
RUN sed -i 's/\r$//' /test/entrypoint.sh /test/test.py && chmod +x /test/entrypoint.sh

EXPOSE 8081
HEALTHCHECK --interval=5s --timeout=3s --start-period=30s --retries=30 \
    CMD curl -sf http://localhost:8081/fledge/ping || exit 1
ENTRYPOINT ["/test/entrypoint.sh"]
