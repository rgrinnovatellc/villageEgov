#!/usr/bin/env python3
"""Export public-facing JSON artifacts from the canonical YAML model."""

from collections import Counter

from analyze_dependency_routes import (
    configure_scope_maps,
    build_budget_scenario_result,
    build_feasibility_rows,
    collect_household_routes,
)
from village_model_io import base_dir, export_json, governance_distance, iter_nodes, load_needs, load_scenarios, load_tree


def node_label(node):
    return node.get("name") or node.get("id", "unknown").replace("_", " ").title()


def collect_tree_stats(tree_root):
    counts = Counter()
    for node in iter_nodes(tree_root, include_inactive=False):
        node_type = node.get("type")
        if node_type:
            counts[node_type] += 1
    return counts


def collect_tree_nodes(tree_root):
    nodes = []
    for node in iter_nodes(tree_root, include_inactive=True):
        meta = node.get("meta", {})
        nodes.append(
            {
                "id": node.get("id"),
                "label": node_label(node),
                "type": node.get("type"),
                "parent_id": node.get("parent_id"),
                "child_ids": node.get("child_ids", []),
                "status": node.get("status", "active"),
                "satisfies": meta.get("satisfies", []),
                "provides": meta.get("provides", []),
                "requires": meta.get("requires", []),
            }
        )
    return nodes


def collect_dependency_graph(tree_root):
    nodes = collect_tree_nodes(tree_root)
    nodes_by_id = {node["id"]: node for node in nodes}
    edges = {}

    for node in iter_nodes(tree_root, include_inactive=False):
        source_id = node.get("id")
        source_type = node.get("type")
        for req in node.get("meta", {}).get("requires", []):
            target_id = req.get("node")
            need_id = req.get("need")
            if not source_id or not target_id or not need_id or target_id not in nodes_by_id:
                continue
            key = (source_id, target_id)
            if key not in edges:
                target_type = nodes_by_id[target_id].get("type")
                edges[key] = {
                    "source": source_id,
                    "source_type": source_type,
                    "target": target_id,
                    "target_type": target_type,
                    "needs": [],
                    "weight": 0,
                    "route_length": governance_distance(tree_root, source_id, target_id),
                }
            edges[key]["needs"].append(need_id)
            edges[key]["weight"] += 1

    graph_edges = []
    for edge in edges.values():
        edge["needs"] = sorted(set(edge["needs"]))
        graph_edges.append(edge)
    graph_edges.sort(key=lambda item: (item["route_length"], item["source"], item["target"]))

    return {
        "nodes": nodes,
        "edges": graph_edges,
        "need_options": sorted({need for edge in graph_edges for need in edge["needs"]}),
    }


def main():
    base = base_dir()
    public_dir = base.parent / "public"
    needs = load_needs()
    tree = load_tree()
    scenarios = load_scenarios()
    configure_scope_maps(needs)
    scope_levels = needs.get("taxonomy", {}).get("scope_levels", [])
    tree_node_counts = collect_tree_stats(tree)
    needs_by_id = {need["id"]: need for need in needs.get("needs", [])}
    routes = collect_household_routes(tree, needs_by_id)
    feasibility_rows = build_feasibility_rows(routes, needs_by_id)
    budget_results = [build_budget_scenario_result(feasibility_rows, scenario) for scenario in scenarios.get("budget_scenarios", [])]
    dependency_graph = collect_dependency_graph(tree)

    export_json(needs, base / "dist" / "village_needs_catalog.json")

    public_bundle = {
        "version": needs.get("version"),
        "taxonomy": needs.get("taxonomy"),
        "summary": {
            "need_count": len(needs.get("needs", [])),
            "tree_node_counts": tree_node_counts,
            "scope_level_counts": [
                {
                    "code": level.get("code"),
                    "name": level.get("name"),
                    "order": level.get("order"),
                    "count": tree_node_counts.get(level.get("code"), 0),
                }
                for level in scope_levels
            ],
            "scope": tree.get("scope"),
            "completeness": tree.get("completeness"),
        },
        "needs": needs.get("needs", []),
        "tree": tree,
        "analysis": {
            "top_interventions": feasibility_rows[:10],
            "budget_scenarios": budget_results,
        },
        "graph": dependency_graph,
    }
    export_json(public_bundle, base / "dist" / "village_governance_public_data.json")

    dashboard_bundle = {
        "summary": public_bundle["summary"],
        "top_interventions": feasibility_rows[:10],
        "budget_scenarios": budget_results,
        "graph": dependency_graph,
        "needs": [
            {
                "id": need["id"],
                "name": need.get("name"),
                "category": need.get("category"),
                "scope_options": need.get("scope_options", []),
                "confidence": need.get("confidence", "provisional"),
                "evidence": need.get("evidence", []),
                "barriers": need.get("barriers", []),
                "feasibility": need.get("feasibility"),
            }
            for need in needs.get("needs", [])
        ],
    }
    export_json(dashboard_bundle, base / "dist" / "village_governance_dashboard_data.json")
    export_json(dashboard_bundle, public_dir / "village_governance_dashboard_data.json")
    print("Wrote dist/village_needs_catalog.json")
    print("Wrote dist/village_governance_public_data.json")
    print("Wrote dist/village_governance_dashboard_data.json")
    print("Wrote ../public/village_governance_dashboard_data.json")


if __name__ == "__main__":
    main()