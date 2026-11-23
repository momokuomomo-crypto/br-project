"""公式サイトへの取得（02_01 2章）。

* 1プロセスあたり最小間隔 MIN_INTERVAL 秒でアクセスする（サイトへの負荷配慮）。
* 一時的なエラー（接続失敗・5xx・429）は最大 RETRIES 回まで待って再試行する。
"""
from __future__ import annotations

import io
import threading
import time

import requests

BOATRACE = "https://www.boatrace.jp/owpc/pc/race"
MBRACE = "https://www1.mbrace.or.jp/od2"
USER_AGENT = "br-project/1.0 (personal research; low-rate collector)"
MIN_INTERVAL = 1.0
RETRIES = 4
TIMEOUT = 30


class Client:
    def __init__(self, min_interval: float = MIN_INTERVAL):
        self.session = requests.Session()
        self.session.headers["User-Agent"] = USER_AGENT
        self.min_interval = min_interval
        self._lock = threading.Lock()
        self._last = 0.0

    def _wait(self) -> None:
        with self._lock:
            now = time.monotonic()
            delay = self._last + self.min_interval - now
            if delay > 0:
                time.sleep(delay)
            self._last = time.monotonic()

    def get(self, url: str, params: dict | None = None) -> requests.Response | None:
        """200ならResponse、404ならNone。それ以外は再試行後に例外。"""
        last_err: Exception | None = None
        for attempt in range(RETRIES + 1):
            self._wait()
            try:
                r = self.session.get(url, params=params, timeout=TIMEOUT)
            except requests.RequestException as e:
                last_err = e
            else:
                if r.status_code == 200:
                    return r
                if r.status_code == 404:
                    return None
                last_err = RuntimeError(f"HTTP {r.status_code}: {r.url}")
            time.sleep(min(60, 5 * 2 ** attempt))
        raise RuntimeError(f"取得に失敗しました: {url} {params or ''}: {last_err}")

    def page(self, kind: str, hd: str, jcd: str | None = None, rno: int | None = None) -> str | None:
        params = {"hd": hd}
        if jcd is not None:
            params["jcd"] = jcd
        if rno is not None:
            params["rno"] = str(rno)
        r = self.get(f"{BOATRACE}/{kind}", params)
        if r is None:
            return None
        r.encoding = "utf-8"
        return r.text

    def lzh_text(self, kind: str, hd: str) -> str | None:
        """番組表（kind="B"）・競走成績（kind="K"）のLZHを取得し、Shift_JISの本文を返す。

        hd は YYYYMMDD。ファイルが無い（非開催・未公開）場合は None。
        """
        yymmdd = hd[2:]
        url = f"{MBRACE}/{kind}/{hd[:6]}/{kind.lower()}{yymmdd}.lzh"
        r = self.get(url)
        if r is None or len(r.content) < 30:
            return None
        return decode_lzh(r.content)


def decode_lzh(data: bytes) -> str:
    import lhafile  # 遅延import（テストでは不要な場合がある）

    archive = lhafile.Lhafile(io.BytesIO(data))
    names = archive.namelist()
    if not names:
        raise ValueError("LZHに中身がありません")
    raw = archive.read(names[0])
    return raw.decode("cp932", errors="replace").replace("\r\n", "\n")
