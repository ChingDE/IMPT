"""adapters/factor_enricher.py — Enriches mutants with static analysis factors."""
from __future__ import annotations
import logging
import subprocess
from pathlib import Path
from typing import Dict, List, Optional

from impt.models.mutant import Mutant

log = logging.getLogger(__name__)

SECURITY_KEYWORDS = {
    "password", "token", "auth", "crypt", "sql", "inject", "xss", "csrf",
    "sanitize", "hash", "salt", "sign", "verify", "permission", "role",
    "admin", "secret", "key", "encrypt", "decrypt", "hmac", "jwt", "oauth",
    "session", "cookie", "header", "cors",
}

# Literature-based defaults (used when DB is unavailable)
# Sources: Andrews et al. 2005, Just et al. 2014, Papadakis et al. 2019
LITERATURE_KILL_RATES: Dict[str, float] = {
    # Kill rates grounded in Just et al. (2014) — 357 real faults from Defects4J.
    # ROR and ABS: directly cited (75-85% fault detection).
    # SDL: directly cited (35-45% fault detection) — significantly lower than others.
    # AOR, COR: derived from Just et al.'s fault distribution
    #   (25% arithmetic, 60% conditional logic errors).
    # UOI, LCR, NEGATE_RETURN, NULL_RETURN, CRP: estimates with no direct citation.
    # These are labelled as initial defaults; the operator_stats table is updated
    # from real run data after every completed session.
    "ROR":           0.80,   # Empirical: Just et al. (2014), 75-85% fault detection
    "ABS":           0.80,   # Empirical: Just et al. (2014), 75-85% fault detection
    "NEGATE_RETURN": 0.75,   # Estimate (PIT ReturnValsMutator widely effective)
    "COR":           0.75,   # Derived: Just et al. (2014), 60% of faults are conditional
    "AOR":           0.72,   # Derived: Just et al. (2014), 25% of faults are arithmetic
    "UOI":           0.70,   # Estimate: no direct citation
    "LCR":           0.65,   # Estimate: no direct citation
    "NULL_RETURN":   0.60,   # Estimate: no direct citation
    "CRP":           0.55,   # Estimate: no direct citation
    "SDL":           0.40,   # Empirical: Just et al. (2014), 35-45% fault detection
}


def _load_operator_kill_rates() -> Dict[str, float]:
    """Load global operator kill rates from DB, fall back to literature defaults."""
    try:
        import sqlalchemy as sa
        from config.settings import get_settings
        settings = get_settings()
        sync_url = settings.DATABASE_URL_SYNC or settings.DATABASE_URL.replace(
            'postgresql+asyncpg', 'postgresql+psycopg2'
        ).replace('sqlite+aiosqlite', 'sqlite').replace('?ssl=require', '?sslmode=require')
        engine = sa.create_engine(sync_url, pool_pre_ping=True,
                                   connect_args={"connect_timeout": 3}
                                   if 'postgresql' in sync_url else {})
        with engine.connect() as conn:
            rows = conn.execute(
                sa.text("SELECT operator, kill_rate FROM operator_stats")
            ).fetchall()
        engine.dispose()
        if rows:
            rates = {r[0]: float(r[1]) for r in rows}
            log.debug("Loaded %d operator kill rates from DB", len(rates))
            return rates
    except Exception as e:
        log.debug("Could not load operator kill rates from DB: %s", e)
    return dict(LITERATURE_KILL_RATES)


