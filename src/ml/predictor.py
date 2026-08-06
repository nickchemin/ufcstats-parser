"""
Machine Learning fight outcome predictor.

Features:
- Time-series temporal train/test split (no future data leakage)
- Feature-inverted symmetry augmentation
- Feature importance evaluation
- Probability estimation for upcoming matchups
"""

import json
import math
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

from ..storage.ml_dataset import MLDatasetGenerator
from ..utils.logger import get_logger

logger = get_logger(__name__)

FEATURE_COLUMNS = [
    "diff_pre_elo",
    "diff_height_cm",
    "diff_weight_kg",
    "diff_reach_cm",
    "diff_ape_index",
    "diff_age_years",
    "is_same_stance",
    "is_orthodox_vs_southpaw",
    "diff_pre_wins",
    "diff_pre_losses",
    "diff_pre_win_rate",
    "diff_pre_ko_win_rate",
    "diff_pre_sub_win_rate",
    "diff_pre_dec_win_rate",
    "diff_pre_streak",
    "diff_pre_days_since_last_fight",
    "diff_pre_win_rate_last3",
    "diff_slpm",
    "diff_str_acc",
    "diff_sapm",
    "diff_str_def",
    "diff_td_avg",
    "diff_td_acc",
    "diff_td_def",
    "title_fight",
    "is_main_event",
    "pre_f1_ufc_debut",
    "pre_f2_ufc_debut",
]


