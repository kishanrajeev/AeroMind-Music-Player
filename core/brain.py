"""Mushroom body: sparse expansion + reward-modulated MBON weights (spec §7).

Pipeline per track:

    z-scored features -> KC sparse expansion (10% of 2000) -> MBON (w . kc)

Learning is the three-factor rule:

    delta_w = eta * reward * kc_activity      (reward in {-1, 0, +1})

Everything needed to reproduce the KC basis is persisted in ``data/brain.npz``
(spec §9): weights, projection matrix, z-score stats, feature order hash, seed.
Seeding alone is not enough — if the code path changes, learned weights must
still apply to the same basis they were trained on.

Cold start: w = 0 -> every sigmoid output is 0.5. The engine normalizes brain
scores within the candidate pool (spec §8), so that is safe rather than dead.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

from core.library import FEATURE_NAMES, feature_list_hash
from core.types import KC_DIM, VALID_REWARDS, BrainState

if TYPE_CHECKING:
    from core.index import IndexData

BRAIN_VERSION = "brain-1"
DEFAULT_SEED = 20261010
#: eta is scaled for the 200-active KC code: one feedback shifts the raw MBON
#: drive by ~eta * active_count = 1.0 (sigmoid ~0.27 / 0.73), so ~5 feedbacks
#: give clear structure without instantly saturating the sigmoid.
DEFAULT_ETA = 1.0 / 200.0
KC_ACTIVE_FRACTION = 0.10  # spec §7: 5-10% of Kenyon cells active
EPSILON = 1e-9
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
BRAIN_PATH = DATA_DIR / "brain.npz"


class BrainMismatch(RuntimeError):
    """Cached brain does not match the current features/config — rebuild it."""


def library_features_hash(features: np.ndarray) -> str:
    array = np.ascontiguousarray(np.asarray(features, dtype="<f4"))
    return hashlib.sha1(array.tobytes()).hexdigest()


def _sigmoid(values):
    return 1.0 / (1.0 + np.exp(-np.asarray(values, dtype=np.float64)))


class Brain:
    """Sparse expansion + one learnable MBON weight per Kenyon cell."""

    def __init__(
        self,
        projection: np.ndarray,
        weights: np.ndarray,
        z_mean: np.ndarray,
        z_std: np.ndarray,
        meta: dict[str, str],
    ):
        self.projection = projection  # (D, KC_DIM)
        self.weights = weights  # (KC_DIM,)
        self.z_mean = z_mean  # (D,)
        self.z_std = z_std  # (D,)
        self.meta = meta

    # -- construction -------------------------------------------------------
    @classmethod
    def create(
        cls,
        features: np.ndarray,
        seed: int = DEFAULT_SEED,
        eta: float = DEFAULT_ETA,
    ) -> "Brain":
        features = np.asarray(features, dtype=np.float64)
        if features.ndim != 2 or features.shape[0] == 0:
            raise ValueError("features must be a non-empty (N, D) matrix")

        z_mean = features.mean(axis=0)
        z_std = features.std(axis=0)
        z_std = np.where(z_std < EPSILON, 1.0, z_std)  # constant-column guard

        rng = np.random.default_rng(seed)
        projection = (
            rng.standard_normal((features.shape[1], KC_DIM)) / np.sqrt(features.shape[1])
        ).astype("float32")

        active = max(1, int(round(KC_DIM * KC_ACTIVE_FRACTION)))
        meta = {
            "brain_version": BRAIN_VERSION,
            "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "rng_seed": str(seed),
            "eta": str(eta),
            "kc_dim": str(KC_DIM),
            "pn_dim": str(features.shape[1]),
            "kc_active_fraction": str(KC_ACTIVE_FRACTION),
            "kc_active_count": str(active),
            "feature_list_hash": feature_list_hash(),
            "feature_names": "|".join(FEATURE_NAMES),
            "library_features_hash": library_features_hash(features),
            "feedback_count": "0",
        }
        return cls(
            projection=projection,
            weights=np.zeros(KC_DIM, dtype="float32"),
            z_mean=z_mean.astype("float32"),
            z_std=z_std.astype("float32"),
            meta=meta,
        )

    # -- state --------------------------------------------------------------
    @property
    def feature_dim(self) -> int:
        return int(self.projection.shape[0])

    @property
    def active_count(self) -> int:
        return int(self.meta["kc_active_count"])

    @property
    def feedback_count(self) -> int:
        return int(self.meta["feedback_count"])

    def project(self, features) -> np.ndarray:
        """PN step: z-score features, then the fixed random projection."""
        values = np.asarray(features, dtype=np.float64)
        normalized = (values - self.z_mean) / self.z_std
        return normalized.astype("float32") @ self.projection

    def kc_matrix(self, features) -> np.ndarray:
        """KC step: top-k pattern separation. (D,) -> (KC,), (N, D) -> (N, KC)."""
        pre = self.project(features)
        single = pre.ndim == 1
        rows = pre[None, :] if single else pre
        kc = np.zeros(rows.shape, dtype="float32")
        top = np.argsort(-rows, axis=1, kind="stable")[:, : self.active_count]
        np.put_along_axis(kc, top, 1.0, axis=1)
        return kc[0] if single else kc

    def valences(self, features) -> np.ndarray:
        """Raw MBON drive w . kc for one track or a whole matrix."""
        kc = self.kc_matrix(features)
        if kc.ndim == 1:
            return np.array([float(kc @ self.weights)], dtype=np.float64)
        return (kc @ self.weights).astype(np.float64)

    def state(self, track_id: str, features) -> BrainState:
        kc = self.kc_matrix(features)
        raw = float(kc @ self.weights)
        return BrainState(
            track_id=track_id,
            mbon_output=float(_sigmoid(raw)),
            kc_activity=tuple(float(value) for value in kc),
            weights=tuple(float(value) for value in self.weights),
            feedback_count=self.feedback_count,
        )

    # -- learning -----------------------------------------------------------
    def feedback(self, features, reward: int) -> None:
        """Three-factor update: delta_w = eta * reward * kc_activity."""
        if reward not in VALID_REWARDS:
            raise ValueError(f"reward must be one of {list(VALID_REWARDS)}")
        if reward == 0:
            return  # neutral: no plasticity, no counted signal
        kc = self.kc_matrix(features)
        eta = float(self.meta["eta"])
        self.weights = (self.weights + eta * reward * kc).astype("float32")
        self.meta["feedback_count"] = str(self.feedback_count + 1)

    # -- persistence --------------------------------------------------------
    def save(self, path: Path = BRAIN_PATH) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        with open(tmp, "wb") as handle:
            np.savez_compressed(
                handle,
                weights=self.weights.astype("float32"),
                projection=self.projection.astype("float32"),
                z_mean=self.z_mean.astype("float32"),
                z_std=self.z_std.astype("float32"),
                meta_json=np.array(json.dumps(self.meta, sort_keys=True)),
            )
        tmp.replace(path)

    @classmethod
    def load(
        cls,
        path: Path = BRAIN_PATH,
        *,
        expected_library_hash: str | None = None,
    ) -> "Brain":
        path = Path(path)
        if not path.exists():
            raise BrainMismatch(f"no brain at {path}")

        with np.load(path, allow_pickle=False) as npz:
            missing = [
                name
                for name in ("weights", "projection", "z_mean", "z_std", "meta_json")
                if name not in npz.files
            ]
            if missing:
                raise BrainMismatch(f"{path.name}: missing arrays {missing} — rebuild")
            meta = json.loads(str(npz["meta_json"]))
            weights = npz["weights"].astype("float32")
            projection = npz["projection"].astype("float32")
            z_mean = npz["z_mean"].astype("float32")
            z_std = npz["z_std"].astype("float32")

        if meta.get("brain_version") != BRAIN_VERSION:
            raise BrainMismatch(
                f"brain_version: {meta.get('brain_version')!r} != {BRAIN_VERSION!r} — rebuild"
            )
        if meta.get("feature_list_hash") != feature_list_hash():
            raise BrainMismatch("feature list changed — rebuild brain")
        if expected_library_hash is not None and meta.get("library_features_hash") != expected_library_hash:
            raise BrainMismatch("library features changed — rebuild brain")
        if weights.shape != (KC_DIM,):
            raise BrainMismatch(f"weights shape {weights.shape} != ({KC_DIM},)")
        if projection.shape[1] != KC_DIM or projection.shape[0] != z_mean.shape[0]:
            raise BrainMismatch(f"projection shape {projection.shape} does not match KC_DIM")
        if z_std.shape != z_mean.shape or np.any(z_std <= 0):
            raise BrainMismatch("invalid z-score stats — rebuild brain")

        return cls(projection, weights, z_mean, z_std, meta)


def ensure_brain(
    index: "IndexData",
    path: Path = BRAIN_PATH,
    seed: int = DEFAULT_SEED,
    eta: float = DEFAULT_ETA,
    force: bool = False,
) -> Brain:
    """Load a valid brain or create one (spec §9: mismatch -> rebuild)."""
    library_hash = library_features_hash(index.features)
    if path.exists() and not force:
        try:
            return Brain.load(path, expected_library_hash=library_hash)
        except BrainMismatch:
            pass
    brain = Brain.create(index.features, seed=seed, eta=eta)
    brain.save(path)
    return brain
