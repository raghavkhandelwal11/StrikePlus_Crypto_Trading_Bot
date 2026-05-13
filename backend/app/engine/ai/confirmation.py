"""AI confirmation layer. NEVER the sole decision maker — only confirms a strategy signal.

Decision rule:
  - If RF and LSTM both agree with the strategy direction with confidence
    above threshold, boost the signal confidence and approve.
  - If they disagree strongly, reject (return False).
  - If they're neutral or unavailable, approve (don't block trading).
"""
from __future__ import annotations

from typing import Optional, Tuple

import pandas as pd
from loguru import logger

from app.core.config import get_settings
from app.core.types import Side, Signal
from app.engine.ai.lstm import LSTMPredictor
from app.engine.ai.random_forest import RandomForestTrend


class AIConfirmation:
    def __init__(self) -> None:
        s = get_settings()
        self.enabled = s.ai_enabled
        self.threshold = s.ai_confidence_threshold
        self.rf = RandomForestTrend(model_path=s.rf_model_path)
        # LSTM uses PyTorch's native .pt file even if the env var ends in .pkl
        lstm_path = s.lstm_model_path
        if lstm_path.endswith(".pkl"):
            lstm_path = lstm_path[:-4] + ".pt"
        self.lstm = LSTMPredictor(model_path=lstm_path)
        self.rf_loaded = self.rf.load()
        self.lstm_loaded = self.lstm.load()
        if self.enabled and not (self.rf_loaded or self.lstm_loaded):
            logger.warning(
                "AI is enabled but no models are loaded. Train via scripts/train_ai.py. "
                "AI will pass through (not block) signals until trained."
            )

    def confirm(self, signal: Signal, df: pd.DataFrame) -> Tuple[bool, float, str]:
        """Return (approved, adjusted_confidence, reason).

        Adjusted confidence is the strategy confidence, possibly boosted by
        agreeing models.
        """
        if not self.enabled:
            return True, signal.confidence, "ai_disabled"

        intended = 1 if signal.side == Side.BUY else -1
        votes = []     # (confidence, predicted_class)
        if self.rf_loaded:
            r = self.rf.predict_proba(df)
            if r is not None:
                votes.append(("rf", *r))
        if self.lstm_loaded:
            r = self.lstm.predict_direction(df)
            if r is not None:
                votes.append(("lstm", *r))

        if not votes:
            # Pass-through when models unavailable.
            return True, signal.confidence, "ai_no_models"

        agree = sum(1 for _, _, c in votes if c == intended)
        disagree = sum(1 for _, conf, c in votes if c == -intended and conf >= self.threshold)
        avg_conf = sum(conf for _, conf, _ in votes) / len(votes)

        if disagree >= len(votes):
            return False, signal.confidence, f"ai_disagrees({disagree}/{len(votes)})"
        if agree >= 1 and avg_conf >= self.threshold:
            boosted = min(1.0, signal.confidence + 0.15)
            return True, boosted, f"ai_confirmed({agree}/{len(votes)} avg_conf={avg_conf:.2f})"
        return True, signal.confidence, "ai_neutral"
