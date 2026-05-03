"""
adapters/factor_enricher.py
Static Analysis Factor Enricher
=================================
Enriches each Mutant's PriorityFactors with values derived from:
  - Cyclomatic / cognitive complexity (line-level proxy)
  - Nesting depth (indentation heuristic)
  - Change recency (git log --follow)
  - Bug density (git log --grep "fix|bug|error|issue|hotfix")
  - Security keywords (auth, crypt, sql, password, token, ...)

This runs fast (pure Python, no subprocess per mutant) and is called
after the adapter produces the initial mutant list.
"""

from __future__ import annotations

import logging
import re
import subprocess
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from impt.models.mutant import Mutant, PriorityFactors

log = logging.getLogger(__name__)

# Security-critical keywords — presence raises security_score to 1.0
SECURITY_KEYWORDS = {
    "password", "passwd", "secret", "token", "auth", "authz",
    "authoriz", "authenticat", "crypt", "encrypt", "decrypt",
    "sql", "query", "execute", "injection", "xss", "csrf",
    "sanitize", "escape", "hash", "salt", "sign", "verify",
    "permission", "role", "admin", "privilege",
}


class FactorEnricher:
    """
    Enriches PriorityFactors for a list of mutants using static analysis.

    Parameters
    ----------
    project_dir : Path
        Root of the project — used for git log and source reading.
    historical_kill_rates : dict, optional
        Maps operator value (str) → historical kill rate [0,1].
        If not supplied, uses calibrated defaults from Just et al. (2014).
    """

    # Calibrated defaults from Just et al. (2014) Table 3
    DEFAULT_KILL_RATES: Dict[str, float] = {
        "AOR": 0.62,
        "ROR": 0.81,
        "ABS": 0.73,
        "COR": 0.58,
        "LCR": 0.67,
        "SOR": 0.55,
        "UOI": 0.48,
        "SDL": 0.71,
        "VDL": 0.60,
        "ODL": 0.58,
        "NEGATE_RETURN": 0.76,
        "NULL_RETURN":   0.69,
    }

    def __init__(
        self,
        project_dir: Path,
        historical_kill_rates: Optional[Dict[str, float]] = None,
    ) -> None:
        self.project_dir = Path(project_dir)
        self.kill_rates  = historical_kill_rates or dict(self.DEFAULT_KILL_RATES)
        self._git_cache: Dict[str, Tuple[float, float]] = {}  # file → (days, bug_density)
        self._source_cache: Dict[str, List[str]] = {}         # file → lines
        self._has_git = self._check_git()

    # ── Public API ───────────────────────────────────────────────────────────

    def enrich(self, mutants: List[Mutant]) -> List[Mutant]:
        """
        Fill in PriorityFactors for every mutant in place.
        Returns the same list.
        """
        log.info("FactorEnricher: enriching %d mutants", len(mutants))

        # Pre-compute git data per unique file
        unique_files = {m.location.file for m in mutants}
        if self._has_git:
            for f in unique_files:
                self._git_cache[f] = self._git_factors(f)
        else:
            for f in unique_files:
                self._git_cache[f] = (30.0, 1.0)  # neutral defaults

        for m in mutants:
            m.factors = self._compute_factors(m)

        return mutants

    # ── Per-mutant computation ────────────────────────────────────────────────

    def _compute_factors(self, m: Mutant) -> PriorityFactors:
        lines = self._get_source_lines(m.location.file)
        line_idx = m.location.line - 1  # 0-indexed

        cyclomatic  = self._cyclomatic_proxy(lines, line_idx)
        cognitive   = self._cognitive_proxy(lines, line_idx)
        nesting     = self._nesting_depth(lines, line_idx)
        security    = self._security_score(lines, line_idx)
        days, bugs  = self._git_cache.get(m.location.file, (30.0, 1.0))
        historical  = self.kill_rates.get(m.operator.value, 0.60)

        return PriorityFactors(
            historical_effectiveness=historical,
            cyclomatic_complexity=float(cyclomatic),
            cognitive_complexity=float(cognitive),
            nesting_depth=float(nesting),
            security_score=security,
            days_since_change=days,
            bug_density=bugs,
        )

    # ── Source analysis ───────────────────────────────────────────────────────

    def _get_source_lines(self, file_rel: str) -> List[str]:
        if file_rel in self._source_cache:
            return self._source_cache[file_rel]

        # Try to find the file under src/main or src/
        candidates = [
            self.project_dir / file_rel,
            *list(self.project_dir.rglob(Path(file_rel).name)),
        ]
        for candidate in candidates:
            if candidate.exists():
                try:
                    lines = candidate.read_text(errors="ignore").splitlines()
                    self._source_cache[file_rel] = lines
                    return lines
                except OSError:
                    break
        self._source_cache[file_rel] = []
        return []

    def _cyclomatic_proxy(self, lines: List[str], line_idx: int) -> int:
        """
        Count decision points in a ±20-line window around the mutated line.
        Keywords: if, else, for, while, switch, case, catch, ternary (?:), &&, ||
        """
        window = lines[max(0, line_idx - 20): line_idx + 20]
        pattern = re.compile(
            r'\b(if|else\s+if|for|while|switch|case|catch|finally)\b'
            r'|(\?\s*\w)|(\|\|)|(&&)'
        )
        count = sum(len(pattern.findall(l)) for l in window)
        return max(1, count)

    def _cognitive_proxy(self, lines: List[str], line_idx: int) -> int:
        """
        Cognitive complexity proxy: count nested control structures.
        Each nesting level adds 1 extra. Simplified Sonarqube heuristic.
        """
        window = lines[max(0, line_idx - 30): line_idx + 10]
        depth = 0
        score = 0
        for line in window:
            stripped = line.lstrip()
            indent   = len(line) - len(stripped)
            level    = indent // 4   # assume 4-space indentation
            control  = re.search(r'\b(if|for|while|switch|catch)\b', stripped)
            if control:
                score += level + 1
                depth = max(depth, level)
        return max(1, score)

    def _nesting_depth(self, lines: List[str], line_idx: int) -> int:
        """Indentation-based nesting depth of the mutated line."""
        if not lines or line_idx >= len(lines):
            return 1
        line = lines[line_idx]
        indent = len(line) - len(line.lstrip())
        return max(1, indent // 4)

    def _security_score(self, lines: List[str], line_idx: int) -> float:
        """1.0 if any security keyword appears near the mutated line, else 0.0."""
        window = "\n".join(lines[max(0, line_idx - 5): line_idx + 5]).lower()
        for kw in SECURITY_KEYWORDS:
            if kw in window:
                return 1.0
        return 0.0

    # ── Git analysis ──────────────────────────────────────────────────────────

    def _check_git(self) -> bool:
        try:
            r = subprocess.run(
                ["git", "rev-parse", "--is-inside-work-tree"],
                cwd=self.project_dir, capture_output=True, timeout=5
            )
            return r.returncode == 0
        except Exception:
            return False

    def _git_factors(self, file_rel: str) -> Tuple[float, float]:
        """Returns (days_since_last_change, bug_density_per_kloc)."""
        days       = self._days_since_change(file_rel)
        bug_density = self._bug_density(file_rel)
        return days, bug_density

    def _days_since_change(self, file_rel: str) -> float:
        """Days since the file was last committed."""
        try:
            r = subprocess.run(
                ["git", "log", "-1", "--format=%ct", "--", file_rel],
                cwd=self.project_dir, capture_output=True, text=True, timeout=10
            )
            ts = r.stdout.strip()
            if not ts:
                return 30.0
            commit_time = datetime.fromtimestamp(int(ts), tz=timezone.utc)
            delta = datetime.now(tz=timezone.utc) - commit_time
            return max(0.5, delta.days + delta.seconds / 86400)
        except Exception:
            return 30.0

    def _bug_density(self, file_rel: str) -> float:
        """
        Bug-fix commits touching this file / KLOC.
        Bug-fix commits are detected by commit message keywords.
        """
        try:
            r = subprocess.run(
                [
                    "git", "log", "--oneline",
                    "--grep=fix", "--grep=bug", "--grep=error",
                    "--grep=issue", "--grep=hotfix", "--grep=patch",
                    "--all-match=false",   # OR semantics
                    "--", file_rel,
                ],
                cwd=self.project_dir, capture_output=True, text=True, timeout=10
            )
            fix_commits = len(r.stdout.strip().splitlines())
            loc = self._file_loc(file_rel)
            kloc = max(loc / 1000, 0.1)
            return round(fix_commits / kloc, 2)
        except Exception:
            return 1.0

    def _file_loc(self, file_rel: str) -> int:
        lines = self._get_source_lines(file_rel)
        return sum(1 for l in lines if l.strip() and not l.strip().startswith("//"))
