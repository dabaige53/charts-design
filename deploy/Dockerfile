# One native service, shared by author, publication and scheduled-cleaner hosts.
FROM rust:1.91.1-bookworm AS chef
WORKDIR /build/runtime-core
ENV CARGO_BUILD_JOBS=2 CXXFLAGS=-g0
COPY runtime-core/rust-toolchain.toml ./
RUN rustup show && cargo install --locked --version 0.1.73 cargo-chef

FROM chef AS native-plan
COPY runtime-core/ ./
RUN cargo chef prepare --recipe-path recipe.json

FROM chef AS native
COPY --from=native-plan /build/runtime-core/recipe.json recipe.json
# Only dependency metadata invalidates this layer, including bundled DuckDB.
# Keep cook and the real build in the same directory with the same toolchain.
RUN cargo chef cook --release --locked --recipe-path recipe.json
# Restore the real build.rs, source and embedded resources after the skeleton.
COPY runtime-core/ ./
RUN cargo build --release --locked --bin charts-design-core

FROM oven/bun:1.3.8 AS ui
WORKDIR /build/runtime-ui
COPY runtime-ui/package.json runtime-ui/bun.lock ./
RUN bun install --frozen-lockfile --ignore-scripts
COPY runtime-ui/ ./
RUN bun run build && bun run package:runtime

FROM debian:bookworm-slim AS runtime-base
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates libssl3 libstdc++6 tar \
 && rm -rf /var/lib/apt/lists/* \
 && useradd --system --uid 10001 --home-dir /data charts \
 && mkdir -p /data/projects /data/runtime && chown -R charts /data
COPY --from=native /build/runtime-core/target/release/charts-design-core /usr/local/bin/charts-design-core
WORKDIR /app
ENV CHARTS_PACKAGE_ROOT=/app CHARTS_WORKSPACE=/data/projects CHARTS_RUNTIME_ROOT=/data/runtime CHARTS_HOST=0.0.0.0 CHARTS_PORT=8000
USER charts
ENTRYPOINT ["/usr/local/bin/charts-design-core"]

FROM runtime-base AS cleaner
ENV CHARTS_RUNTIME_ROOT=/tmp/charts-cleaner CHARTS_PORT=9000
EXPOSE 9000
CMD ["cleanup-server"]

FROM runtime-base AS app
USER root
RUN apt-get update && apt-get install -y --no-install-recommends fonts-dejavu-core fonts-noto-cjk \
 && rm -rf /var/lib/apt/lists/*
COPY --from=ui /build/runtime-ui/dist/ runtime-ui/dist/
COPY skills/ skills/
COPY cloudbase/migrations/ cloudbase/migrations/
COPY package.json README.md ./
ARG CHARTS_IMAGE_COMMIT
ENV CHARTS_IMAGE_COMMIT=${CHARTS_IMAGE_COMMIT}
USER charts
VOLUME ["/data"]
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s CMD ["/usr/local/bin/charts-design-core", "healthcheck"]
CMD ["server"]
