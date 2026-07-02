"""Meta 廣告優化專家（Meta Ads Mode）。

診斷 Meta 廣告帳戶、產出優化建議與 dry-run 行動計畫。AdsProvider 抽象層
可切換 Meta / Mock。所有動用真實預算的操作都受 AdsSafetyPolicy 多重防護，
且會擴大花費的動作預設全部鎖住。規格見 ../../docs/meta_ads_mode.md。
"""
