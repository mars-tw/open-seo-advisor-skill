# 行銷方法論知識庫（中性化蒸餾）

`scripts/seo_advisor/knowledge/methodology.yaml` 收錄了四大領域、共 50 條
可執行的行銷/電商檢核原則，供各模組（ecommerce、Content Writer、Meta Ads、
growth、matrix 角色）共用引用。

## 四大領域

| 領域 | 內容 | 條數 |
|---|---|---|
| `ecommerce` | Amazon / 電商平台 listing 優化 | 12 |
| `paid_ads_funnel` | 付費廣告 / 漏斗（hook、受眾分層、素材疲勞、再行銷、歸因） | 12 |
| `content_brand` | 內容 / 品牌成長（主題群集、E-E-A-T、跨平台再利用、病毒傳播） | 12 |
| `growth_hacking` | 轉換 / 成長駭客（AARRR、北極星指標、實驗設計、留存、病毒係數） | 14 |

每條原則的格式為「檢核點（check）+ 為什麼/怎麼做（why）」，動作導向，可被
程式或 LLM 當檢核清單使用。

## 合規原則（重要）

這份知識庫是**中性化蒸餾**的成果，嚴守以下紅線：

- **只萃取業界公開、廣泛認可的通用方法論原則**，轉成不具名、可執行的檢核點。
- **不使用任何真實專家人名、課程名或商標**，不逐字複製任何人的付費課程或著作，
  不宣稱「這是某某人本人的方法」，也不暗示與任何專家有關聯或代言。
- 與 `docs/content_writer_guide.md` 的精神一致：蒸餾成通用原則、避免侵權、
  不綁定單一權威來源。

有一條自動化測試（`tests/test_knowledge.py` 的 `test_methodology_is_neutralized_
no_expert_names`）會在 CI 持續檢查知識庫不含具名內容，守護這條紅線。

## 內容可信度與時效性（免責聲明）

這份知識庫解決的是「著作權/商標」風險（見上方合規原則），但另有一類不同性質
的風險需要誠實揭露：**內容本身的正確性與時效性**。

- 每個領域都有 `last_reviewed` 欄位，標記這批原則**最後一次被人工檢視確認**
  的日期——這不代表持續監控更新，也不代表在該日期之後仍完全適用。
- 這些原則是通用行銷/電商實務的蒸餾整理，**效果因產業、市場、時機、執行細節
  而異**，不構成投資、行銷成效或業績的保證。
- 平台演算法與政策（例如 Amazon 的排序機制、Meta 的廣告政策）會隨時間變動，
  遇到與本檔內容衝突時，請以平台官方最新規範為準。
- 貢獻者新增或修改原則時，請一併更新對應領域的 `last_reviewed` 日期。

## 目的

讓任何人——個人賣家、小型團隊、開源貢獻者——都能**免費**用這些被蒸餾成
中性化檢核清單的方法論來自我健檢與優化，不需要花錢買課程或請人代操。這與整個
專案「開源、免金鑰、不綁定單一廠商」的精神一致。

## 如何載入

```python
from seo_advisor.knowledge import load_methodology, get_domain

domains = load_methodology()            # {domain_id: MethodologyDomain}
ecommerce = get_domain("ecommerce")     # 取單一領域
for principle in ecommerce.principles:
    print(principle.check, principle.why)
```
