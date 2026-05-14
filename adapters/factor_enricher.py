"""adapters/factor_enricher.py — Enriches mutants with static analysis factors."""
from __future__ import annotations
import logging
import os
import subprocess
from pathlib import Path
from typing import List

from impt.models.mutant import Mutant

log = logging.getLogger(__name__)

SECURITY_KEYWORDS = {
    "password", "token", "auth", "crypt", "sql", "inject", "xss", "csrf",
    "sanitize", "hash", "salt", "sign", "verify", "permission", "role",
    "admin", "secret", "key", "encrypt", "decrypt", "hmac", "jwt", "oauth",
    "session", "cookie", "header", "cors",
}


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
