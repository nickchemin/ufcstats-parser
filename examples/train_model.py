"""
Train UFC Fight Prediction Machine Learning model and evaluate predictive performance.

Usage:
    python examples/train_model.py
"""

import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from rich.console import Console
from rich.table import Table
from rich import box

from src.ml.predictor import FightPredictor

console = Console()


def main():
    console.print("\n[bold cyan]====================================================[/]")
    console.print("[bold cyan]       UFCStats Fight Outcome ML Predictor          [/]")
    console.print("[bold cyan]====================================================[/]\n")

    db_path = "ufc_data.db"
    if not Path(db_path).exists():
        console.print(f"[bold red][!] Database '{db_path}' not found.[/]")
        console.print("[yellow]    Please run: python cli.py crawl --all --limit-events 5[/]\n")
        return

    predictor = FightPredictor(db_path)
    console.print("[bold green][+] Training model with temporal train/test split & symmetry augmentation...[/]")

    metrics = predictor.train(test_size=0.2)

    if "error" in metrics:
        console.print(f"[bold red][!] {metrics['error']}[/]")
        return

    # Print Metrics Table
    table = Table(title="Model Evaluation Metrics (Out-of-Time Test Set)", box=box.ROUNDED)
    table.add_column("Metric", style="bold white")
    table.add_column("Value", style="bold green")

    table.add_row("Training Samples", str(metrics["train_samples"]))
    table.add_row("Test Samples", str(metrics["test_samples"]))
    table.add_row("Accuracy", f"{metrics['accuracy']:.1f}%")
    table.add_row("ROC-AUC", f"{metrics['roc_auc']:.3f}")
    table.add_row("Log Loss", f"{metrics['log_loss']:.3f}")
    table.add_row("Precision", f"{metrics['precision']:.3f}")
    table.add_row("Recall", f"{metrics['recall']:.3f}")
    table.add_row("F1 Score", f"{metrics['f1_score']:.3f}")

    console.print(table)

    # Print Top Feature Importance Table
    feat_table = Table(title="Top Predictive Feature Importances", box=box.ROUNDED)
    feat_table.add_column("Feature Name", style="bold white")
    feat_table.add_column("Importance Weight", style="cyan")

    for feat, imp in metrics.get("top_features", {}).items():
        feat_table.add_row(feat, f"{imp:.4f}")

    console.print(feat_table)

    # Save model
    output_model = "data/fight_predictor_model.json"
    predictor.save_model(output_model)
    console.print(f"\n[bold green][OK] Model saved cleanly -> {Path(output_model).resolve()}[/]\n")


if __name__ == "__main__":
    main()
