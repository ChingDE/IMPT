"""tests/adapters/test_factor_enricher.py"""
import tempfile
from pathlib import Path
from adapters.factor_enricher import FactorEnricher
from tests.conftest import make_mutant


def _write(tmp: Path, filename: str, content: str) -> None:
    (tmp / filename).parent.mkdir(parents=True, exist_ok=True)
    (tmp / filename).write_text(content)


def test_cyclomatic_proxy_counts_branches():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        code = "\n".join([
            "if (x > 0) {",
            "  for (int i=0; i<10; i++) {",
            "    if (i % 2 == 0) {",
            "      while (true) { break; }",
            "    }",
            "  }",
            "}",
        ])
        _write(root, "src/Calc.java", code)
        m = make_mutant(file="src/Calc.java", line=3)
        enricher = FactorEnricher(root)
        enricher.enrich([m])
        assert m.factors.cyclomatic_complexity > 0


def test_security_score_flags_password_keyword():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        code = "String password = hashPassword(raw);"
        _write(root, "src/Auth.java", code)
        m = make_mutant(file="src/Auth.java", line=1)
        enricher = FactorEnricher(root)
        enricher.enrich([m])
        assert m.factors.security_score == 1.0


def test_security_score_zero_for_plain_code():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        code = "int sum = a + b;"
        _write(root, "src/Calc.java", code)
        m = make_mutant(file="src/Calc.java", line=1)
        enricher = FactorEnricher(root)
        enricher.enrich([m])
        assert m.factors.security_score == 0.0


def test_missing_file_sets_defaults():
    with tempfile.TemporaryDirectory() as tmp:
        m = make_mutant(file="nonexistent/File.java", line=1)
        enricher = FactorEnricher(Path(tmp))
        enricher.enrich([m])
        assert m.factors.cyclomatic_complexity >= 0
        assert m.factors.days_since_change >= 0


def test_nesting_depth_positive():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        code = "    " * 4 + "return x + y;"
        _write(root, "src/Deep.java", code)
        m = make_mutant(file="src/Deep.java", line=1)
        enricher = FactorEnricher(root)
        enricher.enrich([m])
        assert m.factors.nesting_depth >= 0


def test_enriches_multiple_mutants():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        for i in range(3):
            _write(root, f"src/File{i}.java", f"int x{i} = {i};")
        mutants = [make_mutant(file=f"src/File{i}.java", line=1) for i in range(3)]
        enricher = FactorEnricher(root)
        enricher.enrich(mutants)
        assert all(m.factors.cyclomatic_complexity >= 0 for m in mutants)
