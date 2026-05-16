#!/bin/bash
# scripts/clone_foss_projects.sh
# Clone all FOSS projects to ~/impt/foss/
# Run on the Droplet host (not inside docker)

set -e
FOSS_DIR="${HOME}/impt/foss"
mkdir -p "$FOSS_DIR"

clone_or_update() {
    local slug="$1"
    local url="$2"
    local tag="$3"
    local dest="$FOSS_DIR/$slug"
    if [ -d "$dest/.git" ]; then
        echo "[$slug] Already cloned — skipping"
    else
        echo "[$slug] Cloning $url @ $tag …"
        git clone --depth 1 --branch "$tag" "$url" "$dest" 2>&1 | tail -2
        echo "[$slug] Done"
    fi
}

# ── Java — Small ──────────────────────────────────────────────────────────────
clone_or_update "gson"        "https://github.com/google/gson"        "gson-parent-2.10.1"
clone_or_update "commons-io"  "https://github.com/apache/commons-io"  "rel/commons-io-2.15.1"
clone_or_update "joda-time"   "https://github.com/JodaOrg/joda-time"  "v2.12.7"

# ── Java — Medium ─────────────────────────────────────────────────────────────
clone_or_update "commons-lang"        "https://github.com/apache/commons-lang"        "rel/commons-lang-3.14.0"
clone_or_update "commons-collections" "https://github.com/apache/commons-collections" "rel/commons-collections-4.4"
clone_or_update "jsoup"               "https://github.com/jhy/jsoup"                  "jsoup-1.17.2"
clone_or_update "mockito"             "https://github.com/mockito/mockito"            "v5.11.0"

# ── Java — Large ──────────────────────────────────────────────────────────────
clone_or_update "commons-math" "https://github.com/apache/commons-math" "MATH_3_6_1"
clone_or_update "assertj"      "https://github.com/assertj/assertj"     "assertj-core-3.25.3"
clone_or_update "rxjava"       "https://github.com/ReactiveX/RxJava"    "v3.1.8"

# ── JavaScript — Small (pure logic, Jest) ─────────────────────────────────────
clone_or_update "ms"       "https://github.com/vercel/ms"       "2.1.3"
clone_or_update "uuid"     "https://github.com/uuidjs/uuid"     "v9.0.1"
clone_or_update "dayjs"    "https://github.com/iamkun/dayjs"    "v1.11.10"
clone_or_update "mathjs"   "https://github.com/josdejong/mathjs" "v12.4.2"

# ── JavaScript — Medium (Jest) ────────────────────────────────────────────────
clone_or_update "validator-js" "https://github.com/validatorjs/validator.js" "13.11.0"
clone_or_update "zod"          "https://github.com/colinhacks/zod"           "v3.22.4"
clone_or_update "axios"        "https://github.com/axios/axios"              "v1.6.8"
clone_or_update "date-fns"     "https://github.com/date-fns/date-fns"        "v3.6.0"

# ── JavaScript — Large ────────────────────────────────────────────────────────
clone_or_update "faker-js" "https://github.com/faker-js/faker"  "v8.4.1"
clone_or_update "ramda"    "https://github.com/ramda/ramda"      "v0.29.1"

echo ""
echo "All 20 FOSS projects cloned to $FOSS_DIR"
ls -la "$FOSS_DIR"
