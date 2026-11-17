import os
import subprocess
from pathlib import Path

import pytest

from invopt.cli import build_parser, terms_from_args

ROOT = Path(__file__).resolve().parents[1]


def test_contract_terms_flags():
    args = build_parser().parse_args(["backtest", "--hard-discount", "0.35", "--soft-discount", "0.25",
                                      "--dyn-discount", "0.12"])
    t = terms_from_args(args)
    assert (t.hard_discount, t.soft_discount, t.dyn_discount) == (0.35, 0.25, 0.12)
    assert terms_from_args(build_parser().parse_args(["backtest"])).hard_discount == 0.30


def test_contract_terms_flags_validated():
    args = build_parser().parse_args(["backtest", "--hard-discount", "0.1", "--soft-discount", "0.2"])
    with pytest.raises(ValueError):
        terms_from_args(args)


@pytest.mark.skipif(not (ROOT / "data" / "raw" / "hotels.csv").exists(), reason="data not fetched")
def test_fetch_script_does_not_need_gnu_stat(tmp_path):
    shim = tmp_path / "bin"
    shim.mkdir()
    fake = shim / "stat"  # BSD/macOS stat rejects GNU's -c flag
    fake.write_text("#!/bin/sh\necho 'stat: illegal option -- c' >&2\nexit 1\n")
    fake.chmod(0o755)
    env = {**os.environ, "PATH": f"{shim}:{os.environ['PATH']}"}
    out = subprocess.run(["bash", str(ROOT / "scripts" / "fetch_data.sh")], env=env, capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    assert "OK" in out.stdout


def test_zero_discount_is_respected():
    args = build_parser().parse_args(["backtest", "--dyn-discount", "0"])
    assert terms_from_args(args).dyn_discount == 0.0
