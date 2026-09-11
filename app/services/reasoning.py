from __future__ import annotations

from pathlib import Path

from app.services.clarification import usable_value


class Reasoner:
    def __init__(self, knowledge_dir: Path):
        import yaml
        self.actions = {a["action_id"]: a for a in yaml.safe_load((knowledge_dir / "actions.yaml").read_text())["actions"]}
        self.rules = yaml.safe_load((knowledge_dir / "rules.yaml").read_text())["rules"]
        self.edges = yaml.safe_load((knowledge_dir / "interactions.yaml").read_text())["interactions"]

    def evaluate(self, state: dict, evidence_ids: set[str]) -> tuple[list[dict], list[dict]]:
        current = {field: event["value"] for field, event in state["current"].items() if event}
        land = current.get("land.use_type")
        ranked, rejected = [], []
        for action in self.actions.values():
            if not action.get("enabled"):
                rejected.append({"action_id": action["action_id"], "title": action["title"], "reason": "Deferred action: not enabled in this release."})
                continue
            if land not in action["compatible_ecosystems"]:
                rejected.append({"action_id": action["action_id"], "title": action["title"], "reason": "Incompatible or unknown land-use context."})
                continue
            activation_evidence = set(action.get("activation_evidence_ids", action["evidence_ids"]))
            missing_evidence = activation_evidence - evidence_ids
            if missing_evidence:
                rejected.append({"action_id": action["action_id"], "title": action["title"], "reason": "Required reviewed evidence was not retrieved."})
                continue
            missing = [field for field in action["required_known_fields"] if not usable_value(current, field)]
            if missing:
                labels = {"land.use_type": "land type", "land.crop_system": "current crop system", "biodiversity.habitat_types": "current habitat types"}
                readable_missing = ", ".join(labels.get(field, field.replace("_", " ").replace(".", " ")) for field in missing)
                rejected.append({"action_id": action["action_id"], "title": action["title"], "reason": f"Missing prerequisite: {readable_missing}."})
                continue
            if action["action_id"] == "conditional_cover_cropping" and not usable_value(current, "climate.rainfall_pattern"):
                rejected.append({"action_id": action["action_id"], "title": action["title"], "reason": "Missing prerequisite: climate.rainfall_pattern for the water feasibility gate."})
                continue
            dry_water_context = current.get("climate.rainfall_pattern") in {"low", "erratic", "seasonally_dry"} or (
                current.get("climate.annual_rainfall_mm") is not None
                and bool(current.get("climate.rainfall_seasonality_detail"))
            )
            conditional = (
                action["action_id"] == "conditional_cover_cropping" and dry_water_context
            ) or (
                action["action_id"] == "crop_diversification"
            ) or (
                action["action_id"] == "locally_appropriate_habitat_strips"
            ) or (
                action["action_id"] == "protect_existing_native_habitat" and not current.get("biodiversity.habitat_types")
            )
            if action["action_id"] == "pesticide_pressure_review" and not current.get("pressures.pesticide_use"):
                rejected.append({"action_id": action["action_id"], "title": action["title"], "reason": "No pesticide use or exposure concern has been reported."})
                continue
            if action["action_id"] == "protect_existing_native_habitat" and land not in {"forest", "grassland", "wetland"}:
                rejected.append({"action_id": action["action_id"], "title": action["title"], "reason": "No natural habitat context requiring protection is active."})
                continue
            score = 2 if not conditional else 1
            if action["action_id"] == "pesticide_pressure_review": score += 2
            if action["action_id"] == "protect_existing_native_habitat": score += 2
            ranked.append({"action": action, "conditional": conditional, "score": score, "retrieved_evidence_ids": [eid for eid in action["evidence_ids"] if eid in evidence_ids]})
        return sorted(ranked, key=lambda item: (-item["score"], item["action"]["action_id"])), rejected

    def paths_for(self, action_id: str, state: dict) -> list[dict]:
        current = state["current"]
        wanted = {"crop_diversification": ["diversification_biodiversity_context"], "conditional_cover_cropping": ["growing_cover_crop_uses_water", "residue_can_conserve_water", "rainfall_distribution_changes_cover_decision"], "pesticide_pressure_review": ["pesticide_exposure_soil_invertebrate_hazard"], "locally_appropriate_habitat_strips": ["habitat_reconnection_response"], "protect_existing_native_habitat": ["land_change_biodiversity_driver", "habitat_reconnection_response"]}.get(action_id, [])
        output = []
        def context_observations(edge_id: str) -> list[str]:
            # Edges describe mechanisms, while the observation links record
            # the actual conditions used to decide whether that mechanism is
            # applicable.  Never emit an ungrounded empty path.
            fields = {
                "diversification_biodiversity_context": ("land.", "soil.", "climate."),
                "growing_cover_crop_uses_water": ("land.", "climate."),
                "residue_can_conserve_water": ("land.", "soil."),
                "rainfall_distribution_changes_cover_decision": ("climate.", "land."),
                "pesticide_exposure_soil_invertebrate_hazard": ("pressures.", "land."),
                "land_change_biodiversity_driver": ("land.", "biodiversity."),
                "habitat_reconnection_response": ("land.", "biodiversity."),
            }[edge_id]
            return [event["observation_id"] for field, event in current.items() if event and field.startswith(fields)]

        def conditions_are_observed(edge_id: str) -> bool:
            """Do not expose an evidence edge merely because its label exists.

            These are explicit runtime counterparts for the declarative edge
            conditions; unknown conditions remain a clarification need.
            """
            values = {field: event["value"] for field, event in current.items() if event}
            return {
                "diversification_biodiversity_context": values.get("land.use_type") == "crop" and bool(values.get("land.crop_system")),
                "growing_cover_crop_uses_water": values.get("land.use_type") == "crop" and bool(values.get("climate.rainfall_pattern")),
                "residue_can_conserve_water": values.get("land.use_type") == "crop" and bool(values.get("climate.rainfall_pattern")),
                "rainfall_distribution_changes_cover_decision": values.get("climate.rainfall_pattern") in {"low", "erratic", "seasonally_dry"},
                "pesticide_exposure_soil_invertebrate_hazard": bool(values.get("pressures.pesticide_use")),
                "land_change_biodiversity_driver": values.get("land.use_type") in {"forest", "grassland", "wetland"},
                "habitat_reconnection_response": bool(values.get("biodiversity.habitat_types")) and bool(values.get("land.use_type")),
            }[edge_id]
        for edge in self.edges:
            if edge["edge_id"] not in wanted or edge["review_status"] != "reviewed": continue
            if not conditions_are_observed(edge["edge_id"]):
                continue
            obs_ids = context_observations(edge["edge_id"])
            if not obs_ids:
                continue
            output.append({"path_id": f"path_{edge['edge_id']}", "observation_ids": obs_ids, "edge_ids": [edge["edge_id"]], "decision_rule_id": "cover_crop_water_check" if "cover" in edge["edge_id"] else None, "summary": f"{edge['from']} → {edge['to']} ({edge['relation_type']})", "evidence_ids": edge["evidence_ids"]})
        return output
