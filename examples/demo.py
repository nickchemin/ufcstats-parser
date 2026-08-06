"""
Demo script: Train and evaluate the UFC Fight Outcome Prediction Model.

Usage:
    python examples/demo.py
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.ml.predictor import FightPredictor


def main():
    print("=" * 60)
    print("           UFCStats ML Predictor Demo ")
    print("=" * 60)

    db_path = "ufc_data.db"
    if not Path(db_path).exists():
        print(f"[!] Database file '{db_path}' not found. Please run: python cli.py crawl --limit-events 5")
        return

    # Initialize predictor
    predictor = FightPredictor(db_path)
    print("[+] Training model with temporal train/test split & symmetry augmentation...")

    metrics = predictor.train(test_size=0.2)

    if "error" in metrics:
        print(f"[!] Error: {metrics['error']}")
        return

    print("\n--- Model Evaluation Results ---")
    print(f"Training Matchups : {metrics['train_samples']}")
    print(f"Test Matchups     : {metrics['test_samples']}")
    print(f"Test Accuracy     : {metrics['accuracy']:.1f}%")
    print(f"ROC-AUC           : {metrics['roc_auc']:.3f}")
    print(f"Log Loss          : {metrics['log_loss']:.3f}")
    print(f"F1 Score          : {metrics['f1_score']:.3f}")

    print("\n--- Top Predictive Features ---")
    for feat, imp in metrics.get("top_features", {}).items():
        print(f"  - {feat:<32}: {imp:.4f}")

    print("\n[OK] ML Fight Predictor executed successfully!")


if __name__ == "__main__":
    main()
