"""Random Forest trend classifier. Fully working with sklearn."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional, Tuple

import joblib
import numpy as np
import pandas as pd
from loguru import logger

try:
    from sklearn.ensemble import RandomForestClassifier
    _HAS_SKLEARN = True
except Exception:
    _HAS_SKLEARN = False

from app.engine.ai.features import build_features, make_labels


class RandomForestTrend:
    """Classifies the next-N-bar direction as up/flat/down."""

    def __init__(self, model_path: str = "backend/data/models/rf.pkl"):
        self.model_path = model_path
        self.model: Optional["RandomForestClassifier"] = None

    def load(self) -> bool:
        if not _HAS_SKLEARN:
            logger.warning("sklearn not installed — RF disabled")
            return False
        if Path(self.model_path).exists():
            try:
                self.model = joblib.load(self.model_path)
                logger.info(f"loaded RF model from {self.model_path}")
                return True
            except Exception as e:
                logger.warning(f"failed to load RF model: {e}")
        return False

    def train(self, df: pd.DataFrame, horizon: int = 5, threshold: float = 0.002) -> dict:
        if not _HAS_SKLEARN:
            raise RuntimeError("sklearn not installed")
        X = build_features(df)
        y = make_labels(df, horizon=horizon, threshold=threshold).loc[X.index]
        # Guard against label leakage at the tail
        valid = y.notna()
        X, y = X[valid], y[valid]

        self.model = RandomForestClassifier(
            n_estimators=200, max_depth=8, min_samples_leaf=20,
            class_weight="balanced", random_state=42, n_jobs=-1,
        )
        self.model.fit(X, y)
        os.makedirs(Path(self.model_path).parent, exist_ok=True)
        joblib.dump(self.model, self.model_path)
        score = float(self.model.score(X, y))
        logger.info(f"RF trained, in-sample accuracy={score:.3f} — REMEMBER to validate out-of-sample")
        return {"accuracy_in_sample": score, "samples": len(X)}

    def predict_proba(self, df: pd.DataFrame) -> Optional[Tuple[float, int]]:
        """Return (confidence_for_predicted_class, predicted_class).

        Class is one of {-1, 0, 1}. Returns None if the model is unavailable
        or features cannot be computed.
        """
        if self.model is None or not _HAS_SKLEARN:
            return None
        X = build_features(df)
        if X.empty:
            return None
        last = X.iloc[[-1]]
        proba = self.model.predict_proba(last)[0]
        idx = int(np.argmax(proba))
        cls = int(self.model.classes_[idx])
        return float(proba[idx]), cls
