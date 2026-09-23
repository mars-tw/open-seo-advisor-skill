"""The distributed wheel must work without the repository's template files."""

import os
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest


def test_wheel_packages_templates_and_installed_demo_runs(tmp_path):
    pytest.importorskip("build")
    source = Path(__file__).resolve().parents[1]
    wheels = tmp_path / "wheels"
    built = subprocess.run(
        [sys.executable, "-m", "build", "--wheel", "--no-isolation", "--outdir", str(wheels)],
        cwd=source,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
        check=False,
    )
    assert built.returncode == 0, built.stdout + built.stderr
    wheel = next(wheels.glob("*.whl"))
    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()
        for name in (
            "index.html",
            "page.html",
            "styles.css",
            "story.css",
            "site.js",
            "story-timeline.js",
            "brief.example.json",
        ):
            assert f"seo_advisor/website/templates/{name}" in names
    installed = tmp_path / "installed"
    installed_run = subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--no-deps",
            "--no-compile",
            "--target",
            str(installed),
            str(wheel),
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
        check=False,
    )
    assert installed_run.returncode == 0, installed_run.stdout + installed_run.stderr
    env = dict(os.environ, PYTHONPATH=str(installed), PYTHONUTF8="1")
    demo = subprocess.run(
        [
            sys.executable,
            "-m",
            "seo_advisor.cli",
            "website",
            "demo",
            "--out",
            str(tmp_path / "demo"),
        ],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=False,
    )
    assert demo.returncode == 0, demo.stdout + demo.stderr
    assert '"status": "scaffold"' in demo.stdout
    assert (tmp_path / "demo/public/styles.css").is_file()
