#!/usr/bin/env python3
"""
Check that village_governance_tree.yaml covers all needs from the canonical village_needs_catalog.yaml.
Run: python check_needs_coverage.py
"""
from village_model_io import iter_nodes, load_needs, load_tree

def collect_needs_from_model(model):
    """Collect all need ids referenced anywhere in the governance model."""
    covered = set()
    for node in iter_nodes(model, include_inactive=True):
        meta = node.get("meta", {})
        covered.update(meta.get("satisfies", []))
        covered.update(meta.get("provides", []))
        for req in meta.get("requires", []):
            need_id = req.get("need")
            if need_id:
                covered.add(need_id)
        for need_dep in meta.get("need_deps", []):
            if need_dep.get("need"):
                covered.add(need_dep["need"])
            if need_dep.get("depends_on"):
                covered.add(need_dep["depends_on"])
    return covered

def main():
    needs_data = load_needs()
    governance_model = load_tree()

    all_need_ids = {n["id"] for n in needs_data["needs"]}
    # Exclude external/10% scope
    external = {"energy.cooking.lpg", "health.hospital"}
    required = all_need_ids - external

    covered = collect_needs_from_model(governance_model)

    missing = required - covered
    extra = covered - all_need_ids

    if missing:
        print("MISSING needs (not in tree):")
        for m in sorted(missing):
            print(f"  - {m}")
        print()

    if extra:
        print("EXTRA (in tree but not in needs model):")
        for e in sorted(extra):
            print(f"  - {e}")
        print()

    pct = 100 * len(covered & required) / len(required) if required else 100
    print(f"Coverage: {len(covered & required)}/{len(required)} needs ({pct:.0f}%)")

    if missing:
        exit(1)
    print("OK: All needs covered")

if __name__ == "__main__":
    main()
