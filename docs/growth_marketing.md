# 成長行銷模組（Growth Marketing）

補齊一個成熟網路行銷團隊該有、但先前專案缺少的能力：**歸因追蹤、轉換率
優化、跨渠道成效分析**。三項都可用 `mock` / 純邏輯免金鑰試玩。

```bash
seo-advisor growth demo   # 一次示範 UTM + CRO + 成效分析，全部免金鑰
```

## 1. UTM 歸因規劃（`growth utm`）

為行銷團隊建立一致的 campaign 命名規範與 UTM 標記，避免流量在報表中被拆成
多組來源、或歸因不清。純邏輯，不需外部 API。

```bash
seo-advisor growth utm --url https://example.com/promo --channels google,facebook,email,line
```

- 依常見渠道自動產生一致命名的 tagged URL（source/medium/campaign/content）。
- 歸因衛生檢查：缺必要欄位、大小寫混用、含中文/空格、跨渠道 campaign 重用。

## 2. CRO 落地頁優化（`growth cro`）

診斷落地頁的轉換率優化機會並設計 A/B 測試。有 URL 時透過 HTTPConnector
（read-only）抓頁面分析；抓不到或用 `--no-fetch` 時退回通用 CRO 規劃。

```bash
seo-advisor growth cro --url https://example.com/landing
```

- 六類檢查：結構（H1）、CTA、表單、信任訊號、訊息一致性（title/H1/CTA）、
  速度提示。
- 產出 A/B 測試點子（含假設、對照/實驗版、主要指標、樣本量提醒）。

## 3. 跨渠道成效分析（`growth analytics`）

蒸餾成效分析師的判斷，做四類診斷：追蹤缺漏、高流量低轉換、高成本低回報、
擴量機會。用觀察到的中位數轉換率做動態門檻，避免用固定值誤判。

```bash
seo-advisor growth analytics --provider mock --since-days 30       # 免金鑰試玩
seo-advisor growth analytics --provider ga4 --property <GA4_ID>    # 真實資料（需憑證）
```

- **一律 read-only**：GA4 / Search Console / Google Ads adapter 只讀取成效
  指標，即使是 Google Ads 也**絕不修改**任何廣告設定或預算——廣告變更一律
  走 Meta 廣告模式的 dry-run 計畫流程。
- 真實 Google API 整合（GA4/GSC/Google Ads）為 optional adapter，需要對應
  的環境變數憑證；無憑證時用 `--provider mock` 完整試玩。真實 API 呼叫的
  實作規劃於後續版本。

## 與矩陣系統的關係

矩陣系統（`seo-advisor matrix`）的 ORION（數據分析）、CODY（銷售頁）、
MIRA（CRM/Email）等角色，在未來版本會把成長行銷模組接為專屬引擎。目前
成長行銷能力可透過 `seo-advisor growth` 獨立使用。
