#!/usr/bin/env python3
"""Shared model I/O and traversal helpers for the village governance system."""

import json
from collections import deque
from pathlib import Path
import re

import yaml


CHILD_COLLECTION_KEYS = ("wards", "neighbor_groups", "households")
ACTIVE_STATUSES = {"active", "planned"}


def base_dir() -> Path:
    return Path(__file__).parent


def load_yaml(path: Path):
    with open(path) as f:
        return yaml.safe_load(f)


def load_json(path: Path):
    with open(path) as f:
        return json.load(f)


def load_needs():
    """Load the canonical village needs catalog from YAML."""
    return load_yaml(base_dir() / "village_needs_catalog.yaml")


def load_tree():
    """Load the canonical governance model and normalize it to a node registry."""
    raw_model = load_yaml(base_dir() / "village_governance_tree.yaml")
    return normalize_governance_model(raw_model)


def load_scenarios():
    path = base_dir() / "budget_scenarios.yaml"
    if path.exists():
        return load_yaml(path)
    return {"budget_scenarios": []}


def export_json(data, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")


def default_node_name(node_id, node_type=None):
    if node_id == "village":
        return "Village"
    ward_match = re.fullmatch(r"ward_(\d+)", node_id)
    if ward_match:
        return f"Ward {ward_match.group(1)}"
    neighbor_match = re.fullmatch(r"n(\d+)_(\d+)", node_id)
    if neighbor_match:
        return f"Neighbor Group {neighbor_match.group(1)}.{neighbor_match.group(2)}"
    household_match = re.fullmatch(r"h(\d+)_(\d+)_(\d+)", node_id)
    if household_match:
        return (
            f"Household {household_match.group(1)}."
            f"{household_match.group(2)}.{household_match.group(3)}"
        )
    if node_type:
        return f"{node_type} {node_id}"
    return node_id.replace("_", " ").title()


def normalize_meta(meta):
    meta = dict(meta or {})
    meta.setdefault("satisfies", [])
    meta.setdefault("requires", [])
    meta.setdefault("provides", [])
    meta.setdefault("need_deps", [])
    return meta


def normalize_node(node):
    normalized = dict(node)
    normalized.setdefault("name", default_node_name(normalized.get("id", "unknown"), normalized.get("type")))
    normalized.setdefault("parent_id", None)
    normalized.setdefault("child_ids", [])
    normalized.setdefault("status", "active")
    normalized["meta"] = normalize_meta(normalized.get("meta"))
    if "lineage" in normalized and normalized["lineage"] is None:
        normalized.pop("lineage")
    return normalized


def nested_tree_to_node_registry(raw_model):
    nodes = []

    def visit(node, parent_id=None):
        child_ids = []
        for key in CHILD_COLLECTION_KEYS:
            for child in node.get(key, []):
                child_ids.append(child["id"])
        nodes.append(
            normalize_node(
                {
                    "id": node["id"],
                    "name": node.get("name") or default_node_name(node["id"], node.get("type")),
                    "type": node.get("type"),
                    "parent_id": parent_id,
                    "child_ids": child_ids,
                    "status": node.get("status", "active"),
                    "lineage": node.get("lineage"),
                    "meta": node.get("meta", {}),
                }
            )
        )
        for key in CHILD_COLLECTION_KEYS:
            for child in node.get(key, []):
                visit(child, node["id"])

    root = raw_model["village"]
    visit(root)
    return {
        "version": raw_model.get("version", "1.0"),
        "scope": raw_model.get("scope"),
        "completeness": raw_model.get("completeness"),
        "root_node": root["id"],
        "nodes": nodes,
    }


def normalize_governance_model(raw_model):
    if "nodes" in raw_model and "root_node" in raw_model:
        model = {
            "version": raw_model.get("version", "1.0"),
            "scope": raw_model.get("scope"),
            "completeness": raw_model.get("completeness"),
            "root_node": raw_model["root_node"],
            "nodes": [normalize_node(node) for node in raw_model.get("nodes", [])],
        }
    else:
        model = nested_tree_to_node_registry(raw_model)
    return model


def get_scope_levels(needs_data):
    levels = needs_data.get("taxonomy", {}).get("scope_levels", [])
    indexed = []
    for index, level in enumerate(levels):
        normalized = dict(level)
        normalized.setdefault("order", index)
        indexed.append(normalized)
    return sorted(indexed, key=lambda level: level["order"])


def get_scope_order_map(needs_data):
    return {level["code"]: level["order"] for level in get_scope_levels(needs_data)}


def get_scope_label_map(needs_data):
    labels = {}
    for level in get_scope_levels(needs_data):
        labels[level["code"]] = f"{level['code']} ({level['name'].lower()})"
    return labels


def build_node_index(model):
    return {node["id"]: node for node in model.get("nodes", [])}


def get_node(model, node_id):
    return build_node_index(model).get(node_id)


def get_root_node(model):
    return get_node(model, model.get("root_node"))


def is_active_node(node):
    return node.get("status", "active") in ACTIVE_STATUSES


def iter_nodes(model, include_inactive=True):
    for node in model.get("nodes", []):
        if include_inactive or is_active_node(node):
            yield node


def iter_nodes_by_type(model, node_type, include_inactive=False):
    for node in iter_nodes(model, include_inactive=include_inactive):
        if node.get("type") == node_type:
            yield node


def iter_child_nodes(model, node, include_inactive=True):
    nodes_by_id = build_node_index(model)
    for child_id in node.get("child_ids", []):
        child = nodes_by_id.get(child_id)
        if not child:
            continue
        if include_inactive or is_active_node(child):
            yield child


def iter_requirement_edges(model, include_inactive=False):
    for node in iter_nodes(model, include_inactive=include_inactive):
        for req in node.get("meta", {}).get("requires", []):
            yield (node.get("id"), req.get("node"), req.get("need"))


def governance_adjacency(model, include_inactive=True):
    adjacency = {node["id"]: set() for node in iter_nodes(model, include_inactive=include_inactive)}
    nodes_by_id = build_node_index(model)
    for node in iter_nodes(model, include_inactive=include_inactive):
        node_id = node["id"]
        parent_id = node.get("parent_id")
        if parent_id and parent_id in nodes_by_id:
            parent = nodes_by_id[parent_id]
            if include_inactive or is_active_node(parent):
                adjacency.setdefault(node_id, set()).add(parent_id)
                adjacency.setdefault(parent_id, set()).add(node_id)
        for child_id in node.get("child_ids", []):
            child = nodes_by_id.get(child_id)
            if not child:
                continue
            if include_inactive or is_active_node(child):
                adjacency.setdefault(node_id, set()).add(child_id)
                adjacency.setdefault(child_id, set()).add(node_id)
    return adjacency


def governance_distance(model, source_id, target_id):
    if source_id == target_id:
        return 0
    adjacency = governance_adjacency(model, include_inactive=False)
    if source_id not in adjacency or target_id not in adjacency:
        return -1
    queue = deque([(source_id, 0)])
    visited = {source_id}
    while queue:
        node_id, distance = queue.popleft()
        for neighbor_id in adjacency.get(node_id, []):
            if neighbor_id in visited:
                continue
            if neighbor_id == target_id:
                return distance + 1
            visited.add(neighbor_id)
            queue.append((neighbor_id, distance + 1))
    return -1
