# Meta 廣告優化專家（Meta Ads Mode）

診斷 Meta（Facebook / Instagram）廣告帳戶、產出優化建議與 dry-run 行動計畫。

## 安全底線（最重要）

這個模式會接觸到**真實廣告預算**，因此整體流程刻意設計成多層防護：

```
audit（唯讀診斷）
  → plan（dry-run 行動計畫，不修改任何東西）
  → 人工檢視 action-plan.json
  → 精確確認字串
  → apply（實際套用，目前尚未開放）
  → change-log（可回滾）
```

`AdsSafetyPolicy`（`scripts/seo_advisor/ads/models.py`）把這些原則變成程式碼
強制約束，**預設值刻意保守**：

- `dry_run=True`：預設不寫入任何東西。
- 會「擴大花費」的動作一律預設禁止，需逐項明確開啟：
  - `allow_budget_increase=False`（增加預算）
  - `allow_activate_entities=False`（恢復投放）
  - `allow_campaign_pause=False`（暫停整個活動）
- 預算變更有多重上限：單一實體百分比上限、單一實體金額上限、單次總增額上限。
- 資料量門檻：觀察天數或花費不足時不建議動作，避免根據雜訊做決定。
- 帳戶白名單：`allowed_ad_accounts` 限制只能操作指定帳戶。

> **目前版本（v0.1.3）**：`seo-advisor ads apply`（自動化代操）**尚未開放**。
> 目前只提供 audit（唯讀）與 plan（dry-run），你可以檢視 `action-plan.json`
> 後，手動到 Meta 廣告管理員套用。自動化 apply 會在防護與回滾機制經充分
> 驗證後，於後續版本才逐步開放，且擴大花費的動作預設仍鎖住。

## 觸發方式

```bash
# 唯讀健檢（不需要修改權限）
seo-advisor ads audit --account act_123456 --since 30d --out ./ads-report

# 產出 dry-run 行動計畫
seo-advisor ads plan --account act_123456 --since 30d --out ./ads-plan

# 不需要 Meta API 金鑰的示範
seo-advisor ads demo
```

`--provider mock` 可用內建假帳戶資料試玩，`--provider meta`（預設）連接真實
Meta Marketing API（需環境變數 `META_ACCESS_TOKEN`，選配 `META_APP_ID` /
`META_APP_SECRET` 以啟用 appsecret proof）。

## 診斷項目

- **追蹤設定**：Pixel 是否存在（缺少為 P0，等於盲投）、是否有核心轉換事件。
- **成效診斷**：高花費低 ROAS（預算浪費）、素材疲勞（高頻次 + 低 CTR）、
  擴量候選（低花費高 ROAS）、資料量是否足以做決策。
- （後續版本）活動結構、受眾重疊、預算配置、A/B test 設計。

## 動用預算的操作與防護

| 動作 | MVP 是否允許 | 防護 |
|---|---|---|
| 暫停低效素材（pause ad） | ✅（dry-run 計畫） | 記錄 rollback snapshot |
| 降低每日預算 | ✅（dry-run 計畫） | 不得低於最低預算 |
| 增加每日預算 | ❌ 預設禁止 | 需 `allow_budget_increase` + 金額上限 + 精確確認 |
| 啟用/恢復投放 | ❌ 預設禁止 | 需 `allow_activate_entities` |
| 暫停整個活動 | ❌ 預設禁止 | 需 `allow_campaign_pause` |

「擴量候選」這類需要增加預算的建議，會在報告中呈現，但**不會**自動排入
dry-run 行動計畫——需要使用者自行判斷後手動調整。

## 與其他模式串接

- 素材疲勞的廣告，可用**產圖素材專家**（`seo-advisor image`）產生新的
  素材變體替換。
- Meta 廣告 API 接入依據 Meta Business SDK（需註冊 App、加入 Marketing API
  product、使用 access token）。read-only audit 至少需 `ads_read` 權限，
  未來的代操需要 `ads_management`。
