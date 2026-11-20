ARG BUILD_FROM=ghcr.io/seb5594/home-assistant-base-python:3.14-alpine3.24-2026.11.0@sha256:807723c78eeeb57962063875e19b500571a5a6e89423977db6d1123832f1550e

FROM ${BUILD_FROM}

# The application itself only needs Python's standard library. openssl creates the self-signed
# certificate that lets other mail servers encrypt their connection to this app.
RUN apk add --no-cache \
    # renovate: datasource=repology depName=alpine_3_24/openssl
    openssl=3.5.9-r1

COPY rootfs/ /

# Git does not keep the executable bit when files are uploaded through the GitHub API.
RUN chmod a+x /usr/bin/mail-forwarder-health \
    && find /etc/s6-overlay/s6-rc.d -type f \( -name run -o -name finish \) -exec chmod a+x {} +

ARG BUILD_VERSION=2026.11.20.3
ARG BUILD_ARCH=amd64
RUN mkdir -p /etc/mail-forwarder && echo "${BUILD_VERSION}" >/etc/mail-forwarder/version
LABEL io.hass.version="${BUILD_VERSION}" \
    io.hass.type="addon" \
    io.hass.arch="${BUILD_ARCH}" \
    org.opencontainers.image.source="https://github.com/seb5594/Home-Assistant-Mail-Forwarder-App"

HEALTHCHECK --interval=5m --timeout=10s --start-period=1m --retries=3 \
    CMD ["/usr/bin/mail-forwarder-health"]