def update_operator_stats(operator_results: Dict[str, Dict[str, int]]) -> None:
    """
    Update global operator kill rates after a completed run.
    operator_results: {operator: {total: N, killed: K}}
    """
    if not operator_results:
        return
    try:
        import sqlalchemy as sa
        from datetime import datetime
        from config.settings import get_settings
        settings = get_settings()
        sync_url = settings.DATABASE_URL_SYNC or settings.DATABASE_URL.replace(
            'postgresql+asyncpg', 'postgresql+psycopg2'
        ).replace('sqlite+aiosqlite', 'sqlite').replace('?ssl=require', '?sslmode=require')
        engine = sa.create_engine(sync_url, pool_pre_ping=True,
                                   connect_args={"connect_timeout": 3}
                                   if 'postgresql' in sync_url else {})
        with engine.begin() as conn:
            for op, stats in operator_results.items():
                total  = stats.get("total", 0)
                killed = stats.get("killed", 0)
                if total == 0:
                    continue
                conn.execute(sa.text("""
                    INSERT INTO operator_stats (operator, total_mutants, killed_mutants, kill_rate, last_updated)
                    VALUES (:op, :total, :killed, :rate, :now)
                    ON CONFLICT (operator) DO UPDATE SET
                        total_mutants  = operator_stats.total_mutants  + :total,
                        killed_mutants = operator_stats.killed_mutants + :killed,
                        kill_rate      = CAST(operator_stats.killed_mutants + :killed AS FLOAT)
                                         / NULLIF(operator_stats.total_mutants + :total, 0),
                        last_updated   = :now
                """), {
                    "op":     op,
                    "total":  total,
                    "killed": killed,
                    "rate":   killed / total,
                    "now":    datetime.utcnow(),
                })
        engine.dispose()
        log.info("Updated operator kill rates for %d operators", len(operator_results))
    except Exception as e:
        log.warning("Could not update operator stats (non-fatal): %s", e)


