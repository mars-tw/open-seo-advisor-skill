#Requires -Version 5.1
<#
  Open SEO Advisor - Windows 一鍵安裝腳本

  用途：檢查 Python 版本、建立虛擬環境、安裝套件，讓新手不需要自己敲
  pip / venv 指令。設計上只做「安裝」這一件事，不會順便安裝 Docker、
  Playwright 或 Lighthouse 等進階選配套件。
#>

$ErrorActionPreference = "Stop"

function Write-Step($message) {
    Write-Host ""
    Write-Host "==> $message" -ForegroundColor Cyan
}

function Write-Success($message) {
    Write-Host $message -ForegroundColor Green
}

function Write-Failure($message) {
    Write-Host $message -ForegroundColor Red
}

Write-Step "檢查 Python 是否已安裝"

$pythonCmd = $null
foreach ($candidate in @("python", "python3", "py")) {
    try {
        $version = & $candidate --version 2>&1
        if ($LASTEXITCODE -eq 0) {
            # 解析版本，必須 >= 3.10 才收（避免用舊版建好環境後才壞掉）
            if ($version -match "(\d+)\.(\d+)") {
                $major = [int]$Matches[1]
                $minor = [int]$Matches[2]
                if ($major -gt 3 -or ($major -eq 3 -and $minor -ge 10)) {
                    $pythonCmd = $candidate
                    Write-Success "找到 Python：$version（使用指令：$candidate）"
                    break
                } else {
                    Write-Host "略過 $candidate（$version）：需要 Python 3.10 以上。" -ForegroundColor DarkYellow
                }
            }
        }
    } catch {
        continue
    }
}

if (-not $pythonCmd) {
    Write-Failure "找不到 Python 3.10 以上版本。請先到 https://www.python.org/downloads/ 安裝 Python 3.10 或更新版本。"
    Write-Failure "安裝時記得勾選「Add Python to PATH」，安裝完成後重新開一個 PowerShell 視窗再執行本腳本。"
    exit 1
}

Write-Step "建立虛擬環境（.venv）"
$scriptsDir = Join-Path $PSScriptRoot "scripts"
$venvDir = Join-Path $scriptsDir ".venv"

if (Test-Path $venvDir) {
    Write-Success "虛擬環境已存在，跳過建立步驟。"
} else {
    & $pythonCmd -m venv $venvDir
    if ($LASTEXITCODE -ne 0) {
        Write-Failure "建立虛擬環境失敗，請確認 Python 安裝是否完整。"
        exit 1
    }
    Write-Success "虛擬環境建立完成。"
}

$venvPython = Join-Path $venvDir "Scripts\python.exe"

Write-Step "安裝 Open SEO Advisor 套件（第一次安裝可能需要幾分鐘，請耐心等候，畫面會持續顯示進度）"
& $venvPython -m pip install --upgrade pip
& $venvPython -m pip install -e "$scriptsDir"
if ($LASTEXITCODE -ne 0) {
    Write-Failure "套件安裝失敗，請檢查上方錯誤訊息，或參考 docs/install-troubleshooting.md。"
    exit 1
}

Write-Step "驗證安裝"
& $venvPython -m seo_advisor.cli mode consultant

$venvExe = Join-Path $venvDir "Scripts\seo-advisor.exe"

Write-Host ""
Write-Success "安裝完成！接下來只要做一件事：複製貼上這一行，就能看一份範例（不花錢）："
Write-Host ""
Write-Host "    & `"$venvExe`" auto-demo" -ForegroundColor Yellow
Write-Host ""
Write-Host "（要分析自己的網站、或其他進階用法，請看 QUICKSTART.md。）" -ForegroundColor DarkGray
