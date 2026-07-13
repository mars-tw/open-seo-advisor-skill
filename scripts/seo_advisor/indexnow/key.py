"""IndexNow key 的生成與格式驗證。

IndexNow 協定要求 key 是一組 8-128 字元、只含 `[A-Za-z0-9-]` 的字串，
放在網站可讀取的 `https://<host>/<key>.txt` 檔案裡（內容就是 key 本身），
作為「這次通知確實來自網站擁有者」的所有權驗證機制。
"""

from __future__ import annotations

import re
import secrets

_KEY_PATTERN = re.compile(r"^[A-Za-z0-9-]{8,128}$")


class InvalidIndexNowKeyError(ValueError):
    """key 格式不符合 IndexNow 協定要求時拋出。"""


def generate_key() -> str:
    """產生一組符合協定格式的隨機 key（64 字元十六進位，落在 8-128 範圍
    內，且只含允許的字元）。
    """
    return secrets.token_hex(32)


def validate_key_format(key: str) -> None:
    if not _KEY_PATTERN.match(key):
        raise InvalidIndexNowKeyError(
            f"key 格式不正確：必須是 8-128 字元，只能包含英數字與連字號（-）。"
            f"收到長度 {len(key)} 的字串。可以用 `seo-advisor indexnow key generate` 產生一組合法的 key。"
        )
