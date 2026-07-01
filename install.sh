#!/usr/bin/env bash
# Open SEO Advisor - Mac / Linux 一鍵安裝腳本
#
# 用途：檢查 Python 版本、建立虛擬環境、安裝套件，讓新手不需要自己敲
# pip / venv 指令。設計上只做「安裝」這一件事，不會順便安裝 Docker、
# Playwright 或 Lighthouse 等進階選配套件。

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPTS_DIR="$SCRIPT_DIR/scripts"
VENV_DIR="$SCRIPTS_DIR/.venv"

step() { printf "\n==> %s\n" "$1"; }
success() { printf "\033[0;32m%s\033[0m\n" "$1"; }
failure() { printf "\033[0;31m%s\033[0m\n" "$1"; }

step "檢查 Python 是否已安裝"

PYTHON_CMD=""
for candidate in python3 python; do
    if command -v "$candidate" >/dev/null 2>&1; then
        version="$("$candidate" --version 2>&1)"
        major_minor="$("$candidate" -c 'import sys; print(f"{sys.version_info[0]}.{sys.version_info[1]}")' 2>/dev/null || echo "0.0")"
        major="${major_minor%%.*}"
        minor="${major_minor##*.}"
        if [ "$major" -ge 3 ] && [ "$minor" -ge 10 ]; then
            PYTHON_CMD="$candidate"
            success "找到 Python：$version（使用指令：$candidate）"
            break
        fi
    fi
done

if [ -z "$PYTHON_CMD" ]; then
    failure "找不到 Python 3.10 以上版本，請先到 https://www.python.org/downloads/ 安裝。"
    exit 1
fi

step "建立虛擬環境（.venv）"
if [ -d "$VENV_DIR" ]; then
    success "虛擬環境已存在，跳過建立步驟。"
else
    "$PYTHON_CMD" -m venv "$VENV_DIR"
    success "虛擬環境建立完成。"
fi

if [ -f "$VENV_DIR/bin/python" ]; then
    VENV_PYTHON="$VENV_DIR/bin/python"
elif [ -f "$VENV_DIR/Scripts/python.exe" ]; then
    # Git Bash on Windows：venv 內部仍是 Windows 目錄結構
    VENV_PYTHON="$VENV_DIR/Scripts/python.exe"
else
    failure "找不到虛擬環境中的 Python 執行檔，請刪除 scripts/.venv 後重新執行本腳本。"
    exit 1
fi

step "安裝 Open SEO Advisor 套件（第一次安裝可能需要幾分鐘，請耐心等候，畫面會持續顯示進度）"
"$VENV_PYTHON" -m pip install --quiet --upgrade pip
"$VENV_PYTHON" -m pip install -e "$SCRIPTS_DIR"

step "驗證安裝"
"$VENV_PYTHON" -m seo_advisor.cli mode consultant

echo ""
success "安裝完成！"
echo ""
echo "接下來請執行以下指令啟動虛擬環境，並開始使用："
echo ""
if [ -f "$VENV_DIR/bin/activate" ]; then
    echo "    source $VENV_DIR/bin/activate"
else
    echo "    source $VENV_DIR/Scripts/activate"
fi
echo "    seo-advisor"
echo ""
echo "不知道下一步怎麼做？請看 QUICKSTART.md。"
