"""矩陣 engine 抽象介面：把一個 Assignment 執行成 AgentRunResult。

每個角色透過對應的 engine 執行。engine 盡量接到現有已實作的引擎
（Consultant / Content Writer / Meta Ads / Image Material），沒有現成引擎的
角色走 GenericLLMEngine，測試/demo 走 MockEngine。
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from seo_advisor.matrix.models import AgentRunResult, Assignment, TaskRequest


class Engine(ABC):
    @abstractmethod
    def run(self, assignment: Assignment, task: TaskRequest) -> AgentRunResult:
        """執行一個派工單，回傳正規化的角色結果。"""
