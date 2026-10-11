"""Mushroom body: sparse expansion + reward-modulated MBON weights (spec §7).

Pipeline per track:

    raw 9-d features -> z-score -> whitening -> KC random projection
                     -> top-k sparse code (5-10% of 2000 cells) -> MBON (w . kc)

Learning is the three-factor rule:

    delta_w = drive * reward * kc_activity / active_count   (reward in {-1, 0, +1})

Dividing by the active count keeps one feedback's total drive constant no matter
how sparse the track's code is, and the weights are clipped so repeated feedback
cannot blow up. The readout subtracts the learned DC component (mean weight), so
a track that has nothing in common with the feedback history sits at the neutral
midpoint instead of inheriting every skip the library has ever seen; the result is
then standardized against the library's own valence spread before the sigmoid.

Everything needed to reproduce the KC basis is persisted in ``data/brain.npz``
(spec §9): weights, projection matrix (whitening is folded into it), z-score
stats, feature order hash, seed, activation rule. Seeding alone is not enough —
if the code path changes, learned weights must still apply to the same basis.
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

BRAIN_VERSION = "brain-2"
DEFAULT_SEED = 20261010
#: Total MBON drive one feedback event contributes, spread over the active cells:
#: a skip moves the skipped track by about -1 before the sigmoid, a listen +1.
DEFAULT_DRIVE = 1.0
#: Per-cell weight bound; keeps repeated feedback on the same cells finite.
WEIGHT_LIMIT = 1.0
#: Sparse code: mean active fraction and the half-range it varies over per track
#: (spec §7: top 5-10% active). The per-track count is driven by signal energy.
KC_ACTIVE_FRACTION = 0.075
KC_ACTIVE_SPREAD = 0.025
#: How hard the calibrated valence is pushed through the sigmoid; ~1.5 spreads
#: one standard deviation of taste to roughly 0.18 / 0.82.
DRIVE_GAIN = 1.5
#: The output of the last layer is sigmoid-normalized to [0, 1] (spec §7).
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
        self.projection = projection  # (D, KC_DIM), whitening folded in
        self.weights = weights  # (KC_DIM,)
        self.z_mean = z_mean  # (D,)
        self.z_std = z_std  # (D,)
        self.meta = meta
        names = meta.get("feature_names", "").split("|")
        self._energy_index = names.index("rms") if "rms" in names else 0
        # Library valence mean/std for the calibrated readout; set by calibrate().
        self._calibration: tuple[float, float] | None = None

    # -- construction -------------------------------------------------------
    @classmethod
    def create(
        cls,
        features: np.ndarray,
        seed: int = DEFAULT_SEED,
        drive: float = DEFAULT_DRIVE,
    ) -> "Brain":
        features = np.asarray(features, dtype=np.float64)
        if features.ndim != 2 or features.shape[0] == 0:
            raise ValueError("features must be a non-empty (N, D) matrix")

        z_mean = features.mean(axis=0)
        z_std = features.std(axis=0)
        z_std = np.where(z_std < EPSILON, 1.0, z_std)  # constant-column guard

        # Decorrelate the (strongly correlated) audio features before the random
        # projection: without this, every track's top-k lands on overlapping cells
        # and one skip leaks into the whole library.
        normalized = (features - z_mean) / z_std
        covariance = np.atleast_2d(np.cov(normalized, rowvar=False))
        eigenvalues, eigenvectors = np.linalg.eigh(covariance)
        # Relative floor: a near-constant direction must not get amplified into
        # numerical noise (condition number stays sane for degenerate libraries).
        floor = max(EPSILON, 1e-6 * float(eigenvalues.max()))
        whitening = (
            eigenvectors
            @ np.diag(1.0 / np.sqrt(np.maximum(eigenvalues, floor)))
            @ eigenvectors.T
        )

        rng = np.random.default_rng(seed)
        projection = (
            whitening
            @ (rng.standard_normal((features.shape[1], KC_DIM)) / np.sqrt(features.shape[1]))
        ).astype("float32")

        meta = {
            "brain_version": BRAIN_VERSION,
            "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "rng_seed": str(seed),
            "drive": str(drive),
            "kc_dim": str(KC_DIM),
            "pn_dim": str(features.shape[1]),
            "kc_active_fraction": str(KC_ACTIVE_FRACTION),
            "kc_active_spread": str(KC_ACTIVE_SPREAD),
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
        """Nominal active-cell count; the real per-track count varies 5-10%."""
        return int(round(KC_DIM * KC_ACTIVE_FRACTION))

    @property
    def feedback_count(self) -> int:
        return int(self.meta["feedback_count"])

    @property
    def calibrated(self) -> bool:
        return self._calibration is not None

    def project(self, features) -> np.ndarray:
        """PN step: z-score features, then the fixed (whitened) random projection."""
        values = np.asarray(features, dtype=np.float64)
        normalized = (values - self.z_mean) / self.z_std
        return normalized.astype("float32") @ self.projection

    def active_counts(self, features) -> np.ndarray:
        """Per-track number of Kenyon cells to activate (5-10% of KC_DIM).

        Tracks with more signal energy recruit a few more cells; the rule is
        deterministic from the persisted z-stats, so the basis is reproducible.
        """
        values = np.asarray(features, dtype=np.float64)
        z = (values - self.z_mean) / self.z_std
        energy = z[self._energy_index] if z.ndim == 1 else z[:, self._energy_index]
        fractions = KC_ACTIVE_FRACTION + KC_ACTIVE_SPREAD * np.tanh(energy)
        counts = np.rint(KC_DIM * np.atleast_1d(fractions)).astype(int)
        return np.clip(counts, 1, KC_DIM)

    def kc_matrix(self, features) -> np.ndarray:
        """KC step: top-k pattern separation. (D,) -> (KC,), (N, D) -> (N, KC)."""
        pre = self.project(features)
        single = pre.ndim == 1
        rows = pre[None, :] if single else pre
        kc = np.zeros(rows.shape, dtype="float32")
        for i, count in enumerate(self.active_counts(features)):
            k = int(count)
            top = np.argpartition(-rows[i], k - 1)[:k]
            kc[i, top] = 1.0
        return kc[0] if single else kc

    def valences(self, features) -> np.ndarray:
        """Centered MBON drive w . kc for one track or a whole matrix.

        Subtracting the mean weight removes the DC component that every feedback
        adds to the shared pool, so an unrelated track stays at drive ~0 even
        after many skips and the ranking reflects actual pattern overlap.
        """
        kc = self.kc_matrix(features)
        centered = self.weights - self.weights.mean()
        if kc.ndim == 1:
            return np.array([float(kc @ centered)], dtype=np.float64)
        return (kc @ centered).astype(np.float64)

    def calibrate(self, features: np.ndarray) -> None:
        """Cache the library's valence mean/std used by the calibrated readout."""
        scores = self.valences(features)
        self._calibration = (float(scores.mean()), float(scores.std()))

    def _calibrated(self, scores: np.ndarray) -> np.ndarray:
        mean, std = self._calibration if self._calibration is not None else (0.0, 1.0)
        return _sigmoid(DRIVE_GAIN * (scores - mean) / max(std, EPSILON))

    def outputs(self, features) -> np.ndarray:
        """Calibrated predicted enjoyment (1 track -> (1,), N tracks -> (N,))."""
        return self._calibrated(self.valences(features))

    def state(self, track_id: str, features) -> BrainState:
        kc = self.kc_matrix(features)
        centered = self.weights - self.weights.mean()
        raw = float(kc @ centered)
        return BrainState(
            track_id=track_id,
            mbon_output=float(self._calibrated(np.array([raw]))[0]),
            kc_activity=tuple(float(value) for value in kc),
            weights=tuple(float(value) for value in self.weights),
            feedback_count=self.feedback_count,
        )

    # -- learning -----------------------------------------------------------
    def feedback(self, features, reward: int) -> None:
        """Three-factor update: delta_w = drive * reward * kc_activity / active."""
        if reward not in VALID_REWARDS:
            raise ValueError(f"reward must be one of {list(VALID_REWARDS)}")
        if reward == 0:
            return  # neutral: no plasticity, no counted signal
        kc = self.kc_matrix(features)
        drive = float(self.meta.get("drive", DEFAULT_DRIVE))
        active = max(float(kc.sum()), 1.0)
        self.weights = np.clip(
            self.weights + (drive * reward / active) * kc, -WEIGHT_LIMIT, WEIGHT_LIMIT
        ).astype("float32")
        self.meta["feedback_count"] = str(self.feedback_count + 1)
        self._calibration = None

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
    drive: float = DEFAULT_DRIVE,
    force: bool = False,
) -> Brain:
    """Load a valid brain or create one (spec §9: mismatch -> rebuild)."""
    library_hash = library_features_hash(index.features)
    if path.exists() and not force:
        try:
            brain = Brain.load(path, expected_library_hash=library_hash)
            brain.calibrate(index.features)
            return brain
        except BrainMismatch:
            pass
    brain = Brain.create(index.features, seed=seed, drive=drive)
    brain.calibrate(index.features)
    brain.save(path)
    return brain
