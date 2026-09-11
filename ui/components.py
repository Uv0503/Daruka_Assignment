from __future__ import annotations

import json

import streamlit as st

METRIC_LABELS = {
    "biodiversity_composite": "Biodiversity measures",
    "ecosystem_services": "Ecosystem-service indicators",
    "water_use_efficiency": "Water-use efficiency",
    "soil_water_availability": "Soil-water availability",
    "infiltration_and_evaporation": "Infiltration and evaporation",
    "cash_crop_establishment": "Cash-crop establishment",
    "subsequent_crop_yield": "Subsequent crop performance",
    "plant_pollinator_transects": "Plant and pollinator observations",
    "habitat_extent": "Habitat extent",
    "soil_moisture": "Soil moisture",
    "pesticide_inventory": "Pesticide-use inventory",
}


def readable_label(value: str) -> str:
    return METRIC_LABELS.get(value, value.replace("_", " ").strip().capitalize())


def readable_path(summary: str) -> str:
    cleaned = []
    for part in summary.split("→"):
        label = part.strip()
        relation = ""
        if " (" in label:
            label, suffix = label.split(" (", 1)
            relation = " (" + suffix
        label = label.split(".", 1)[-1].replace("_", " ").strip().capitalize()
        cleaned.append(label + relation)
    return " → ".join(cleaned)


def render_recommendation(rec: dict) -> None:
    st.subheader(rec["title"])
    st.write(rec["action_steps"][0])
    st.caption(f"Confidence: {rec['confidence']['level']} — {' '.join(rec['confidence']['reasons'])}")
    st.caption(f"Applicability: {rec['applicability']}; horizon: {rec['time_horizon']['label']}.")
    st.markdown("**Conditions and preconditions**")
    for condition in rec["preconditions"]: st.write(f"• {condition}")
    st.markdown("**Trade-off**")
    for tradeoff in rec["tradeoffs"]: st.write(f"• {tradeoff['statement']}")
    st.markdown("**Monitoring**")
    for item in rec["monitoring"]:
        st.markdown(f"**{readable_label(item['metric'])}**")
        st.write(f"What and how: {item['method']}")
        st.write(f"Baseline: {item['baseline_requirement']}")
        st.write(f"When to repeat: {item['frequency']}")
        st.caption(item["interpretation_limitation"])
    if rec.get("impacted_metrics"):
        st.markdown("**Metrics**")
        for metric in rec["impacted_metrics"]:
            st.write(f"• {readable_label(metric['metric'])} — evidence direction: {metric['direction']}.")
    if rec.get("interaction_paths"):
        with st.expander("How site observations connect to the evidence"):
            for path in rec["interaction_paths"]:
                st.write(f"• {readable_path(path['summary'])}")


def markdown_export(response: dict) -> str:
    body = ["# Biodiversity Intelligence response", "", response.get("summary", "Response unavailable."), ""]
    for rec in response.get("recommendations", []):
        body.extend([f"## {rec['title']}", rec["action_steps"][0], ""])
    body.append("## Citations")
    for citation in response.get("citations", []):
        source_id = citation.get("source_id", "Source")
        title = citation.get("title", "Reviewed source")
        url = citation.get("url")
        body.append(f"- {source_id}: {title}" + (f" — {url}" if url else ""))
    return "\n".join(body)


def render_response(response: dict) -> None:
    st.write(response.get("summary", "The saved response could not be displayed completely."))
    for question in response.get("questions", []):
        st.info(f"{question['question']}\n\nWhy it matters: {question['why_it_matters']}")
    for rec in response.get("recommendations", []): render_recommendation(rec)
    if response.get("literature_illustrations"):
        illustration = response["literature_illustrations"][0]
        st.info(f"Literature illustration — pooled result, not a site forecast: lnRR {illustration['source_inputs']['lnRR']} becomes {illustration['output_relative_percent']}% (95% CI {illustration['output_ci_percent'][0]}%–{illustration['output_ci_percent'][1]}%). {illustration['transferability_note']}")
    if response.get("rejected_alternatives"):
        with st.expander("Rejected or deferred alternatives"):
            for item in response["rejected_alternatives"]: st.write(f"• {item['title']}: {item['reason']}")
    citations = response.get("citations", [])
    trace = response.get("trace_excerpts", [])
    if citations:
        evidence_label = "Retrieved evidence context" if not response.get("recommendations") else "Evidence"
        with st.expander(evidence_label):
            if not response.get("recommendations"):
                st.caption("Context retrieved from reviewed sources; it does not support an action unless every recommendation gate passes.")
            for citation in citations:
                evidence_claim = citation.get("evidence_claim")
                if evidence_claim:
                    st.markdown(f"**Reviewed evidence claim** — {evidence_claim}")
                else:
                    st.markdown("**Reviewed evidence**")
                    st.caption("This saved turn uses an older response format; submit the message again to refresh its evidence claim.")
                source_id = citation.get("source_id", "Source")
                title = citation.get("title", "Reviewed source")
                publisher = f" ({citation['publisher']})" if citation.get("publisher") else ""
                st.markdown(f"**Source** — {source_id}: {title}{publisher}")
                st.markdown(f"**Exact locator** — {citation.get('locator', 'Not available in this saved response')}")
                st.markdown("**Complete extracted passage**")
                st.write(citation.get("excerpt", "Passage unavailable in this saved response."))
                if citation.get("url"):
                    st.markdown(f"[Open source]({citation['url']})")
    elif response.get("status") == "clarify":
        st.caption("Evidence retrieval has not run yet. The assistant is waiting for a decision-changing site detail and does not attach scientific evidence to a generic clarification.")
    else:
        st.caption("No reviewed evidence was retrieved for this turn.")
    if trace:
        with st.expander("Retrieval trace"):
            st.caption("Reviewed anchor passages selected by bounded lexical and semantic retrieval. Internal IDs and ranking fields are intentionally hidden.")
            readable_items = [item for item in trace if item.get("claim") and item.get("source") and item.get("locator")]
            for item in readable_items:
                st.write(f"• {item['claim']} — {item['source']}, {item['locator']}")
            if not readable_items:
                st.caption("This saved turn uses a legacy internal trace. Submit the message again to view the readable retrieval trace.")
    elif response.get("status") == "clarify":
        st.caption("Retrieval trace: not run on this clarification turn.")
    else:
        st.caption("Retrieval trace: no matching reviewed anchor chunks.")
    turn_key = response.get("turn_id", "response")
    st.download_button("Download JSON", json.dumps(response, indent=2), "biodiversity-response.json", "application/json", key=f"json_{turn_key}")
    st.download_button("Download Markdown", markdown_export(response), "biodiversity-response.md", "text/markdown", key=f"markdown_{turn_key}")
