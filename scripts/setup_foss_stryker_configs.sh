#!/bin/bash
# scripts/setup_foss_stryker_configs.sh
# Creates stryker.impt.config.cjs for each FOSS JS project.
# Run on the Droplet after cloning. Also copies to foss-tmp if present.

FOSS_DIR="${HOME}/impt/foss"
TMP_DIR="${HOME}/impt/foss-tmp"

write_config() {
    local slug="$1"
    local config="$2"
    if [ -d "$FOSS_DIR/$slug" ]; then
        echo "$config" > "$FOSS_DIR/$slug/stryker.impt.config.cjs"
        echo "[$slug] Written to foss/$slug"
    fi
    if [ -d "$TMP_DIR/$slug" ]; then
        echo "$config" > "$TMP_DIR/$slug/stryker.impt.config.cjs"
        echo "[$slug] Copied to foss-tmp/$slug"
    fi
}

# ── ms (Mocha — test script: mocha tests.js) ──────────────────────────────────
write_config "ms" "module.exports = {
  reporters: ['json'],
  testRunner: 'command',
  coverageAnalysis: 'off',
  commandRunner: { command: 'node_modules/.bin/mocha tests.js --exit' },
  mutate: ['index.js', '!tests.js', '!test.js', '!*.config.*'],
  ignorePatterns: ['node_modules', 'reports', '.stryker-tmp'],
  jsonReporter: { fileName: 'reports/mutation/mutation.json' }
};"

# ── uuid (ESM — uses import syntax, needs experimental-vm-modules) ────────────
write_config "uuid" "module.exports = {
  reporters: ['json'],
  testRunner: 'command',
  coverageAnalysis: 'off',
  commandRunner: { command: 'node --experimental-vm-modules node_modules/.bin/jest test/unit/ --passWithNoTests || true' },
  mutate: ['src/**/*.js', '!src/**/*.test.js', '!src/**/*.spec.js'],
  ignorePatterns: ['node_modules', 'reports', '.stryker-tmp', 'dist'],
  jsonReporter: { fileName: 'reports/mutation/mutation.json' }
};"

# ── dayjs (Jest — test script: TZ=... jest) ──────────────────────────────────
write_config "dayjs" "module.exports = {
  reporters: ['json'],
  testRunner: 'command',
  coverageAnalysis: 'off',
  commandRunner: { command: 'node_modules/.bin/jest --passWithNoTests --testPathPattern=test/parse' },
  mutate: ['src/**/*.js', '!src/**/*.test.js', '!src/**/*.spec.js'],
  ignorePatterns: ['node_modules', 'reports', '.stryker-tmp'],
  jsonReporter: { fileName: 'reports/mutation/mutation.json' }
};"

# ── mathjs (Mocha — test script: npm run test:src) ───────────────────────────
write_config "mathjs" "module.exports = {
  reporters: ['json'],
  testRunner: 'command',
  coverageAnalysis: 'off',
  commandRunner: { command: 'node_modules/.bin/mocha --recursive test/unit --exit' },
  mutate: ['src/**/*.js', '!src/**/*.test.js', '!src/**/*.spec.js'],
  ignorePatterns: ['node_modules', 'reports', '.stryker-tmp'],
  jsonReporter: { fileName: 'reports/mutation/mutation.json' }
};"

# ── validator-js (Mocha — test script: nyc mocha --require @babel/register) ──
write_config "validator-js" "module.exports = {
  reporters: ['json'],
  testRunner: 'command',
  coverageAnalysis: 'off',
  commandRunner: { command: 'node_modules/.bin/mocha --require @babel/register --reporter dot --exit' },
  mutate: ['src/**/*.js', '!src/**/*.test.js', '!src/**/*.spec.js'],
  ignorePatterns: ['node_modules', 'reports', '.stryker-tmp'],
  jsonReporter: { fileName: 'reports/mutation/mutation.json' }
};"

# ── zod (Vitest — source files at root level, not src/) ─────────────────────
write_config "zod" "module.exports = {
  reporters: ['json'],
  testRunner: 'command',
  coverageAnalysis: 'off',
  commandRunner: { command: 'node_modules/.bin/vitest run || true' },
  mutate: ['src/**/*.ts', '!src/**/*.test.ts', '!src/**/*.spec.ts', '!src/**/__tests__/**'],
  ignorePatterns: ['node_modules', 'reports', '.stryker-tmp'],
  jsonReporter: { fileName: 'reports/mutation/mutation.json' }
};"

# ── axios (Mocha — unit tests only with timeout) ────────────────────────────
write_config "axios" "module.exports = {
  reporters: ['json'],
  testRunner: 'command',
  coverageAnalysis: 'off',
  commandRunner: { command: 'node_modules/.bin/mocha test/unit --recursive --exit --timeout 10000 || true' },
  mutate: ['lib/**/*.js', '!lib/**/*.test.js', '!lib/**/*.spec.js'],
  ignorePatterns: ['node_modules', 'reports', '.stryker-tmp'],
  jsonReporter: { fileName: 'reports/mutation/mutation.json' }
};"

# ── date-fns (Vitest — test script: vitest run) ───────────────────────────────
write_config "date-fns" "module.exports = {
  reporters: ['json'],
  testRunner: 'command',
  coverageAnalysis: 'off',
  commandRunner: { command: 'node_modules/.bin/vitest run || true' },
  mutate: ['src/**/*.ts', '!src/**/*.test.ts', '!src/**/*.spec.ts'],
  ignorePatterns: ['node_modules', 'reports', '.stryker-tmp'],
  jsonReporter: { fileName: 'reports/mutation/mutation.json' }
};"

# ── faker-js (Vitest — test script: vitest) ───────────────────────────────────
write_config "faker-js" "module.exports = {
  reporters: ['json'],
  testRunner: 'command',
  coverageAnalysis: 'off',
  commandRunner: { command: 'node_modules/.bin/vitest run || true' },
  mutate: ['src/**/*.ts', '!src/**/*.test.ts', '!src/**/*.spec.ts'],
  ignorePatterns: ['node_modules', 'reports', '.stryker-tmp'],
  jsonReporter: { fileName: 'reports/mutation/mutation.json' }
};"

# ── ramda (Mocha — correct test path is source/test/) ───────────────────────
write_config "ramda" "module.exports = {
  reporters: ['json'],
  testRunner: 'command',
  coverageAnalysis: 'off',
  commandRunner: { command: 'node_modules/.bin/mocha --recursive source/test --exit --timeout 10000 || true' },
  mutate: ['source/**/*.js', '!source/test/**', '!source/__tests__/**', '!source/**/*.spec.js'],
  ignorePatterns: ['node_modules', 'reports', '.stryker-tmp'],
  jsonReporter: { fileName: 'reports/mutation/mutation.json' }
};"

echo ""
echo "Done. Stryker override configs written for all 10 JS projects."

# Clear cached Phase 1 reports so next run re-enumerates fresh
for slug in zod faker-js date-fns axios ramda; do
  rm -f "$TMP_DIR/$slug/reports/mutation/mutation.json"
done
echo "Cleared cached reports for updated configs."
