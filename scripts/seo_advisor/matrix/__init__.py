"""AI 矩陣營運系統（AI Matrix Operating System）。

上層統籌層：NORA 總控接收一句目標，判斷情境、派工給 20+ 位 AI 工作夥伴
角色協作，各角色透過 engine adapter 執行（盡量接現有引擎），最後整合成
一份可執行交付物。角色定義為資料驅動（assets/roles.yaml）。

規格與協作規則見專案根目錄 .collab-rules.md。
"""
