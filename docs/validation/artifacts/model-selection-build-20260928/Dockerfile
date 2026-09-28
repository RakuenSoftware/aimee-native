FROM ghcr.io/rakuensoftware/aimee@sha256:3e2df804ad5d6c9bc8c7f73cfd0bad3e42a7111a665b7f6bdf9f247ba562a736 AS build
USER root
RUN apt-get update && apt-get install -y --no-install-recommends build-essential libpq-dev libsqlite3-dev libssl-dev libzstd-dev pkg-config python3 zlib1g-dev libp11-kit-dev git ca-certificates curl
WORKDIR /src
ADD source.tar.gz /src/
RUN sh scripts/fetch-treesitter.sh && make -C src ../aimee-server -j2 AIMEE_TREESITTER=1 GIT_VERSION=v0.4.5-native.model-selection
FROM ghcr.io/rakuensoftware/aimee@sha256:3e2df804ad5d6c9bc8c7f73cfd0bad3e42a7111a665b7f6bdf9f247ba562a736
COPY --from=build /src/aimee-server /usr/local/bin/aimee-server
LABEL org.opencontainers.image.revision="816740e90" org.opencontainers.image.description="Aimee 0.4.5 plus authenticated native delivery bridge"
