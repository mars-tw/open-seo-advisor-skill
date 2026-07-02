# 電商 Listing 健檢模式（Ecommerce）

運用「行銷方法論知識庫」中電商領域的**中性化蒸餾**檢核原則，對 Amazon / 電商
平台的 listing 做健檢，找出影響點擊與轉換的問題並給出改善建議。純邏輯、免金鑰。

## 觸發方式

```bash
# 免金鑰示範（內建範例 listing）
seo-advisor ecommerce demo

# 依 JSON 提供的 listing 資訊做健檢
seo-advisor ecommerce audit --input listing.json --out ./ecommerce-report
```

`listing.json` 欄位（對應 `EcommerceListing` 模型）：

```json
{
  "title": "商品標題",
  "bullet_points": ["賣點1", "賣點2", "..."],
  "backend_keywords": ["關鍵字1", "..."],
  "main_image_present": true,
  "secondary_image_count": 6,
  "has_a_plus_content": true,
  "review_count": 320,
  "rating": 4.5,
  "in_stock": true,
  "has_buy_box": true,
  "variations_count": 3
}
```

## 檢核項目

依電商方法論原則檢核，並依對轉換的影響分級：

- **庫存 / 購買入口**（P0/P1）：缺貨或失去主要購買入口會直接阻斷轉換，優先處理。
- **評分 / 評論**（P1/P2）：評分低於 4.0 明顯影響轉換；評論數過少代表社會證明不足。
- **主圖 / 副圖**（P1/P2）：缺主圖嚴重影響點擊；副圖不足無法回答購買疑慮。
- **標題**（P2）：過短未傳達品類差異、過長影響掃讀、關鍵字堆疊。
- **賣點 bullet points**（P2/P3）：少於 5 點或過短。
- **A+ 內容、後端關鍵字**（P3）：缺 A+ 信任說明；後端關鍵字偏少。
- **變體**（P2）：變體數量異常，需確認是否為真實規格差異。

每個發現都會標註**依據的方法論原則**，報告最後列出本次套用的完整檢核清單。

## 合規說明

本模式的檢核原則為**中性化蒸餾**——萃取業界公開、廣泛認可的電商經營方法論，
轉成不具名、可執行的檢核清單。**不使用任何真實專家人名、課程名或商標，也不
宣稱與任何特定專家有關聯或代言**。目的是讓任何人免費就能用這些方法論自我健檢，
不需購買課程或代操服務。與 `docs/content_writer_guide.md` 的合規精神一致。
