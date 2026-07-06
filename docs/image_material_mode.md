# GPT 產圖素材專家（Image Material Mode）

為廣告、社群、文章、落地頁產生圖像素材。圖像生成 provider 抽象化，可切換
OpenAI / Mock（未來可加 Stability、本地模型），符合專案「不綁定單一廠商」
的原則。

## 觸發方式

```bash
# 產生圖像素材（需要 OPENAI_API_KEY）
seo-advisor image generate --prompt "SEO 健檢工具的社群宣傳圖" \
  --use-case social --aspect 1:1 --variants 4 --out ./image-assets

# 不需要任何 API 金鑰的示範（用 mock provider 產生佔位圖）
seo-advisor image demo

# 讀取 Content Writer 報告，為文章產生配圖
seo-advisor image from-content --content-report ./content-report/content-report.json --out ./content-images
```

`--provider mock` 產生佔位 PNG，讓沒有 API 金鑰的人也能完整跑完流程並看到
manifest 長相；`--provider openai`（預設）呼叫 OpenAI Images API（`gpt-image-1`）。

## 合規前置檢查（安全底線）

在把任何 prompt 送給圖像生成 API 之前，`compliance.py` 會先用規則攔截明顯
違規的需求，攔截到就直接拒絕、不送出請求（也順便省下 API 花費）：

- 冒用或仿造他人品牌、商標、logo
- 未授權使用真人、名人、政治人物肖像
- 誤導性的療效／獲利保證（「保證賺」「根治」等）
- 偽造平台介面、假通知、假新聞截圖
- 仿冒特定在世藝術家的風格

廣告用途（`--use-case meta_ad`）的素材會標記 `human_review_required=True`，
提醒上架前需人工確認是否符合廣告政策與當地法規，並建議揭露為 AI 生成內容。

## 支援的用途與版位

| use-case | 說明 |
|---|---|
| `meta_ad` | Meta 廣告素材（標記需人工審核） |
| `social` | 社群貼文圖 |
| `blog_hero` | 文章封面圖 |
| `blog_inline` | 文章內文插圖 |
| `og_image` | 分享預覽圖（Open Graph） |
| `landing_page` | 落地頁視覺 |

長寬比支援 `1:1` / `4:5` / `9:16` / `16:9` / `3:2` / `2:3`。OpenAI 原生尺寸
有限（1024x1024 / 1024x1536 / 1536x1024），非原生比例會用最接近的尺寸生成，
並在 manifest 標註「需裁切」。

## 輸出

- 圖檔（PNG）
- `image-manifest.json`：每張素材的 prompt、尺寸、用途、合規註記、
  AI 生成揭露建議。

## 與其他模式串接

- **Content Writer**：`seo-advisor image from-content` 讀取文章報告的主題，
  產生對應的封面配圖。
- **Meta 廣告**：`seo-advisor image from-ads ads-report.json` 讀取廣告診斷
  報告，把「素材疲勞、CTR 下降」等問題自動轉成新素材方向 brief（建議測試
  痛點/成果/信任型等不同創意角度，而非換顏色）。本模式只產素材，實際上架
  仍由廣告模式（且受 `AdsSafetyPolicy` 約束）處理。

  ```bash
  seo-advisor ads demo --out ./ads               # 產生 ads-report.json
  seo-advisor image from-ads --ads-report ./ads/ads-report.json
  ```

  **成本安全**：`from-ads` **預設只產出 brief（image-brief.md/json），不呼叫
  API、不花錢**。要真的產圖必須明確加 `--generate`；若主要素材機會信心較低
  （可能不是素材問題，或缺 frequency/CTR 佐證），還需再加 `--confirm-low-confidence`
  才會產圖，避免白花錢。純技術/預算/受眾/追蹤問題不會被誤轉成產圖任務。