class FightPredictor:
    """
    Machine Learning model trainer and predictor for UFC fight outcomes.
    """

    def __init__(self, db_path: str = "ufc_data.db"):
        self.db_path = Path(db_path)
        self.feature_columns = list(FEATURE_COLUMNS)
        self.model = None
        self.scaler_means: Dict[str, float] = {}
        self.scaler_stds: Dict[str, float] = {}
        self.feature_importances: Dict[str, float] = {}

    def prepare_dataset(self, test_size: float = 0.2, augment_symmetry: bool = True):
        """
        Loads dataset, filters valid outcomes, applies temporal train/test split,
        and optionally performs feature-inverted symmetry data augmentation.
        """
        generator = MLDatasetGenerator(str(self.db_path))
        raw_dataset = generator.build_dataset()

        # Filter rows with valid target_winner (0 or 1)
        valid_rows = [r for r in raw_dataset if r.get("target_winner") in (0, 1)]

        if not valid_rows:
            logger.warning("No valid fights with winner labels found in dataset.")
            return [], [], [], []

        # Ensure chronological order by event_date
        valid_rows.sort(key=lambda r: r.get("event_date") or "")

        split_idx = int(len(valid_rows) * (1.0 - test_size))
        train_rows = valid_rows[:split_idx]
        test_rows = valid_rows[split_idx:]

        X_train, y_train = self._extract_features(train_rows, augment_symmetry=augment_symmetry)
        X_test, y_test = self._extract_features(test_rows, augment_symmetry=False)

        return X_train, y_train, X_test, y_test

    def _extract_features(self, rows: List[Dict[str, Any]], augment_symmetry: bool = False) -> Tuple[List[List[float]], List[int]]:
        X = []
        y = []

        for row in rows:
            feat = self._extract_row_vector(row)
            target = int(row["target_winner"])
            X.append(feat)
            y.append(target)

            if augment_symmetry:
                # Invert differentials and swap fighter flags
                inverted_row = dict(row)
                inverted_row["target_winner"] = 1 - target
                for col in self.feature_columns:
                    val = row.get(col)
                    if col.startswith("diff_") and val is not None:
                        inverted_row[col] = -val
                    elif col == "pre_f1_ufc_debut":
                        inverted_row[col] = row.get("pre_f2_ufc_debut")
                    elif col == "pre_f2_ufc_debut":
                        inverted_row[col] = row.get("pre_f1_ufc_debut")

                X.append(self._extract_row_vector(inverted_row))
                y.append(1 - target)

        return X, y

    def _extract_row_vector(self, row: Dict[str, Any]) -> List[float]:
        vector = []
        for col in self.feature_columns:
            val = row.get(col)
            if val is None:
                val = 0.0
            else:
                try:
                    val = float(val)
                except (ValueError, TypeError):
                    val = 0.0
            vector.append(val)
        return vector

    def train(self, test_size: float = 0.2) -> Dict[str, Any]:
        """
        Trains model using temporal train/test split and computes evaluation metrics.
        """
        X_train, y_train, X_test, y_test = self.prepare_dataset(test_size=test_size, augment_symmetry=True)

        if not X_train:
            return {"error": "Insufficient dataset for training."}

        # Calculate standardization statistics (means and stds)
        n_features = len(self.feature_columns)
        for i, col in enumerate(self.feature_columns):
            vals = [X_train[j][i] for j in range(len(X_train))]
            mean = sum(vals) / len(vals)
            var = sum((x - mean) ** 2 for x in vals) / len(vals)
            std = math.sqrt(var) if var > 1e-6 else 1.0
            self.scaler_means[col] = mean
            self.scaler_stds[col] = std

        X_train_scaled = self._scale_matrix(X_train)
        X_test_scaled = self._scale_matrix(X_test)

        # Train model: try Gradient Boosting / Random Forest / Logistic Regression
        try:
            from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
            self.model = HistGradientBoostingClassifier(max_iter=100, random_state=42)
            self.model.fit(X_train_scaled, y_train)

            # Extract feature importances if available, else compute correlation
            if hasattr(self.model, "feature_importances_"):
                imp = self.model.feature_importances_
            else:
                imp = [abs(self._pearson_corr([row[i] for row in X_train_scaled], y_train)) for i in range(n_features)]

        except ImportError:
            # Fallback to simple Logistic Regression implementation
            self.model = _SimpleLogisticRegression(lr=0.01, epochs=300)
            self.model.fit(X_train_scaled, y_train)
            imp = [abs(w) for w in self.model.weights]

        total_imp = sum(imp) or 1.0
        self.feature_importances = {
            col: round(imp[i] / total_imp, 4) for i, col in enumerate(self.feature_columns)
        }

        # Evaluate on test set
        test_preds = self._predict_proba_matrix(X_test_scaled)
        metrics = self._compute_metrics(y_test, test_preds)
        metrics["train_samples"] = len(X_train)
        metrics["test_samples"] = len(X_test)
        metrics["top_features"] = dict(
            sorted(self.feature_importances.items(), key=lambda x: x[1], reverse=True)[:8]
        )

        logger.info(f"Model trained cleanly. Test Accuracy: {metrics['accuracy']:.1f}%, ROC-AUC: {metrics['roc_auc']:.3f}")
        return metrics

    def _scale_matrix(self, X: List[List[float]]) -> List[List[float]]:
        X_scaled = []
        for row in X:
            scaled_row = []
            for i, col in enumerate(self.feature_columns):
                mean = self.scaler_means.get(col, 0.0)
                std = self.scaler_stds.get(col, 1.0)
                scaled_row.append((row[i] - mean) / std)
            X_scaled.append(scaled_row)
        return X_scaled

    def _predict_proba_matrix(self, X_scaled: List[List[float]]) -> List[float]:
        if not self.model or not X_scaled:
            return [0.5] * len(X_scaled)

        if hasattr(self.model, "predict_proba"):
            probs = self.model.predict_proba(X_scaled)
            result = []
            for p in probs:
                try:
                    # Check if p is subscriptable (e.g., sklearn 2D array [prob_0, prob_1])
                    result.append(float(p[1]))
                except (TypeError, IndexError, KeyError):
                    result.append(float(p))
            return result
        return [0.5] * len(X_scaled)

    def predict_matchup(self, f1_features: Dict[str, Any], f2_features: Dict[str, Any]) -> Dict[str, Any]:
        """
        Predicts win probabilities for a matchup given fighter feature dicts.
        """
        if self.model is None:
            self.train()

        matchup_row = {}
        for col in self.feature_columns:
            matchup_row[col] = f1_features.get(col, f2_features.get(col, 0.0))

        feat_vec = [self._extract_row_vector(matchup_row)]
        scaled_vec = self._scale_matrix(feat_vec)
        prob_f1 = self._predict_proba_matrix(scaled_vec)[0]
        prob_f2 = round(1.0 - prob_f1, 3)
        prob_f1 = round(prob_f1, 3)

        predicted_winner = 1 if prob_f1 >= 0.5 else 2

        return {
            "fighter1_win_probability": prob_f1,
            "fighter2_win_probability": prob_f2,
            "predicted_winner": predicted_winner,
            "confidence_pct": round(max(prob_f1, prob_f2) * 100, 1),
        }

    def _compute_metrics(self, y_true: List[int], y_probs: List[float]) -> Dict[str, Any]:
        if not y_true:
            return {"accuracy": 0.0, "roc_auc": 0.5, "log_loss": 0.693, "f1_score": 0.0}

        y_pred = [1 if p >= 0.5 else 0 for p in y_probs]
        correct = sum(1 for yt, yp in zip(y_true, y_pred) if yt == yp)
        accuracy = round(correct / len(y_true) * 100, 1)

        # Log loss
        eps = 1e-15
        loss = -sum(
            yt * math.log(max(p, eps)) + (1 - yt) * math.log(max(1 - p, eps))
            for yt, p in zip(y_true, y_probs)
        ) / len(y_true)

        # ROC AUC approx
        pos_probs = [p for yt, p in zip(y_true, y_probs) if yt == 1]
        neg_probs = [p for yt, p in zip(y_true, y_probs) if yt == 0]
        if pos_probs and neg_probs:
            pairs = sum(1.0 if pos > neg else (0.5 if pos == neg else 0.0) for pos in pos_probs for neg in neg_probs)
            auc = round(pairs / (len(pos_probs) * len(neg_probs)), 3)
        else:
            auc = 0.5

        # Precision, Recall, F1
        tp = sum(1 for yt, yp in zip(y_true, y_pred) if yt == 1 and yp == 1)
        fp = sum(1 for yt, yp in zip(y_true, y_pred) if yt == 0 and yp == 1)
        fn = sum(1 for yt, yp in zip(y_true, y_pred) if yt == 1 and yp == 0)

        precision = round(tp / (tp + fp), 3) if (tp + fp) > 0 else 0.0
        recall = round(tp / (tp + fn), 3) if (tp + fn) > 0 else 0.0
        f1 = round(2 * precision * recall / (precision + recall), 3) if (precision + recall) > 0 else 0.0

        return {
            "accuracy": accuracy,
            "roc_auc": auc,
            "log_loss": round(loss, 3),
            "precision": precision,
            "recall": recall,
            "f1_score": f1,
        }

    def _pearson_corr(self, x: List[float], y: List[int]) -> float:
        n = len(x)
        if n == 0:
            return 0.0
        mx, my = sum(x) / n, sum(y) / n
        num = sum((xi - mx) * (yi - my) for xi, yi in zip(x, y))
        den = math.sqrt(sum((xi - mx) ** 2 for xi in x) * sum((yi - my) ** 2 for yi in y))
        return (num / den) if den > 1e-6 else 0.0

    def save_model(self, filepath: str = "data/fight_predictor.json") -> None:
        """Saves model weights and parameters to JSON file."""
        out_path = Path(filepath)
        out_path.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "feature_columns": self.feature_columns,
            "scaler_means": self.scaler_means,
            "scaler_stds": self.scaler_stds,
            "feature_importances": self.feature_importances,
        }
        out_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        logger.info(f"Saved model params to {out_path}")