class FactorEnricher:
    def __init__(self, project_dir: Path,
                 operator_kill_rates: Optional[Dict[str, float]] = None):
        self.root              = project_dir
        self._kill_rates       = operator_kill_rates or _load_operator_kill_rates()

    def enrich(self, mutants: List[Mutant]) -> None:
        for m in mutants:
            self._enrich_one(m)

    def _enrich_one(self, m: Mutant) -> None:
        f = m.factors
        # Historical effectiveness from global operator kill rates
        op_key = m.operator.value if hasattr(m.operator, "value") else str(m.operator)
        f.historical_effectiveness = self._kill_rates.get(op_key, 0.5)
        # Static analysis factors
        f.cyclomatic_complexity = self._cyclomatic_proxy(m)
        f.cognitive_complexity  = self._cognitive_proxy(m)
        f.nesting_depth         = self._nesting_depth(m)
        f.security_score        = self._security_score(m)
        f.days_since_change     = self._days_since_change(m)
        f.bug_density           = self._bug_density(m)

    def _read_window(self, m: Mutant, radius: int = 20) -> List[str]:
        path = self.root / m.location.file
        if not path.exists():
            return []
        try:
            lines = path.read_text(errors="ignore").splitlines()
            lo    = max(0, m.location.line - 1 - radius)
            hi    = min(len(lines), m.location.line + radius)
            return lines[lo:hi]
        except Exception:
            return []

    def _cyclomatic_proxy(self, m: Mutant) -> float:
        keywords = {"if", "else if", "for", "while", "switch", "case", "catch", "&&", "||", "?"}
        lines    = self._read_window(m, 20)
        return float(sum(1 for line in lines for kw in keywords if kw in line))

    def _cognitive_proxy(self, m: Mutant) -> float:
        nesting  = {"if", "for", "while", "switch"}
        lines    = self._read_window(m, 30)
        score    = 0.0
        depth    = 0
        for line in lines:
            stripped = line.lstrip()
            for kw in nesting:
                if stripped.startswith(kw):
                    score += 1 + depth
                    depth += 1
                    break
        return min(20.0, score)

    def _nesting_depth(self, m: Mutant) -> float:
        path = self.root / m.location.file
        if not path.exists():
            return 1.0
        try:
            lines = path.read_text(errors="ignore").splitlines()
            if m.location.line <= len(lines):
                indent = len(lines[m.location.line - 1]) - len(lines[m.location.line - 1].lstrip())
                return max(1.0, indent / 4.0)
        except Exception:
            pass
        return 1.0

    def _security_score(self, m: Mutant) -> float:
        lines = self._read_window(m, 5)
        text  = " ".join(lines).lower()
        return 1.0 if any(kw in text for kw in SECURITY_KEYWORDS) else 0.0

    def _days_since_change(self, m: Mutant) -> float:
        try:
            result = subprocess.run(
                ["git", "log", "-1", "--format=%ct", "--", m.location.file],
                cwd=self.root, capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0 and result.stdout.strip():
                import time
                ts = int(result.stdout.strip())
                return max(0.0, (time.time() - ts) / 86400)
        except Exception:
            pass
        return 30.0

    def _bug_density(self, m: Mutant) -> float:
        try:
            result = subprocess.run(
                ["git", "log", "--oneline", "--grep=fix", "--grep=bug",
                 "--grep=error", "--all", "--", m.location.file],
                cwd=self.root, capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0:
                bug_commits = len(result.stdout.strip().splitlines())
                path = self.root / m.location.file
                if path.exists():
                    kloc = max(1, sum(1 for _ in path.read_text(errors="ignore").splitlines())) / 1000
                    return bug_commits / kloc
        except Exception:
            pass
        return 1.0



class FactorEnricher:
    def __init__(self, project_dir: Path):
        self.root = project_dir

    def enrich(self, mutants: List[Mutant]) -> None:
        for m in mutants:
            self._enrich_one(m)

    def _enrich_one(self, m: Mutant) -> None:
        f = m.factors
        f.cyclomatic_complexity = self._cyclomatic_proxy(m)
        f.cognitive_complexity  = self._cognitive_proxy(m)
        f.nesting_depth         = self._nesting_depth(m)
        f.security_score        = self._security_score(m)
        f.days_since_change     = self._days_since_change(m)
        f.bug_density           = self._bug_density(m)

    def _read_window(self, m: Mutant, radius: int = 20) -> List[str]:
        path = self.root / m.location.file
        if not path.exists():
            return []
        try:
            lines = path.read_text(errors="ignore").splitlines()
            lo    = max(0, m.location.line - 1 - radius)
            hi    = min(len(lines), m.location.line + radius)
            return lines[lo:hi]
        except Exception:
            return []

    def _cyclomatic_proxy(self, m: Mutant) -> float:
        keywords = {"if", "else if", "for", "while", "switch", "case", "catch", "&&", "||", "?"}
        lines    = self._read_window(m, 20)
        return float(sum(1 for line in lines for kw in keywords if kw in line))

    def _cognitive_proxy(self, m: Mutant) -> float:
        nesting  = {"if", "for", "while", "switch"}
        lines    = self._read_window(m, 30)
        score    = 0.0
        depth    = 0
        for line in lines:
            stripped = line.lstrip()
            for kw in nesting:
                if stripped.startswith(kw):
                    score += 1 + depth
                    depth += 1
                    break
        return min(20.0, score)

    def _nesting_depth(self, m: Mutant) -> float:
        path = self.root / m.location.file
        if not path.exists():
            return 1.0
        try:
            lines = path.read_text(errors="ignore").splitlines()
            if m.location.line <= len(lines):
                indent = len(lines[m.location.line - 1]) - len(lines[m.location.line - 1].lstrip())
                return max(1.0, indent / 4.0)
        except Exception:
            pass
        return 1.0

    def _security_score(self, m: Mutant) -> float:
        lines = self._read_window(m, 5)
        text  = " ".join(lines).lower()
        return 1.0 if any(kw in text for kw in SECURITY_KEYWORDS) else 0.0

    def _days_since_change(self, m: Mutant) -> float:
        try:
            result = subprocess.run(
                ["git", "log", "-1", "--format=%ct", "--", m.location.file],
                cwd=self.root, capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0 and result.stdout.strip():
                import time
                ts = int(result.stdout.strip())
                return max(0.0, (time.time() - ts) / 86400)
        except Exception:
            pass
        return 30.0

    def _bug_density(self, m: Mutant) -> float:
        try:
            result = subprocess.run(
                ["git", "log", "--oneline", "--grep=fix", "--grep=bug",
                 "--grep=error", "--all", "--", m.location.file],
                cwd=self.root, capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0:
                bug_commits = len(result.stdout.strip().splitlines())
                path = self.root / m.location.file
                if path.exists():
                    kloc = max(1, sum(1 for _ in path.read_text(errors="ignore").splitlines())) / 1000
                    return bug_commits / kloc
        except Exception:
            pass
        return 1.0
