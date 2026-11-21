"""HTTP 요청 제한(프로세스 메모리 슬라이딩 윈도).

왜 필요한가
----------
공개 API·MCP 에는 인증이 없어 한 클라이언트가 초당 수십 건을 보낼 수 있었다.
무료 월 한도(250회)는 월 단위라 순간 폭주를 막지 못하고, 공공 API 키가 걸린
경로는 한 번의 폭주로 하루 쿼터가 소진될 수 있다(외부 코드 검수 제보: rate limit 부재).

무엇을 남기는가 / 남기지 않는가
------------------------------
- 제한 키는 **프로세스가 기동할 때 만든 임의 salt + 클라이언트 주소**의 짧은
  BLAKE2b 해시다. 주소 원문은 어디에도 저장하지 않고, DB·`/v1/stats`·로그에
  쓰지 않으며, 프로세스가 죽으면 salt 와 함께 사라진다(재기동 후에는 새 키).
- 카운터는 메모리에만 있고 TTL 이 지나면 비운다. 개인 식별자로 쓸 수 있는 값을
  디스크에 남기지 않는다는 `usage.py` 의 계약과 같은 선을 지킨다.
"""
from __future__ import annotations

import hashlib
import threading
import time
from collections import deque
from typing import Any, Callable, Deque, Dict, Optional

DEFAULT_LIMIT_PER_MINUTE = 120
DEFAULT_WINDOW_SECONDS = 60.0


def client_key(salt: bytes, host: str) -> str:
    """클라이언트 주소 → 일시 해시 키(원문은 반환하지 않는다)."""
    material = (salt or b"") + str(host or "").encode("utf-8", "ignore")
    return hashlib.blake2b(material, digest_size=8).hexdigest()


class SlidingWindowLimiter:
    """키별 슬라이딩 윈도 카운터(스레드 안전).

    `check()` 는 요청 1건을 세고, 한도를 넘으면 `allowed=False` 와 함께
    다시 시도할 수 있는 초(`retry_after`)를 돌려준다.
    """

    def __init__(self, limit: int = DEFAULT_LIMIT_PER_MINUTE,
                 window_seconds: float = DEFAULT_WINDOW_SECONDS,
                 clock: Optional[Callable[[], float]] = None,
                 max_keys: int = 4096) -> None:
        self.limit = max(1, int(limit))
        self.window = max(1.0, float(window_seconds))
        self._clock = clock or time.monotonic
        self._max_keys = max(16, int(max_keys))
        self._hits: Dict[str, Deque[float]] = {}
        self._lock = threading.Lock()

    def _prune(self, key: str, now: float) -> Deque[float]:
        stamps = self._hits.get(key)
        if stamps is None:
            stamps = deque()
            self._hits[key] = stamps
        cutoff = now - self.window
        while stamps and stamps[0] <= cutoff:
            stamps.popleft()
        return stamps

    def _sweep(self, now: float) -> None:
        """키가 너무 많아지면 빈 윈도 키를 버린다(메모리 상한)."""
        if len(self._hits) <= self._max_keys:
            return
        cutoff = now - self.window
        for key in [k for k, v in self._hits.items() if not v or v[-1] <= cutoff]:
            self._hits.pop(key, None)

    def check(self, key: str, limit: Optional[int] = None) -> Dict[str, Any]:
        cap = max(1, int(limit if limit is not None else self.limit))
        now = self._clock()
        with self._lock:
            stamps = self._prune(key, now)
            if len(stamps) >= cap:
                retry_after = max(1, int(round(stamps[0] + self.window - now)))
                return {"allowed": False, "limit": cap, "remaining": 0,
                        "retry_after": retry_after, "window_seconds": int(self.window)}
            stamps.append(now)
            remaining = max(0, cap - len(stamps))
            self._sweep(now)
        return {"allowed": True, "limit": cap, "remaining": remaining,
                "retry_after": 0, "window_seconds": int(self.window)}

    def snapshot(self, key: str) -> Dict[str, Any]:
        """현재 창의 사용량(테스트ㆍ점검용, 세지 않는다)."""
        now = self._clock()
        with self._lock:
            stamps = self._prune(key, now)
            return {"used": len(stamps), "limit": self.limit}
