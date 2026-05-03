# sandbox/Dockerfile
# ─────────────────────────────────────────────────────────────────────────────
# IMPT Sandbox Image
# Runs PIT (Java) and Stryker (JavaScript) mutation testing in isolation.
# Used by the Celery worker for every mutation job.
# ─────────────────────────────────────────────────────────────────────────────

FROM eclipse-temurin:17-jdk-jammy

# ── System packages ───────────────────────────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl wget git maven gradle \
    && rm -rf /var/lib/apt/lists/*

# ── Node.js 20 (for Stryker) ──────────────────────────────────────────────────
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# ── Pre-cache Maven PIT plugin ────────────────────────────────────────────────
# This dramatically speeds up the first run on a cold container.
RUN mvn dependency:get \
    -Dartifact=org.pitest:pitest-maven:1.15.3 \
    -Dmaven.repo.local=/root/.m2/repository \
    2>/dev/null || true

# ── Pre-install Stryker globally ──────────────────────────────────────────────
RUN npm install -g @stryker-mutator/core \
    @stryker-mutator/javascript-mutator \
    @stryker-mutator/jest-runner \
    @stryker-mutator/mocha-runner \
    2>/dev/null || true

# ── Non-root user for security ────────────────────────────────────────────────
RUN useradd -m -u 1001 imptuser
USER imptuser
WORKDIR /project

# ── Healthcheck ───────────────────────────────────────────────────────────────
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD java -version && node --version || exit 1
