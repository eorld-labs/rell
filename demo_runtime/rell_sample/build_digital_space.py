from __future__ import annotations

from pathlib import Path

from digital_space import build_subject_cognitive_model, read_json, write_json


ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"


def main() -> None:
    prior = read_json(DATA / "digital_kitchen_semantic_prior.json")
    model = build_subject_cognitive_model(prior, subject_type="simulated_robot")
    write_json(DATA / "digital_kitchen_cognitive_model.json", model)
    print("Digital kitchen cognitive model generated.")
    print(model["cognitive_model_id"])


if __name__ == "__main__":
    main()
