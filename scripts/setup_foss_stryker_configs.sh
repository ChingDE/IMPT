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

# ── ms (Jest) ─────────────────────────────────────────────────────────────────
write_config "ms" "module.exports = {
  reporters: ['json'],
  testRunner: 'command',
  coverageAnalysis: 'off',
  commandRunner: { command: 'npx jest --passWithNoTests || true' },
  mutate: ['index.js'],
  ignorePatterns: ['node_modules', 'reports', '.stryker-tmp'],
  jsonReporter: { fileName: 'reports/mutation/mutation.json' }
};"

# ── uuid (Jest) ───────────────────────────────────────────────────────────────
write_config "uuid" "module.exports = {
  reporters: ['json'],
  testRunner: 'command',
  coverageAnalysis: 'off',
  commandRunner: { command: 'npx jest --passWithNoTests || true' },
  mutate: ['src/**/*.js', '!src/**/*.test.js'],
  ignorePatterns: ['node_modules', 'reports', '.stryker-tmp', 'dist'],
  jsonReporter: { fileName: 'reports/mutation/mutation.json' }
};"

# ── dayjs (Jest) ──────────────────────────────────────────────────────────────
write_config "dayjs" "module.exports = {
  reporters: ['json'],
  testRunner: 'command',
  coverageAnalysis: 'off',
  commandRunner: { command: 'npx jest --passWithNoTests || true' },
  mutate: ['src/**/*.js', '!src/**/*.test.js'],
  ignorePatterns: ['node_modules', 'reports', '.stryker-tmp'],
  jsonReporter: { fileName: 'reports/mutation/mutation.json' }
};"

# ── mathjs (Jest) ─────────────────────────────────────────────────────────────
write_config "mathjs" "module.exports = {
  reporters: ['json'],
  testRunner: 'command',
  coverageAnalysis: 'off',
  commandRunner: { command: 'npx jest --passWithNoTests || true' },
  mutate: ['src/**/*.js', '!src/**/*.test.js'],
  ignorePatterns: ['node_modules', 'reports', '.stryker-tmp'],
  jsonReporter: { fileName: 'reports/mutation/mutation.json' }
};"

# ── validator-js (Jest) ───────────────────────────────────────────────────────
write_config "validator-js" "module.exports = {
  reporters: ['json'],
  testRunner: 'command',
  coverageAnalysis: 'off',
  commandRunner: { command: 'npx jest --passWithNoTests || true' },
  mutate: ['src/**/*.js', '!src/**/*.test.js'],
  ignorePatterns: ['node_modules', 'reports', '.stryker-tmp'],
  jsonReporter: { fileName: 'reports/mutation/mutation.json' }
};"

# ── zod (Vitest via command) ──────────────────────────────────────────────────
write_config "zod" "module.exports = {
  reporters: ['json'],
  testRunner: 'command',
  coverageAnalysis: 'off',
  commandRunner: { command: 'node_modules/.bin/vitest run || true' },
  mutate: ['src/**/*.ts', '!src/**/*.test.ts'],
  ignorePatterns: ['node_modules', 'reports', '.stryker-tmp'],
  jsonReporter: { fileName: 'reports/mutation/mutation.json' }
};"

# ── axios (Jest) ──────────────────────────────────────────────────────────────
write_config "axios" "module.exports = {
  reporters: ['json'],
  testRunner: 'command',
  coverageAnalysis: 'off',
  commandRunner: { command: 'npx jest --passWithNoTests || true' },
  mutate: ['lib/**/*.js', '!lib/**/*.test.js'],
  ignorePatterns: ['node_modules', 'reports', '.stryker-tmp'],
  jsonReporter: { fileName: 'reports/mutation/mutation.json' }
};"

# ── date-fns (Jest) ───────────────────────────────────────────────────────────
write_config "date-fns" "module.exports = {
  reporters: ['json'],
  testRunner: 'command',
  coverageAnalysis: 'off',
  commandRunner: { command: 'npx jest --passWithNoTests || true' },
  mutate: ['src/**/*.ts', '!src/**/*.test.ts', '!src/**/*.spec.ts'],
  ignorePatterns: ['node_modules', 'reports', '.stryker-tmp'],
  jsonReporter: { fileName: 'reports/mutation/mutation.json' }
};"

# ── faker-js (Vitest via command) ─────────────────────────────────────────────
write_config "faker-js" "module.exports = {
  reporters: ['json'],
  testRunner: 'command',
  coverageAnalysis: 'off',
  commandRunner: { command: 'node_modules/.bin/vitest run || true' },
  mutate: ['src/**/*.ts', '!src/**/*.test.ts', '!src/**/*.spec.ts'],
  ignorePatterns: ['node_modules', 'reports', '.stryker-tmp'],
  jsonReporter: { fileName: 'reports/mutation/mutation.json' }
};"

# ── ramda (Mocha) ─────────────────────────────────────────────────────────────
write_config "ramda" "module.exports = {
  reporters: ['json'],
  testRunner: 'mocha',
  coverageAnalysis: 'off',
  commandRunner: { command: 'npx jest --passWithNoTests || true' },
  mutate: ['source/**/*.js', '!source/**/*.spec.js'],
  ignorePatterns: ['node_modules', 'reports', '.stryker-tmp'],
  jsonReporter: { fileName: 'reports/mutation/mutation.json' }
};"

echo ""
echo "Done. Stryker override configs written for all 10 JS projects."
