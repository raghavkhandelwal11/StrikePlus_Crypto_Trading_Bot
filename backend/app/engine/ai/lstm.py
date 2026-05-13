"""LSTM price-direction predictor.

Uses PyTorch if available; gracefully no-ops if not. The model is small (1 LSTM
layer, ~50k params) so it can run on CPU. To train, populate
backend/data/models/lstm.pt by running scripts/train_ai.py with --model lstm.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional, Tuple

import numpy as np
import pandas as pd
from loguru import logger

try:
    import torch
    import torch.nn as nn
    _HAS_TORCH = True
except Exception:
    _HAS_TORCH = False
    torch = None  # type: ignore
    nn = None     # type: ignore

from app.engine.ai.features import build_features


SEQ_LEN = 32

if _HAS_TORCH:
    class _LSTMNet(nn.Module):
        def __init__(self, n_features: int, hidden: int = 32):
            super().__init__()
            self.lstm = nn.LSTM(n_features, hidden, batch_first=True)
            self.head = nn.Linear(hidden, 3)   # 3 classes: down, flat, up

        def forward(self, x):
            out, _ = self.lstm(x)
            return self.head(out[:, -1, :])


class LSTMPredictor:
    def __init__(self, model_path: str = "backend/data/models/lstm.pt"):
        self.model_path = model_path
        self.model: Optional["nn.Module"] = None
        self.feature_dim: Optional[int] = None

    def load(self) -> bool:
        if not _HAS_TORCH:
            logger.warning("torch not installed — LSTM disabled. `pip install torch` to enable.")
            return False
        path = Path(self.model_path)
        if not path.exists():
            return False
        try:
            checkpoint = torch.load(path, map_location="cpu")
            self.feature_dim = checkpoint["feature_dim"]
            self.model = _LSTMNet(n_features=self.feature_dim)
            self.model.load_state_dict(checkpoint["state_dict"])
            self.model.eval()
            logger.info(f"loaded LSTM model from {self.model_path}")
            return True
        except Exception as e:
            logger.warning(f"failed to load LSTM model: {e}")
            return False

    def predict_direction(self, df: pd.DataFrame) -> Optional[Tuple[float, int]]:
        """Return (confidence, class) where class ∈ {-1, 0, 1}, or None."""
        if not _HAS_TORCH or self.model is None:
            return None
        X = build_features(df)
        if len(X) < SEQ_LEN:
            return None
        seq = X.tail(SEQ_LEN).to_numpy(dtype=np.float32)
        x = torch.from_numpy(seq).unsqueeze(0)
        with torch.no_grad():
            logits = self.model(x)
            probs = torch.softmax(logits, dim=-1).squeeze(0).numpy()
        idx = int(np.argmax(probs))
        cls = idx - 1   # 0->-1, 1->0, 2->1
        return float(probs[idx]), cls
