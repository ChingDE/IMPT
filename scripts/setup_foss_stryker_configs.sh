#!/bin/bash
# scripts/setup_foss_stryker_configs.sh
# Creates stryker.impt.config.cjs for each FOSS project that needs
# a non-standard test runner configuration.
# Run once on the Droplet after cloning.

FOSS_DIR="${HOME}/impt/foss"

write_config() {
    local slug="$1"
    local config="$2"
    local dest="$FOSS_DIR/$slug/stryker.impt.config.cjs"
    if [ -d "$FOSS_DIR/$slug" ]; then
        echo "$config" > "$dest"
        echo "[$slug] Written stryker.impt.config.cjs"
    else
        echo "[$slug] Directory not found — skipping"
    fi
}

# ── chalk (ESM, uses ava + xo — TTY-dependent, use node runner) ──────────────
write_config "chalk" "module.exports = {
  reporters: ['json'],
  testRunner: 'command',
  coverageAnalysis: 'off',
  commandRunner: { command: 'node_modules/.bin/ava' },
  mutate: ['source/**/*.js'],
  ignorePatterns: ['node_modules', 'reports', '.stryker-tmp'],
  jsonReporter: { fileName: 'reports/mutation/mutation.json' }
};"

# ── ms (ESM, uses jest) ───────────────────────────────────────────────────────
write_config "ms" "module.exports = {
  reporters: ['json'],
  testRunner: 'jest',
  coverageAnalysis: 'perTest',
  mutate: ['index.js', 'src/**/*.js'],
  ignorePatterns: ['node_modules', 'reports', '.stryker-tmp'],
  jsonReporter: { fileName: 'reports/mutation/mutation.json' }
};"

# ── uuid (ESM, uses jest) ─────────────────────────────────────────────────────
write_config "uuid" "module.exports = {
  reporters: ['json'],
  testRunner: 'jest',
  coverageAnalysis: 'perTest',
  mutate: ['src/**/*.js', 'src/**/*.ts'],
  ignorePatterns: ['node_modules', 'reports', '.stryker-tmp', 'dist'],
  jsonReporter: { fileName: 'reports/mutation/mutation.json' }
};"

# ── dayjs (uses jest) ─────────────────────────────────────────────────────────
write_config "dayjs" "module.exports = {
  reporters: ['json'],
  testRunner: 'jest',
  coverageAnalysis: 'perTest',
  mutate: ['src/**/*.js'],
  ignorePatterns: ['node_modules', 'reports', '.stryker-tmp'],
  jsonReporter: { fileName: 'reports/mutation/mutation.json' }
};"

# ── validator-js (uses jest) ──────────────────────────────────────────────────
write_config "validator-js" "module.exports = {
  reporters: ['json'],
  testRunner: 'jest',
  coverageAnalysis: 'perTest',
  mutate: ['src/**/*.js'],
  ignorePatterns: ['node_modules', 'reports', '.stryker-tmp'],
  jsonReporter: { fileName: 'reports/mutation/mutation.json' }
};"

# ── lodash (uses jest) ────────────────────────────────────────────────────────
write_config "lodash" "module.exports = {
  reporters: ['json'],
  testRunner: 'jest',
  coverageAnalysis: 'perTest',
  mutate: ['lodash.js', 'src/**/*.js'],
  ignorePatterns: ['node_modules', 'reports', '.stryker-tmp'],
  jsonReporter: { fileName: 'reports/mutation/mutation.json' }
};"

# ── axios (uses jest) ─────────────────────────────────────────────────────────
write_config "axios" "module.exports = {
  reporters: ['json'],
  testRunner: 'jest',
  coverageAnalysis: 'perTest',
  mutate: ['lib/**/*.js'],
  ignorePatterns: ['node_modules', 'reports', '.stryker-tmp'],
  jsonReporter: { fileName: 'reports/mutation/mutation.json' }
};"

# ── date-fns (uses jest) ──────────────────────────────────────────────────────
write_config "date-fns" "module.exports = {
  reporters: ['json'],
  testRunner: 'jest',
  coverageAnalysis: 'perTest',
  mutate: ['src/**/*.ts', 'src/**/*.js'],
  ignorePatterns: ['node_modules', 'reports', '.stryker-tmp'],
  jsonReporter: { fileName: 'reports/mutation/mutation.json' }
};"

# ── luxon (uses jest) ─────────────────────────────────────────────────────────
write_config "luxon" "module.exports = {
  reporters: ['json'],
  testRunner: 'jest',
  coverageAnalysis: 'perTest',
  mutate: ['src/**/*.js'],
  ignorePatterns: ['node_modules', 'reports', '.stryker-tmp'],
  jsonReporter: { fileName: 'reports/mutation/mutation.json' }
};"

# ── yargs (uses jest/mocha) ───────────────────────────────────────────────────
write_config "yargs" "module.exports = {
  reporters: ['json'],
  testRunner: 'mocha',
  coverageAnalysis: 'perTest',
  mutate: ['lib/**/*.js', 'lib/**/*.cjs'],
  ignorePatterns: ['node_modules', 'reports', '.stryker-tmp'],
  jsonReporter: { fileName: 'reports/mutation/mutation.json' }
};"

echo ""
echo "Done. Also copy configs to foss-tmp if it exists:"
for slug in chalk ms uuid dayjs validator-js lodash axios date-fns luxon yargs; do
    if [ -d "${HOME}/impt/foss-tmp/$slug" ]; then
        cp "$FOSS_DIR/$slug/stryker.impt.config.cjs" "${HOME}/impt/foss-tmp/$slug/" 2>/dev/null && echo "  Copied to foss-tmp/$slug"
    fi
done