class _SimpleLogisticRegression:
    """Lightweight pure-python Fallback Logistic Regression Model."""

    def __init__(self, lr: float = 0.01, epochs: int = 200):
        self.lr = lr
        self.epochs = epochs
        self.weights: List[float] = []
        self.bias: float = 0.0

    def fit(self, X: List[List[float]], y: List[int]):
        n_samples = len(X)
        if n_samples == 0:
            return
        n_features = len(X[0])
        self.weights = [0.0] * n_features
        self.bias = 0.0

        for _ in range(self.epochs):
            dw = [0.0] * n_features
            db = 0.0
            for i in range(n_samples):
                z = sum(X[i][j] * self.weights[j] for j in range(n_features)) + self.bias
                sig = 1.0 / (1.0 + math.exp(-max(-20.0, min(20.0, z))))
                err = sig - y[i]
                for j in range(n_features):
                    dw[j] += err * X[i][j]
                db += err

            for j in range(n_features):
                self.weights[j] -= self.lr * (dw[j] / n_samples)
            self.bias -= self.lr * (db / n_samples)

    def predict_proba(self, X: List[List[float]]) -> List[float]:
        probs = []
        n_features = len(self.weights)
        for row in X:
            z = sum(row[j] * self.weights[j] for j in range(min(len(row), n_features))) + self.bias
            sig = 1.0 / (1.0 + math.exp(-max(-20.0, min(20.0, z))))
            probs.append(sig)
        return probs
