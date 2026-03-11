#!/usr/bin/env python3
"""
Generate diagrams from village_governance_tree.yaml.
Outputs: village_governance_tree_ascii.txt, village_governance_tree_mermaid.mmd,
village_dependency_routes_mermaid.mmd, village_governance_tree_graphviz.dot,
village_governance_tree_graphviz.png
"""
from pathlib import Path

from village_model_io import build_node_index, get_node, get_root_node, governance_distance, iter_child_nodes, iter_nodes, load_tree, load_yaml

def load_needs_map(path):
    data = load_yaml(path)
    return {
        need["id"]: need.get("name", need["id"])
        for need in data.get("needs", [])
    }


def friendly_node_name(node):
    return node.get("name") or node.get("id", "unknown").replace("_", " ").title()


def need_label(need_id, needs_map):
    return needs_map.get(need_id, need_id.split(".")[-1].replace("_", " ").title())


def mermaid_node_line(node):
    label = friendly_node_name(node)
    return f'  {node["id"]}["{label}"]'


def dot_node_line(node):
    label = friendly_node_name(node).replace('"', r'\"')
    return f'  {node["id"]} [label="{label}"];'


def ascii_tree(model):
    lines = []
    root = get_root_node(model)

    def visit(node, prefix="", is_last=True):
        connector = "" if not prefix else ("└── " if is_last else "├── ")
        lines.append(prefix + connector + friendly_node_name(node))
        children = list(iter_child_nodes(model, node, include_inactive=False))
        next_prefix = prefix + ("    " if is_last and prefix else "│   " if prefix else "")
        for index, child in enumerate(children):
            visit(child, next_prefix, index == len(children) - 1)

    if root:
        visit(root, prefix="", is_last=True)

    return lines

def mermaid_tree(model):
    lines = ["graph TB"]
    for node in iter_nodes(model, include_inactive=False):
        lines.append(mermaid_node_line(node))
    for node in iter_nodes(model, include_inactive=False):
        for child in iter_child_nodes(model, node, include_inactive=False):
            lines.append(f"  {node['id']} --> {child['id']}")
    return "\n".join(lines)

def mermaid_deps(model, needs_map):
    edges = set()
    nodes_by_id = build_node_index(model)
    for node in iter_nodes(model, include_inactive=False):
        for req in node.get("meta", {}).get("requires", []):
            edges.add((node["id"], req["node"], req["need"]))
    lines = ["graph LR"]
    for node in iter_nodes(model, include_inactive=False):
        lines.append(mermaid_node_line(node))
    for src, tgt, need in sorted(edges):
        label = need_label(need, needs_map)
        route_len = governance_distance(model, src, tgt)
        if tgt in nodes_by_id and route_len >= 0:
            label = f"{label} ({route_len})"
        lines.append(f'  {src} -->|{label}| {tgt}')
    return "\n".join(lines)

def dot_tree(model):
    lines = [
        "digraph village_tree {",
        "  rankdir=TB;",
        "  node [shape=box];",
    ]
    for node in iter_nodes(model, include_inactive=False):
        lines.append(dot_node_line(node))
    for node in iter_nodes(model, include_inactive=False):
        for child in iter_child_nodes(model, node, include_inactive=False):
            lines.append(f"  {node['id']} -> {child['id']};")
    lines.append("}")
    return "\n".join(lines)

def main():
    base = Path(__file__).parent
    data = load_tree()
    needs_map = load_needs_map(base / "village_needs_catalog.yaml")

    # ASCII
    ascii_lines = ascii_tree(data)
    (base / "village_governance_tree_ascii.txt").write_text("\n".join(ascii_lines))
    print("Wrote village_governance_tree_ascii.txt")

    # Mermaid (tree)
    (base / "village_governance_tree_mermaid.mmd").write_text(mermaid_tree(data))
    print("Wrote village_governance_tree_mermaid.mmd")

    # Mermaid (dependencies)
    (base / "village_dependency_routes_mermaid.mmd").write_text(mermaid_deps(data, needs_map))
    print("Wrote village_dependency_routes_mermaid.mmd")

    # DOT
    (base / "village_governance_tree_graphviz.dot").write_text(dot_tree(data))
    print("Wrote village_governance_tree_graphviz.dot")

    # Generate PNG if graphviz available
    try:
        import subprocess
        subprocess.run(["dot", "-Tpng", "-o", str(base / "village_governance_tree_graphviz.png"), str(base / "village_governance_tree_graphviz.dot")], check=True, capture_output=True)
        print("Wrote village_governance_tree_graphviz.png")
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("(Run: dot -Tpng -o village_governance_tree_graphviz.png village_governance_tree_graphviz.dot for PNG)")

if __name__ == "__main__":
    main()
