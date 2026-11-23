"""期待値派の確率モデル（04_01 4章）。

3連単120通りに対する条件付きロジット:

    score(i,j,k) = a * log q(i,j,k) + b1・x_i + b2・x_j

q は3連単オッズの逆数を合計1に正規化した「市場の見立て」、x は艇の特徴量
（レース内で標準化）。p = softmax(score) を推定確率とする。
a < 1 なら「人気の組合せは見立てほど来ず、穴目は見立てより来る」という
市場のクセを補正する。b1・b2 は1着・2着に来やすい艇の特徴の補正。
L2正則化（係数 b のみ）つきニュートン法で、実際の的中組合せの対数尤度を最大化する。
"""
from __future__ import annotations

import json
from dataclasses import dataclass

import numpy as np

from br.analysis.dataset import EX_FROM_TRI, FEATURES, PERMS, WIN_FROM_TRI, Races

FIRST = np.array([a for a, _, _ in PERMS])
SECOND = np.array([b for _, b, _ in PERMS])
L2 = 1.0
CHUNK = 4000


def design(r: Races) -> np.ndarray:
    """(N, 120, P) の説明変数。P = 1 + 2F。"""
    x1 = r.x[:, FIRST, :]
    x2 = r.x[:, SECOND, :]
    return np.concatenate([r.log_q[:, :, None], x1, x2], axis=2)


@dataclass
class Model:
    w: np.ndarray

    @property
    def n_params(self) -> int:
        return len(self.w)

    def scores(self, r: Races) -> np.ndarray:
        out = np.empty(r.log_q.shape)
        for s in range(0, len(r.keys), CHUNK):
            sub = r.subset(np.arange(s, min(s + CHUNK, len(r.keys))))
            out[s:s + CHUNK] = design(sub) @ self.w
        return out

    def proba(self, r: Races) -> np.ndarray:
        z = self.scores(r)
        z -= z.max(axis=1, keepdims=True)
        p = np.exp(z)
        return p / p.sum(axis=1, keepdims=True)

    def to_json(self) -> dict:
        names = ["a_log_q"] + [f"b1_{f}" for f in FEATURES] + [f"b2_{f}" for f in FEATURES]
        return {"weights": dict(zip(names, map(float, self.w)))}

    @classmethod
    def from_json(cls, d: dict) -> "Model":
        return cls(np.array(list(d["weights"].values()), dtype=float))


def market_only(n_features=len(FEATURES)) -> Model:
    w = np.zeros(1 + 2 * n_features)
    w[0] = 1.0
    return Model(w)


def fit(r: Races, iters: int = 30, tol: float = 1e-6) -> Model:
    if len(r.keys) == 0:
        return market_only()
    model = market_only()
    p_dim = model.n_params
    reg = np.full(p_dim, L2)
    reg[0] = 0.0
    prev = -np.inf
    for _ in range(iters):
        g = np.zeros(p_dim)
        h = np.zeros((p_dim, p_dim))
        ll = 0.0
        for s in range(0, len(r.keys), CHUNK):
            sub = r.subset(np.arange(s, min(s + CHUNK, len(r.keys))))
            X = design(sub)                         # (n,120,P)
            z = X @ model.w
            z -= z.max(axis=1, keepdims=True)
            p = np.exp(z)
            p /= p.sum(axis=1, keepdims=True)
            idx = np.arange(len(sub.keys))
            ll += np.log(p[idx, sub.winner]).sum()
            xw = X[idx, sub.winner]                 # (n,P)
            ex = np.einsum("nc,ncp->np", p, X)      # (n,P)
            g += (xw - ex).sum(axis=0)
            exx = np.einsum("nc,ncp,ncq->pq", p, X, X)
            h -= exx - ex.T @ ex
        ll -= 0.5 * (reg * model.w ** 2).sum()
        g -= reg * model.w
        h -= np.diag(reg)
        step = np.linalg.solve(h, g)
        model = Model(model.w - step)
        if abs(ll - prev) < tol * max(1.0, abs(ll)):
            break
        prev = ll
    return model


def log_loss(model: Model, r: Races) -> float:
    p = model.proba(r)
    return float(-np.log(p[np.arange(len(r.keys)), r.winner]).mean())


def marginals(p_tri: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """3連単確率から2連単（30）・単勝（6）の確率を求める。"""
    return p_tri @ EX_FROM_TRI.T, p_tri @ WIN_FROM_TRI.T


def save(model: Model, path, meta: dict) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump({**model.to_json(), **meta}, f, ensure_ascii=False, indent=2)
