# 安裝疑難排解

安裝過程卡住了嗎？先找找看你遇到的狀況在不在下面。

## 「安裝套件」那個步驟跑了好幾分鐘，是不是卡住了？

**通常不是卡住，是正常現象。** 第一次安裝需要下載並安裝多個 Python 套件
（例如網頁解析用的 `lxml`），依網路速度與電腦效能不同，可能需要 1-5
分鐘。只要畫面還在持續捲動出現 `Collecting...`、`Downloading...`、
`Installing...` 這類文字，就代表工具正在正常運作，請耐心等候。

如果畫面完全停止捲動**超過 10 分鐘**都沒有任何新的文字出現，才代表可能
真的卡住了，可以按 `Ctrl+C` 中斷後重新執行安裝腳本一次；已下載的套件會
被快取，第二次通常會快很多。

## 「找不到 Python」或 `python` 指令沒反應

**Windows**：到 <https://www.python.org/downloads/> 下載安裝檔，安裝時務必勾選
「Add Python to PATH」，裝完後**重新開一個新的** PowerShell 視窗再試一次
（舊視窗不會自動抓到新安裝的 Python）。

**Mac**：可以用官網安裝檔，或如果有安裝 [Homebrew](https://brew.sh/)，可以執行
`brew install python3`。

**Linux**：多數發行版已內建 Python 3，若版本太舊，用套件管理員更新，例如
Ubuntu/Debian：`sudo apt install python3 python3-venv`。

## PowerShell 顯示「因為這個系統上已停用指令碼執行」

這是 Windows 的安全機制封鎖了執行 `.ps1` 腳本。用系統管理員身分開啟 PowerShell，
執行：

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

輸入 `Y` 確認後，再重新執行 `.\install.ps1`。

## Mac / Linux 執行 `./install.sh` 出現「Permission denied」

這代表腳本沒有執行權限，執行：

```bash
chmod +x install.sh
./install.sh
```

## 安裝過程中出現大量紅字（pip 錯誤）

常見原因：

1. **Python 版本太舊**：需要 3.10 以上，用 `python3 --version`（或 Windows 的
   `python --version`）確認。
2. **網路連線問題**：pip 安裝套件需要連上網路下載，確認網路連線正常。
3. **公司/學校網路的防火牆或代理伺服器**：可能需要額外設定 pip 的 proxy，
   請洽詢你的網路管理員。

如果紅字訊息裡有明確的套件名稱和版本衝突，可以把完整錯誤訊息貼到專案的
GitHub Issues 尋求協助。

## 執行 `seo-advisor` 出現「command not found」

代表虛擬環境還沒啟動，或安裝沒有完全成功。請先手動啟動虛擬環境：

**Windows（PowerShell）**：

```powershell
scripts\.venv\Scripts\Activate.ps1
```

**Mac / Linux**：

```bash
source scripts/.venv/bin/activate
```

啟動後，終端機提示字元前面應該會出現 `(.venv)` 字樣，這時再輸入
`seo-advisor` 應該就能正常執行。

## 還是解決不了？

歡迎到專案的 GitHub Issues 回報，並附上：

- 你使用的作業系統與版本
- `python --version`（或 `python3 --version`）的輸出
- 完整的錯誤訊息截圖或文字
