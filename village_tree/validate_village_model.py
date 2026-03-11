#!/usr/bin/env python3
"""
Validate the canonical governance model.
Checks:
    - village_needs_catalog.yaml structure and taxonomy rules
  - barrier structure and semantics
    - village_governance_tree.yaml references and scope consistency
Run: python validate_village_model.py
"""
import sys

from village_model_io import build_node_index, get_scope_order_map, iter_nodes, load_needs, load_tree


VALID_BARRIER_TYPES = {"cost", "expertise", "population", "infrastructure", "geography", "regulation"}
VALID_TIME_HORIZONS = {"immediate", "near_term", "medium_term", "long_term"}
VALID_CONFIDENCE = {"low", "medium", "high", "provisional"}
VALID_EVIDENCE_KINDS = {"citation", "field_observation", "policy", "estimate", "model_assumption"}
VALID_NODE_STATUSES = {"active", "planned", "merged", "split", "archived"}


def collect_scope_codes(needs_data):
    return {level.get("code") for level in needs_data.get("taxonomy", {}).get("scope_levels", []) if level.get("code")}


def validate_taxonomy(needs_data):
    errors = []
    levels = needs_data.get("taxonomy", {}).get("scope_levels", [])
    if not levels:
        return ["taxonomy.scope_levels must not be empty"]

    codes = set()
    orders = set()
    for index, level in enumerate(levels):
        code = level.get("code")
        order = level.get("order")
        if not code:
            errors.append(f"Scope level {index}: missing code")
        elif code in codes:
            errors.append(f"Duplicate scope code: {code}")
        codes.add(code)
        if order is None:
            errors.append(f"Scope level {code or index}: missing order")
        elif order in orders:
            errors.append(f"Duplicate scope order: {order}")
        orders.add(order)
    return errors


def validate_needs(needs_data):
    errors = []
    needs = needs_data.get("needs", [])
    ids = set()
    valid_scopes = collect_scope_codes(needs_data)
    valid_categories = {"water", "energy", "food", "shelter", "clothing", "transport",
                       "communication", "education", "health", "governance", "commerce",
                       "environment", "conservation", "sanitation", "social", "industry",
                       "vulnerable", "technology", "infrastructure", "security", "legal", "identity"}

    for i, need in enumerate(needs):
        # ID unique
        need_id = need.get("id")
        if not need_id:
            errors.append(f"Need {i}: missing id")
            continue
        if need_id in ids:
            errors.append(f"Duplicate id: {need_id}")
        ids.add(need_id)

        # Required fields
        for field in ["id", "name", "category", "scope_options"]:
            if field not in need:
                errors.append(f"Need {need.get('id', i)}: missing {field}")

        # Category valid
        if need.get("category") and need["category"] not in valid_categories:
            errors.append(f"Need {need_id}: invalid category {need['category']}")

        # scope_options non-empty and valid
        opts = need.get("scope_options", [])
        if not opts:
            errors.append(f"Need {need_id}: scope_options empty")
        for s in opts:
            if s not in valid_scopes:
                errors.append(f"Need {need_id}: invalid scope {s}")

        # barrier structure
        for j, barrier in enumerate(need.get("barriers", [])):
            b_type = barrier.get("type")
            if b_type not in VALID_BARRIER_TYPES:
                errors.append(f"Need {need_id}: barrier {j} invalid type '{b_type}'")
            if not barrier.get("description"):
                errors.append(f"Need {need_id}: barrier {j} missing description")
            holds_at = barrier.get("holds_at")
            if holds_at and holds_at not in valid_scopes:
                errors.append(f"Need {need_id}: barrier {j} invalid holds_at '{holds_at}'")

        feasibility = need.get("feasibility")
        if feasibility:
            target_scope = feasibility.get("target_scope")
            if target_scope and target_scope not in valid_scopes:
                errors.append(f"Need {need_id}: feasibility invalid target_scope '{target_scope}'")
            if target_scope and target_scope not in opts:
                errors.append(f"Need {need_id}: feasibility target_scope '{target_scope}' not in scope_options {opts}")
            for field in ["investment_cost_band", "maintenance_cost_band", "implementation_difficulty_band"]:
                value = feasibility.get(field)
                if value is not None and not (1 <= value <= 5):
                    errors.append(f"Need {need_id}: feasibility {field} must be between 1 and 5")
            time_horizon = feasibility.get("time_horizon")
            if time_horizon and time_horizon not in VALID_TIME_HORIZONS:
                errors.append(f"Need {need_id}: feasibility invalid time_horizon '{time_horizon}'")

        confidence = need.get("confidence")
        if confidence and confidence not in VALID_CONFIDENCE:
            errors.append(f"Need {need_id}: invalid confidence '{confidence}'")

        for j, evidence in enumerate(need.get("evidence", [])):
            kind = evidence.get("kind")
            if kind not in VALID_EVIDENCE_KINDS:
                errors.append(f"Need {need_id}: evidence {j} invalid kind '{kind}'")
            if not evidence.get("notes"):
                errors.append(f"Need {need_id}: evidence {j} missing notes")

    # depends_on references exist
    all_ids = {n["id"] for n in needs}
    for need in needs:
        for dep in need.get("depends_on", []):
            if dep not in all_ids:
                errors.append(f"Need {need['id']}: depends_on '{dep}' not found")

    return errors


