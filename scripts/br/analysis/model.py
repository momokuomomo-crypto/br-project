"""期待値派の確率モデルと想定オッズモデル（04_01 4章）。

確率モデル：3連単120通りに対する条件付きロジット

    score(i,j,k) = b1・x_i + b2・x_j + b3・x_k,   p = softmax(score)

x は艇の特徴量（枠番ダミー＋レース内で標準化した数値）。b1〜b3 は1〜3着に来る艇の特徴の重み。
L2正則化つきニュートン法で、実際の的中組合せの対数尤度を最大化する。

想定オッズモデル：オッズの履歴が手に入らないため、「その組合せが的中したときの払戻」を
過去の払戻実績から推定する。券種ごとに、的中した組合せの log(払戻) を組合せの特徴量
（着順位置ごとの艇の特徴量）で回帰（リッジ）し、exp(予測 + 残差分散/2) を想定払戻とする。
"""
from __future__ import annotations

import json
from dataclasses import dataclass

import numpy as np

from br.analysis.dataset import EX_FROM_TRI, EX_PAIRS, FEATURES, PERMS, WIN_FROM_TRI, Races

POS = {"trifecta": [np.array([a for a, _, _ in PERMS]), np.array([b for _, b, _ in PERMS]), np.array([c for _, _, c in PERMS])],
       "exacta": [np.array([a for a, _ in EX_PAIRS]), np.array([b for _, b in EX_PAIRS])],
       "win": [np.arange(6)]}
L2 = 1.0
CHUNK = 2000


def combo_design(x: np.ndarray, bet_type: str = "trifecta") -> np.ndarray:
    """(n, 6, F) → (n, n_combo, len(pos)*F)"""
    return np.concatenate([x[:, idx, :] for idx in POS[bet_type]], axis=2)


@dataclass
class Model:
    w: np.ndarray

    def proba(self, r: Races) -> np.ndarray:
        out = np.empty((len(r), 120))
        for s in range(0, len(r), CHUNK):
            z = combo_design(r.x[s:s + CHUNK]) @ self.w
            z -= z.max(axis=1, keepdims=True)
            p = np.exp(z)
            out[s:s + CHUNK] = p / p.sum(axis=1, keepdims=True)
        return out

    def to_json(self) -> dict:
        names = [f"b{pos}_{f}" for pos in (1, 2, 3) for f in FEATURES]
        return dict(zip(names, map(float, self.w)))


def baseline(r: Races) -> np.ndarray:
    """比較用：枠番だけで決まる確率（学習期間の3連単の出現率）。"""
    return np.full((len(r), 120), 1 / 120)


def fit(r: Races, iters: int = 25, tol: float = 1e-7) -> Model:
    P = 3 * len(FEATURES)
    w = np.zeros(P)
    prev = -np.inf
    for _ in range(iters):
        g = np.zeros(P)
        h = np.zeros((P, P))
        ll = 0.0
        for s in range(0, len(r), CHUNK):
            X = combo_design(r.x[s:s + CHUNK])
            win = r.winner[s:s + CHUNK]
            n = len(win)
            z = X @ w
            z -= z.max(axis=1, keepdims=True)
            p = np.exp(z)
            p /= p.sum(axis=1, keepdims=True)
            idx = np.arange(n)
            ll += np.log(p[idx, win]).sum()
            ex = np.einsum("nc,ncp->np", p, X)
            g += (X[idx, win] - ex).sum(axis=0)
            Xf = X.reshape(-1, P)
            h -= (Xf * p.reshape(-1)[:, None]).T @ Xf - ex.T @ ex
        ll -= 0.5 * L2 * (w ** 2).sum()
        g -= L2 * w
        h -= L2 * np.eye(P)
        w = w - np.linalg.solve(h, g)
        if abs(ll - prev) < tol * max(1.0, abs(ll)):
            break
        prev = ll
    return Model(w)


def log_loss(p: np.ndarray, r: Races) -> float:
    return float(-np.log(np.clip(p[np.arange(len(r)), r.winner], 1e-12, None)).mean())


def marginals(p_tri: np.ndarray) -> dict[str, np.ndarray]:
    return {"trifecta": p_tri, "exacta": p_tri @ EX_FROM_TRI.T, "win": p_tri @ WIN_FROM_TRI.T}


@dataclass
class PayoutModel:
    """券種ごとの想定払戻（100円あたり）。"""
    coef: dict  # bet_type -> (theta, sigma2)

    def predict(self, r: Races, bet_type: str) -> np.ndarray:
        theta, s2 = self.coef[bet_type]
        theta = np.asarray(theta)
        out = np.empty((len(r), len(POS[bet_type][0])))
        for s in range(0, len(r), CHUNK):
            out[s:s + CHUNK] = np.exp(theta[0] + combo_design(r.x[s:s + CHUNK], bet_type) @ theta[1:] + s2 / 2)
        return out

    def to_json(self) -> dict:
        return {k: {"theta": list(map(float, t)), "sigma2": float(s)} for k, (t, s) in self.coef.items()}

    @classmethod
    def from_json(cls, d: dict) -> "PayoutModel":
        return cls({k: (np.array(v["theta"]), v["sigma2"]) for k, v in d.items()})


def fit_payout(r: Races, ridge: float = 1.0) -> PayoutModel:
    coef = {}
    for bt in ("win", "exacta", "trifecta"):
        pay = r.pay[bt]
        n_idx, c_idx = np.nonzero(pay > 0)
        if len(n_idx) < 50:
            continue
        # 的中した組合せの特徴量だけを作る（全組合せの行列は作らない）
        X = np.concatenate([np.ones((len(n_idx), 1))] + [r.x[n_idx, idx[c_idx], :] for idx in POS[bt]], axis=1)
        y = np.log(pay[n_idx, c_idx])
        reg = ridge * np.eye(X.shape[1])
        reg[0, 0] = 0
        theta = np.linalg.solve(X.T @ X + reg, X.T @ y)
        resid = y - X @ theta
        coef[bt] = (theta, float(resid.var()))
    return PayoutModel(coef)


def save(path, model: Model, payout: PayoutModel, meta: dict) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"weights": model.to_json(), "payout": payout.to_json(), **meta}, f, ensure_ascii=False, indent=2)


def load_saved(path) -> tuple[Model, PayoutModel, dict]:
    d = json.loads(open(path, encoding="utf-8").read())
    return Model(np.array(list(d["weights"].values()), dtype=float)), PayoutModel.from_json(d["payout"]), d
