# 免費額度與網站部署引導

官方文件查核日期：2026-09-18。額度、付款條件及產品功能會變；每次部署前重新開啟下列官方來源，記錄實際方案與日期。這份文件協助選型，不代表已登入、已部署或已驗證帳務。

## 先讓使用者做一個容易回答的選擇

依已有對話填好網站類型、是否需要付款／訂單後台，再問缺少的選項：

> 你想先用哪一種上線方式？
> 1. Cloudflare 免費方案：適合圖文與滾動動畫網站，之後可接 API。
> 2. Google Firebase Hosting Spark：適合希望用 Google 帳號管理的靜態網站。
> 3. Google Cloud Run：適合需要自己的後端，須啟用帳務並管理用量。
> 如果還沒決定，我先做好可搬移的靜態版本，預設準備 Cloudflare 設定。

「CF 黃雲」是 DNS 的代理狀態，讓流量經過 Cloudflare 的快取、防護與代理服務；網站檔案仍要放在 Workers Static Assets、Pages 或另一個來源主機。開黃雲不等於建立免費主機。[Cloudflare Proxy status](https://developers.cloudflare.com/dns/proxy-status/)

## 選型表

| 選項 | 適合用途 | 免費與帳務邊界 | 本技能採用方式 |
| --- | --- | --- | --- |
| Cloudflare Workers Static Assets | 銷售站、品牌故事、沉浸式體驗；需要時加 API | 直接提供靜態檔案的請求免費；執行 Worker、資料庫、媒體處理另計額度 | 新建專案優先準備靜態輸出，動態 API 明確分路徑 |
| Cloudflare Pages Free | 現有 Pages 專案或希望用 Git 建置的靜態站 | 有建置與檔案限制；Pages Functions 使用 Workers 額度 | 保留既有 Pages 工作流，無須為動畫搬家 |
| Firebase Hosting Spark | 靜態銷售頁、型錄、體驗站 | 不需付款資訊起步；Hosting 有儲存與傳輸配額，超額可能停止提供網站 | 選 **Hosting**；不可把需 Blaze 的其他 Firebase 產品混稱為 Spark 功能 |
| Google Cloud Run | 自訂伺服器、SSR、付款 webhook、訂單 API | 有免費額度，須 Cloud Billing；超額與其他服務可能收費 | 使用者需要後端且接受帳務條件時才選 |

這是本技能的架構建議；免費條件以各產品官方說明及帳戶狀態為準。網域購買、金流手續費、GPT 產圖、郵件、資料庫、第三方服務與付費 API 不因主機有免費額度而免費。

## Cloudflare：靜態優先

查核快照：

- Workers Static Assets 的靜態檔案請求不按次計費，儲存 Assets 無額外費用；SSR 或 `run_worker_first` 觸發 Worker 時依 Workers 計費／限額。避免為每張圖片都執行 Worker。[Static Assets 計費](https://developers.cloudflare.com/workers/static-assets/billing-and-limitations/)
- Workers Free：每帳戶每日 100,000 次 Worker 請求、每次 10 ms CPU；每 Worker 版本 20,000 個靜態檔案、每檔 25 MiB。CPU 限額不等於網路等待時間；SSR 框架須另測實際相容性。[Workers 限制](https://developers.cloudflare.com/workers/platform/limits/)
- Pages Free：每月 500 次建置、同時 1 次；20,000 個檔案、每檔 25 MiB。Functions 與靜態服務的配額分開看。[Pages 限制](https://developers.cloudflare.com/pages/platform/limits/)

引導步驟：

1. 在本機完成 build、圖檔壓縮、路由、404 與手機版檢查，確定真正的靜態輸出目錄，例如 `dist`。
2. 準備專案自己的 Wrangler 設定；`assets.directory` 指向輸出目錄。不要把原始碼、`.env` 或整個儲存庫當成發布目錄。選 Workers Static Assets 時參照[官方入門](https://developers.cloudflare.com/workers/static-assets/get-started/)。
3. 先交付可檢視的預覽與部署設定。使用者已要求上線到明確帳戶／專案時可按授權繼續；只要求「建站」或「選主機」時，完成本機交付後再確認公開目標。
4. 經官方 OAuth 登入或使用權限適當的 Token，核對帳戶、專案名稱與正式網址。不要把憑證放入 HTML、Git 或聊天記錄。
5. 部署後實際讀回首頁、獨立內容頁、圖片、`robots.txt`、`sitemap.xml` 與不存在的 URL。驗證 HTTPS、canonical、404、快取及 API 狀態碼。
6. 再設定自訂網域；只調整本專案需要的 DNS。記錄版本、公開 URL、回復上一版的方式與用量頁入口。

若加上 D1、KV、R2、Images、Workers AI 或其他產品，重新查核各自方案與費用。API 超額時要顯示可理解的狀態，不得讓購物頁誤顯示付款成功。

## Google：先分清 Spark 與 Cloud Run

### Firebase Hosting Spark

Spark 可不填付款資訊開始；連結 Cloud Billing 或在同一專案啟用 Cloud Run 等服務可能把專案轉為 Blaze。不可為了方便部署自行升級。[Firebase 方案](https://firebase.google.com/docs/projects/billing/firebase-pricing-plans)

本次查核發現兩個官方頁面口徑不同：

| 官方頁 | 2026-09-18 讀到的 Hosting 免費額度 |
| --- | --- |
| [Firebase 價格表](https://firebase.google.com/pricing) | 儲存 10 GB、傳輸 360 MB/day |
| [Hosting 用量文件](https://firebase.google.com/docs/hosting/usage-quotas-pricing) | 儲存 10 GB、傳輸 10 GB/month；Spark 傳輸超額經短暫寬限後停站至下個月 |

不要把每天與每月限額換算成可以互換的承諾。部署時查看專案 Console 顯示的實際週期與配額；仍無法確認時，以兩者都不超過作保守設計，並將差異記入交付說明。Hosting 的儲存用量包含保留的版本。

1. 建立／選取 Firebase 專案，確認仍為 Spark。
2. 依[Hosting 入門](https://firebase.google.com/docs/hosting/quickstart)初始化 Hosting，指定已驗證的輸出目錄。多頁 SEO 站保持各頁真實路徑，不要任意把未知 URL 全部改寫至首頁。
3. 本機預覽，核對專案 ID、發布內容與授權後部署 Hosting；部署前後都核對方案。
4. 讀回正式頁面與 404；檢查 Hosting 使用量與保留版本。把 GPT 生成圖片以壓縮後的靜態檔案發布，不要為此默默啟用另一個計費儲存產品。

### Google Cloud Run

Cloud Run request-based billing 的免費用量快照為每月 200 萬次請求、180,000 vCPU-seconds、360,000 GiB-seconds；以指定基準價格折抵、跨專案按 Billing account 合計，地區與 billing mode 會影響費用。Cloud Build、Artifact Registry、網路傳輸及其他相依服務須另外估算。[Cloud Run pricing](https://cloud.google.com/run/pricing?hl=en)

Google Cloud Free Tier 需要有效帳務帳戶；免費試用額度有期限，與持續性的 Free Tier 不同。已啟用付費帳戶的超額用量會計費。[Google Cloud Free Program](https://docs.cloud.google.com/free/docs/free-cloud-features)

1. 先列出後端必要性與完整服務清單：Cloud Run、建置、映像儲存、資料庫、Secrets、網路等；不要為純靜態動畫頁硬加容器。
2. 確認使用者接受 Billing、地區及用量安排後，才啟用需要的服務。以 request-based billing、最小執行個體數 0 作為低流量起點，依測試設定最大執行個體數及 timeout。
3. 伺服器監聽 `0.0.0.0` 與平台提供的 `PORT`；訂單不能只存在容器本機檔案系統。參照[容器合約](https://docs.cloud.google.com/run/docs/container-contract)。
4. 設定一般用量警報，並確認帳戶可用的 Spend cap enforcement；記錄服務範圍、停止服務影響與恢復方式。
5. 本機驗證容器、公開路由、API 與 Secrets 設定，按既有部署授權上線，再以正式 URL 驗證。交付成本檢視、停用及回復指引。

一般 **alerts-only budget 只通知，不會自動停用服務**。[預算與警報](https://docs.cloud.google.com/billing/docs/how-to/budgets)

截至查核日，Google 已提供 **Spend cap budgets（Preview）**，適用服務包含 Cloud Run；它限單一專案、單一適用服務，非整帳戶費用總上限。執行有延遲、進行中的請求可繼續計費，持續性資源也可能繼續收費，超出部分仍須支付。不能宣稱設定後保證零帳單。[Spend cap budgets](https://docs.cloud.google.com/billing/docs/how-to/budgets-spend-caps)

最大執行個體數只能限制部分擴充行為，不是金額上限；Cloud Run 文件也列有暫時超過設定值的情況。[Maximum instances](https://docs.cloud.google.com/run/docs/configuring/max-instances)

## 購物站的交付界線

靜態網站可以有商品頁、篩選、購物車介面與第三方結帳連結。真正的付款確認、庫存、訂單、退款、物流與會員資料需要可信後端或受託電商平台。

- 展示模式：明示模擬資料，不收款，不回報「已成立真實訂單」。
- 第三方託管結帳：使用商家確認的商品與付款連結；訂單權威在供應商，不相信網址參數或前端成功畫面。
- 自訂後端：伺服器核價、驗證金流簽章、處理 webhook 重試與冪等、保存訂單狀態，再驗證退款與庫存一致性。只在完整 sandbox 流程通過後標記可準備正式收款。

交付必填：主機／方案、查核日期、計費範圍、公開 URL 或未部署狀態、可用功能、尚未接通的後端、驗證證據、回復方式。使用者要求主機費零支出時，優先提供 Free／Spark 靜態版本，清楚列出外部服務成本與配額耗盡時的行為。