def validate_tree(model, needs_data):
    errors = []
    needs = needs_data.get("needs", [])
    needs_by_id = {n["id"]: n for n in needs}
    nodes = list(iter_nodes(model, include_inactive=True))
    nodes_by_id = build_node_index(model)
    valid_scopes = collect_scope_codes(needs_data)
    scope_order = get_scope_order_map(needs_data)
    root_id = model.get("root_node")

    if not root_id:
        errors.append("Governance model missing root_node")
    elif root_id not in nodes_by_id:
        errors.append(f"Governance model root_node '{root_id}' not found in nodes")

    seen_ids = set()
    for node in nodes:
        node_id = node.get("id")
        if not node_id:
            errors.append("Governance node missing id")
            continue
        if node_id in seen_ids:
            errors.append(f"Duplicate node id: {node_id}")
        seen_ids.add(node_id)

        node_type = node.get("type")
        if node_type not in valid_scopes:
            errors.append(f"Node {node_id}: invalid type '{node_type}'")

        status = node.get("status", "active")
        if status not in VALID_NODE_STATUSES:
            errors.append(f"Node {node_id}: invalid status '{status}'")

        parent_id = node.get("parent_id")
        if node_id == root_id:
            if parent_id is not None:
                errors.append(f"Root node {node_id}: parent_id must be null")
        elif not parent_id:
            errors.append(f"Node {node_id}: missing parent_id")
        elif parent_id not in nodes_by_id:
            errors.append(f"Node {node_id}: missing parent node '{parent_id}'")
        else:
            parent = nodes_by_id[parent_id]
            if node_id not in parent.get("child_ids", []):
                errors.append(f"Node {node_id}: parent {parent_id} does not list it in child_ids")
            if parent.get("type") in scope_order and node_type in scope_order:
                if scope_order[parent["type"]] <= scope_order[node_type]:
                    errors.append(
                        f"Node {node_id}: parent {parent_id} must be at a broader layer than child "
                        f"({parent.get('type')} <= {node_type})"
                    )

        child_ids = node.get("child_ids", [])
        if len(child_ids) != len(set(child_ids)):
            errors.append(f"Node {node_id}: child_ids contains duplicates")
        for child_id in child_ids:
            child = nodes_by_id.get(child_id)
            if not child:
                errors.append(f"Node {node_id}: missing child node '{child_id}'")
                continue
            if child.get("parent_id") != node_id:
                errors.append(f"Node {node_id}: child {child_id} does not point back with parent_id={node_id}")

        meta = node.get("meta", {})
        for need_id in meta.get("satisfies", []) + meta.get("provides", []):
            if need_id not in needs_by_id:
                errors.append(f"Node {node_id}: unknown need '{need_id}'")
                continue
            scope_options = needs_by_id[need_id].get("scope_options", [])
            if node_type not in scope_options:
                errors.append(
                    f"Node {node_id}: need '{need_id}' placed at scope {node_type} not allowed by {scope_options}"
                )

        for req in meta.get("requires", []):
            target_id = req.get("node")
            need_id = req.get("need")
            if not target_id or not need_id:
                errors.append(f"Node {node_id}: malformed requires entry {req}")
                continue
            if need_id not in needs_by_id:
                errors.append(f"Node {node_id}: requires unknown need '{need_id}'")
                continue
            if target_id not in nodes_by_id:
                errors.append(f"Node {node_id}: requires missing node '{target_id}'")
                continue
            target_meta = nodes_by_id[target_id].get("meta", {})
            offered = set(target_meta.get("satisfies", [])) | set(target_meta.get("provides", []))
            if need_id not in offered:
                errors.append(
                    f"Node {node_id}: requires '{need_id}' from {target_id}, but target does not satisfy/provide it"
                )

        for need_dep in meta.get("need_deps", []):
            need_id = need_dep.get("need")
            depends_on = need_dep.get("depends_on")
            if need_id and need_id not in needs_by_id:
                errors.append(f"Node {node_id}: need_deps unknown need '{need_id}'")
            if depends_on and depends_on not in needs_by_id:
                errors.append(f"Node {node_id}: need_deps unknown depends_on '{depends_on}'")

        lineage = node.get("lineage", {})
        for key in ("split_from", "merged_from"):
            for source_id in lineage.get(key, []):
                if source_id not in nodes_by_id:
                    errors.append(f"Node {node_id}: lineage {key} references missing node '{source_id}'")
        merged_into = lineage.get("merged_into")
        if merged_into and merged_into not in nodes_by_id:
            errors.append(f"Node {node_id}: lineage merged_into references missing node '{merged_into}'")

    if root_id in nodes_by_id:
        visited = set()
        stack = set()

        def walk(node_id):
            if node_id in stack:
                errors.append(f"Governance model contains a cycle at node '{node_id}'")
                return
            if node_id in visited:
                return
            stack.add(node_id)
            visited.add(node_id)
            for child_id in nodes_by_id[node_id].get("child_ids", []):
                if child_id in nodes_by_id:
                    walk(child_id)
            stack.remove(node_id)

        walk(root_id)
        for node_id in nodes_by_id:
            if node_id not in visited:
                errors.append(f"Node {node_id}: unreachable from root_node '{root_id}'")

    return errors

def main():
    needs_data = load_needs()
    tree_data = load_tree()

    errors = []
    errors.extend(validate_taxonomy(needs_data))
    if "needs" not in needs_data:
        errors.append("Missing 'needs' key")
    else:
        errors.extend(validate_needs(needs_data))
        errors.extend(validate_tree(tree_data, needs_data))

    if errors:
        print("Validation errors:")
        for e in errors:
            print(f"  - {e}")
        sys.exit(1)
    else:
        print(f"OK: {len(needs_data['needs'])} needs and governance model validated")

if __name__ == "__main__":
    main()
