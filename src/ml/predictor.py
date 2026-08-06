"""
Machine Learning model trainer, predictor, and model persistence for UFC fight outcomes.

Features:
- Multi-model Soft-Voting Ensemble (XGBoost + LightGBM + HistGradientBoosting + RandomForest)
- Temporal out-of-time train/test validation split
- Dual-pass invariant symmetrization (P(F1) + P(F2) = 1.0, P(F1, F1) = 0.50)
- Model serialization (save_model / load_model) with pickle & JSON metadata
- Fallback classifier with explicit warning logging if ML libraries are not installed
"""

import json
import math
import pickle
from pathlib import Path
from typing import List, Dict, Tuple, Any, Optional

from ..storage.ml_dataset import MLDatasetGenerator, FEATURE_COLUMNS
from ..utils.logger import get_logger

logger = get_logger(__name__)


class EnsemblePredictor:
    """
    Soft-voting ML Ensemble combining XGBoost, LightGBM, HistGradientBoosting, and Random Forest.
    """

    def __init__(self, random_state: int = 42):
        self.random_state = random_state
        self.models = []
        self.weights = []
        self._init_models()

    def _init_models(self):
        self.models = []
        self.weights = []

        # 1. XGBoost
        try:
            from xgboost import XGBClassifier
            xgb = XGBClassifier(
                n_estimators=120,
                max_depth=4,
                learning_rate=0.05,
                subsample=0.8,
                colsample_bytree=0.8,
                random_state=self.random_state,
                eval_metric="logloss",
                n_jobs=1,
            )
            self.models.append(("xgboost", xgb))
            self.weights.append(0.35)
            logger.info("Ensemble member loaded: XGBoost")
        except Exception as e:
            logger.debug(f"XGBoost unavailable: {e}")

        # 2. LightGBM
        try:
            from lightgbm import LGBMClassifier
            lgb = LGBMClassifier(
                n_estimators=120,
                max_depth=4,
                learning_rate=0.05,
                subsample=0.8,
                colsample_bytree=0.8,
                random_state=self.random_state,
                verbose=-1,
                n_jobs=1,
            )
            self.models.append(("lightgbm", lgb))
            self.weights.append(0.35)
            logger.info("Ensemble member loaded: LightGBM")
        except Exception as e:
            logger.debug(f"LightGBM unavailable: {e}")

        # 3. HistGradientBoosting (scikit-learn)
        try:
            from sklearn.ensemble import HistGradientBoostingClassifier
            hgb = HistGradientBoostingClassifier(
                max_iter=120,
                max_depth=4,
                learning_rate=0.05,
                random_state=self.random_state,
            )
            self.models.append(("hist_gb", hgb))
            self.weights.append(0.20)
            logger.info("Ensemble member loaded: HistGradientBoosting")
        except Exception as e:
            logger.debug(f"HistGradientBoosting unavailable: {e}")

        # 4. Random Forest (scikit-learn)
        try:
            from sklearn.ensemble import RandomForestClassifier
            rf = RandomForestClassifier(
                n_estimators=100,
                max_depth=6,
                random_state=self.random_state,
                n_jobs=1,
            )
            self.models.append(("random_forest", rf))
            self.weights.append(0.10)
            logger.info("Ensemble member loaded: RandomForest")
        except Exception as e:
            logger.debug(f"RandomForest unavailable: {e}")

        # Fallback if no ML libraries available
        if not self.models:
            logger.warning("[WARNING] No ML frameworks installed! Falling back to _SimpleLogisticRegression.")
            self.models.append(("simple_lr", _SimpleLogisticRegression(lr=0.01, epochs=300)))
            self.weights.append(1.0)

        # Normalize weights
        total_w = sum(self.weights) or 1.0
        self.weights = [w / total_w for w in self.weights]

    def fit(self, X: List[List[float]], y: List[int]):
        try:
            import numpy as np
            X_data = np.array(X, dtype=np.float32)
            y_data = np.array(y, dtype=np.int32)
        except ImportError:
            X_data = X
            y_data = y

        for name, model in self.models:
            try:
                model.fit(X_data, y_data)
            except Exception as e:
                logger.warning(f"Failed to fit ensemble model {name}: {e}")

    def predict_proba(self, X: List[List[float]]) -> List[float]:
        if not X:
            return []

        try:
            import numpy as np
            X_data = np.array(X, dtype=np.float32)
            has_numpy = True
        except ImportError:
            X_data = X
            has_numpy = False

        if has_numpy:
            import numpy as np
            ensemble_probs = np.zeros(len(X), dtype=np.float64)
            active_weight = 0.0

            for (name, model), w in zip(self.models, self.weights):
                try:
                    if hasattr(model, "predict_proba"):
                        probs = model.predict_proba(X_data)
                        if hasattr(probs, "ndim") and probs.ndim > 1 and probs.shape[1] > 1:
                            p1 = probs[:, 1]
                        else:
                            p1 = probs
                        ensemble_probs += w * p1
                        active_weight += w
                except Exception as e:
                    logger.warning(f"Failed predict_proba for ensemble model {name}: {e}")

            if active_weight > 0:
                ensemble_probs /= active_weight
            else:
                ensemble_probs = np.full(len(X), 0.5)

            return ensemble_probs.tolist()
        else:
            if self.models and hasattr(self.models[0][1], "predict_proba"):
                return self.models[0][1].predict_proba(X)
            return [0.5] * len(X)


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
        self.is_trained: bool = False

    def prepare_dataset(self, test_size: float = 0.2) -> Tuple[List[List[float]], List[int], List[List[float]], List[int]]:
        """
        Loads dataset, applies temporal train/test split, and applies symmetry
        data augmentation to BOTH train and test sets to guarantee a balanced 50/50 target distribution.
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

        # Apply symmetry augmentation to BOTH train and test to avoid single-class evaluation bias
        X_train, y_train = self._extract_features(train_rows, augment_symmetry=True)
        X_test, y_test = self._extract_features(test_rows, augment_symmetry=True)

        return X_train, y_train, X_test, y_test

    def _extract_features(self, rows: List[Dict[str, Any]], augment_symmetry: bool = True) -> Tuple[List[List[float]], List[int]]:
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
        Trains Ensemble model using temporal train/test split and computes evaluation metrics.
        """
        X_train, y_train, X_test, y_test = self.prepare_dataset(test_size=test_size)

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

        # Train Ensemble Predictor
        self.model = EnsemblePredictor(random_state=42)
        self.model.fit(X_train_scaled, y_train)

        self.is_trained = True

        # Extract feature importances by Pearson correlation with target
        imp = [abs(self._pearson_corr([row[i] for row in X_train_scaled], y_train)) for i in range(n_features)]
        total_imp = sum(imp) or 1.0
        self.feature_importances = {
            col: round(imp[i] / total_imp, 4) for i, col in enumerate(self.feature_columns)
        }

        # Evaluate on test set
        test_preds = self._predict_proba_matrix(X_test_scaled)
        metrics = self._calculate_metrics(y_test, test_preds)
        metrics["train_samples"] = len(X_train)
        metrics["test_samples"] = len(X_test)

        # Sort top 8 feature importances
        sorted_imp = sorted(self.feature_importances.items(), key=lambda x: x[1], reverse=True)[:8]
        metrics["top_features"] = dict(sorted_imp)

        logger.info(
            f"Ensemble Model trained cleanly. Test Accuracy: {metrics['accuracy']}%, ROC-AUC: {metrics['roc_auc']}"
        )
        return metrics

    def _scale_matrix(self, X: List[List[float]]) -> List[List[float]]:
        scaled = []
        for row in X:
            scaled.append(self._scale_vector(row))
        return scaled

    def _scale_vector(self, vec: List[float]) -> List[float]:
        scaled_row = []
        for i, col in enumerate(self.feature_columns):
            val = vec[i] if i < len(vec) else 0.0
            mean = self.scaler_means.get(col, 0.0)
            std = self.scaler_stds.get(col, 1.0)
            scaled_row.append((val - mean) / std if std > 1e-6 else 0.0)
        return scaled_row

    def _predict_proba_matrix(self, X_scaled: List[List[float]]) -> List[float]:
        if not self.model or not X_scaled:
            return [0.5] * len(X_scaled)

        if hasattr(self.model, "predict_proba"):
            probs = self.model.predict_proba(X_scaled)
            result = []
            for p in probs:
                try:
                    result.append(float(p[1]))
                except (TypeError, IndexError, KeyError):
                    result.append(float(p))
            return result
        return [0.5] * len(X_scaled)

    def predict_matchup(self, f1_features: Dict[str, Any], f2_features: Dict[str, Any]) -> Dict[str, Any]:
        """
        Predicts win probabilities and matchup outcome using invariant dual-pass prediction.

        Guarantees:
        1. P(F1) + P(F2) = 1.0
        2. Swapping fighters (F1 <-> F2) inverts probabilities identically
        3. F1 vs F1 yields exactly 50% / 50% win probabilities
        """
        if not self.is_trained:
            self.load_model()

        if not self.is_trained or self.model is None:
            return {
                "error": "Model is not trained. Please run python cli.py train first.",
                "fighter1_win_probability": 0.5,
                "fighter2_win_probability": 0.5,
                "predicted_winner": 1,
                "confidence_pct": 50.0,
                "is_trained": False,
            }

        # Build forward vector (F1 vs F2)
        v_forward = [self._extract_feature_diff(f1_features, f2_features, col) for col in self.feature_columns]
        v_forward_scaled = [self._scale_vector(v_forward)]

        # Build backward vector (F2 vs F1)
        v_backward = [self._extract_feature_diff(f2_features, f1_features, col) for col in self.feature_columns]
        v_backward_scaled = [self._scale_vector(v_backward)]

        p1_forward = self._predict_proba_matrix(v_forward_scaled)[0]
        p2_backward = self._predict_proba_matrix(v_backward_scaled)[0]

        # Invariant Dual-Pass Symmetrization:
        # P(F1 wins) = (P(F1 vs F2) + (1.0 - P(F2 vs F1))) / 2.0
        prob_f1 = (p1_forward + (1.0 - p2_backward)) / 2.0
        prob_f1 = max(0.01, min(0.99, prob_f1))
        prob_f2 = round(1.0 - prob_f1, 4)
        prob_f1 = round(prob_f1, 4)

        winner = 1 if prob_f1 >= 0.5 else 2
        confidence = round(max(prob_f1, prob_f2) * 100.0, 1)

        return {
            "fighter1_win_probability": prob_f1,
            "fighter2_win_probability": prob_f2,
            "predicted_winner": winner,
            "confidence_pct": confidence,
            "is_trained": True,
        }

    def _extract_feature_diff(self, f1: Dict[str, Any], f2: Dict[str, Any], col: str) -> float:
        if col.startswith("diff_"):
            raw_key = col[5:]
            v1 = f1.get(raw_key) or f1.get(f"pre_f1_{raw_key}") or f1.get(f"f1_{raw_key}") or 0.0
            v2 = f2.get(raw_key) or f2.get(f"pre_f2_{raw_key}") or f2.get(f"f2_{raw_key}") or 0.0
            try:
                return float(v1) - float(v2)
            except (ValueError, TypeError):
                return 0.0
        elif col == "is_same_stance":
            st1 = (f1.get("stance") or "").strip().lower()
            st2 = (f2.get("stance") or "").strip().lower()
            return 1.0 if (st1 and st2 and st1 == st2) else 0.0
        elif col == "is_orthodox_vs_southpaw":
            st1 = (f1.get("stance") or "").strip().lower()
            st2 = (f2.get("stance") or "").strip().lower()
            return 1.0 if (set([st1, st2]) == {"orthodox", "southpaw"}) else 0.0
        elif col == "pre_f1_ufc_debut":
            return 1.0 if (f1.get("wins") or 0) + (f1.get("losses") or 0) == 0 else 0.0
        elif col == "pre_f2_ufc_debut":
            return 1.0 if (f2.get("wins") or 0) + (f2.get("losses") or 0) == 0 else 0.0
        else:
            v1 = f1.get(col) or f1.get(f"pre_f1_{col}") or 0.0
            try:
                return float(v1)
            except (ValueError, TypeError):
                return 0.0

    def _calculate_metrics(self, y_true: List[int], y_probs: List[float]) -> Dict[str, Any]:
        if not y_true or not y_probs:
            return {}

        y_pred = [1 if p >= 0.5 else 0 for p in y_probs]
        correct = sum(1 for yt, yp in zip(y_true, y_pred) if yt == yp)
        accuracy = round(correct / len(y_true) * 100, 1)

        # Log loss
        eps = 1e-15
        loss = -sum(
            yt * math.log(max(p, eps)) + (1 - yt) * math.log(max(1 - p, eps))
            for yt, p in zip(y_true, y_probs)
        ) / len(y_true)

        # ROC AUC
        pos_probs = [p for yt, p in zip(y_true, y_probs) if yt == 1]
        neg_probs = [p for yt, p in zip(y_true, y_probs) if yt == 0]
        if pos_probs and neg_probs:
            pairs = sum(1.0 if pos > neg else (0.5 if pos == neg else 0.0) for pos in pos_probs for neg in neg_probs)
            auc = round(pairs / (len(pos_probs) * len(neg_probs)), 3)
        else:
            auc = 0.500

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

    def save_model(self, filepath: str = "data/fight_predictor_model.json") -> None:
        """Saves trained model binary and JSON metadata to disk."""
        out_path = Path(filepath)
        out_path.parent.mkdir(parents=True, exist_ok=True)

        meta = {
            "feature_columns": self.feature_columns,
            "scaler_means": self.scaler_means,
            "scaler_stds": self.scaler_stds,
            "feature_importances": self.feature_importances,
            "is_trained": self.is_trained,
        }
        out_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")

        if self.model is not None:
            pkl_path = out_path.with_suffix(".pkl")
            with open(pkl_path, "wb") as f:
                pickle.dump(self.model, f)
            logger.info(f"Saved trained ML model binary to {pkl_path}")
        logger.info(f"Saved model metadata to {out_path}")

    def load_model(self, filepath: str = "data/fight_predictor_model.json") -> bool:
        """Loads trained model binary and JSON metadata from disk."""
        out_path = Path(filepath)
        if not out_path.exists():
            return False

        try:
            meta = json.loads(out_path.read_text(encoding="utf-8"))
            self.feature_columns = meta.get("feature_columns", list(FEATURE_COLUMNS))
            self.scaler_means = meta.get("scaler_means", {})
            self.scaler_stds = meta.get("scaler_stds", {})
            self.feature_importances = meta.get("feature_importances", {})
            self.is_trained = meta.get("is_trained", False)

            pkl_path = out_path.with_suffix(".pkl")
            if pkl_path.exists():
                with open(pkl_path, "rb") as f:
                    self.model = pickle.load(f)
                self.is_trained = True
                logger.info(f"Loaded trained ML model binary from {pkl_path}")
                return True
            return False
        except Exception as e:
            logger.error(f"Failed to load model from {filepath}: {e}")
            return False


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
