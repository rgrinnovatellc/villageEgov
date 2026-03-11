#!/usr/bin/env python3
"""
Extract dependency graph from village_governance_tree.yaml.
Output: list of (source_node, target_node, need) edges.
No GUI—just data.
"""
from village_model_io import iter_nodes, load_tree


def main():
    tree = load_tree()
    edges = []
    for node in iter_nodes(tree, include_inactive=False):
        for req in node.get("meta", {}).get("requires", []):
            target = req.get("node")
            need = req.get("need")
            if target and need:
                edges.append((node["id"], target, need))

    print("Dependency edges (source -> target, for need):")
    for src, tgt, need in edges:
        print(f"  {src} -> {tgt}  [{need}]")

if __name__ == "__main__":
    main()
