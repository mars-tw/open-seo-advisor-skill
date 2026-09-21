"""Run the shell installer offline with fake Python and pip executables."""

import os
import shutil
import subprocess
from pathlib import Path

import pytest


def _find_bash():
    if os.name == "nt":
        # Avoid WindowsApps/WSL launchers: these tests need Git Bash's local filesystem.
        git = shutil.which("git")
        if git:
            candidate = Path(git).resolve().parent.parent / "bin" / "bash.exe"
            if candidate.is_file():
                return str(candidate)
        pytest.skip("Git Bash is required to exercise install.sh on Windows")
    bash = shutil.which("bash")
    if not bash:
        pytest.skip("bash is required to exercise install.sh")
    return bash


def _write_executable(path, content):
    path.write_text(content, encoding="utf-8", newline="\n")
    path.chmod(0o755)


@pytest.fixture
def run_installer(tmp_path):
    bash = _find_bash()
    project = tmp_path / "installer copy"
    project.mkdir()
    (project / "scripts").mkdir()
    installer = Path(__file__).resolve().parents[2] / "install.sh"
    (project / "install.sh").write_text(
        installer.read_text(encoding="utf-8"), encoding="utf-8", newline="\n"
    )
    fake_bin = project / "fake-bin"
    fake_bin.mkdir()
    fake_python = r"""#!/bin/bash
set -eu
printf 'candidate:%s:%s\n' "${0##*/}" "$*" >> "$TEST_INSTALL_LOG"
case "$1" in
    --version) printf 'Python %s\n' "$TEST_PYTHON_VERSION" ;;
    -c) printf '%s\n' "$TEST_PYTHON_VERSION" ;;
    -m)
        [ "$2" = venv ] || exit 90
        mkdir -p "$3/bin"
        cp "$TEST_VENV_TEMPLATE" "$3/bin/python"
        chmod +x "$3/bin/python"
        touch "$3/bin/seo-advisor"
        ;;
    *) exit 91 ;;
esac
"""
    for name in ("python3", "python"):
        _write_executable(fake_bin / name, fake_python)
    _write_executable(
        project / "fake-venv-python",
        r"""#!/bin/bash
set -eu
printf 'venv:%s\n' "$*" >> "$TEST_INSTALL_LOG"
case "$*" in
    '-m pip install --upgrade pip') ;;
    '-m pip install -e '*) [ -d "$5" ] ;;
    '-m seo_advisor.cli mode consultant') ;;
    *) exit 92 ;;
esac
""",
    )

    def run(version="3.12", locale="C"):
        env = dict(
            os.environ,
            LC_ALL=locale,
            LANG=locale,
            TEST_PYTHON_VERSION=version,
            TEST_INSTALL_LOG="calls.log",
            TEST_VENV_TEMPLATE="fake-venv-python",
        )
        env.pop("BASH_ENV", None)
        result = subprocess.run(
            [
                bash,
                "--noprofile",
                "--norc",
                "-c",
                'export PATH="$PWD/fake-bin:/usr/bin:/bin"; exec bash ./install.sh',
            ],
            cwd=project,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=20,
            check=False,
        )
        calls = (project / "calls.log").read_text(encoding="utf-8").splitlines()
        return result, calls, project

    return run


@pytest.mark.parametrize("version", ["3.10", "3.12", "4.0"])
def test_installer_completes_in_c_locale_without_real_install(run_installer, version):
    result, calls, project = run_installer(version=version)

    assert result.returncode == 0, result.stdout + result.stderr
    assert f"找到 Python：Python {version}（使用指令：python3）" in result.stdout
    assert "安裝完成！" in result.stdout
    assert "unbound variable" not in result.stderr
    assert calls[0] == "candidate:python3:--version"
    assert calls[1].startswith("candidate:python3:-c ")
    assert calls[2].startswith("candidate:python3:-m venv ")
    assert calls[2].endswith("/scripts/.venv")
    assert calls[3] == "venv:-m pip install --upgrade pip"
    assert calls[4].startswith("venv:-m pip install -e ")
    assert calls[4].endswith("/scripts")
    assert calls[5:] == ["venv:-m seo_advisor.cli mode consultant"]
    assert (project / "scripts/.venv/bin/python").is_file()
    assert 'seo-advisor" auto-demo' in result.stdout


def test_installer_completes_in_available_single_byte_locale(run_installer):
    bash = _find_bash()
    selected_locale = "en_US.ISO-8859-1"
    probe = subprocess.run(
        [bash, "--noprofile", "--norc", "-c", "locale charmap"],
        env=dict(os.environ, LC_ALL=selected_locale),
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    if probe.returncode or probe.stdout.strip() != "ISO-8859-1":
        pytest.skip("ISO-8859-1 locale is not installed")

    result, calls, _ = run_installer(locale=selected_locale)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "找到 Python：Python 3.12（使用指令：python3）" in result.stdout
    assert "安裝完成！" in result.stdout
    assert calls[-1] == "venv:-m seo_advisor.cli mode consultant"
    assert "unbound variable" not in result.stderr


@pytest.mark.parametrize("version", ["3.9", "2.10", "", "unavailable"])
def test_installer_rejects_missing_or_old_version_before_installing(run_installer, version):
    result, calls, project = run_installer(version=version)

    assert result.returncode == 1, result.stdout + result.stderr
    assert "找不到 Python 3.10 以上版本" in result.stdout
    assert "安裝完成！" not in result.stdout
    assert "integer expression expected" not in result.stderr
    assert all(":-m " not in call for call in calls)
    assert not (project / "scripts/.venv").exists()
