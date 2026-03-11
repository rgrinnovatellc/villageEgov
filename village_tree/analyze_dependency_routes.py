#!/usr/bin/env python3
"""Analyze dependency routes, barriers, feasibility, and budget scenarios."""

import sys
from collections import defaultdict

from village_model_io import get_scope_label_map, get_scope_order_map, governance_distance, iter_nodes, load_needs, load_scenarios, load_tree

SCOPE_ORDER = {}
SCOPE_NAMES = {}


def configure_scope_maps(needs_data):
    global SCOPE_ORDER, SCOPE_NAMES
    SCOPE_ORDER = get_scope_order_map(needs_data)
    scope_labels = get_scope_label_map(needs_data)
    SCOPE_NAMES = {order: scope_labels[code] for code, order in SCOPE_ORDER.items()}


def lowest_scope_code():
    return min(SCOPE_ORDER, key=SCOPE_ORDER.get)


def collect_household_routes(model, needs_by_id=None):
    routes = []
    source_scope = lowest_scope_code()
    for node in iter_nodes(model, include_inactive=False):
        if node.get("type") != source_scope:
            continue
        household_id = node["id"]
        meta = node.get("meta", {})
        for need_id in meta.get("satisfies", []):
            routes.append((household_id, need_id, 0, household_id))
        for req in meta.get("requires", []):
            target = req.get("node")
            need = req.get("need")
            if target and need:
                route_len = governance_distance(model, household_id, target)
                routes.append((household_id, need, route_len, target))
    return routes


def find_pushdown_opportunities(routes, needs_by_id):
    opportunities = []
    for household_id, need_id, route_len, target in routes:
        if route_len <= 0:
            continue
        need = needs_by_id.get(need_id)
        if not need:
            continue
        min_possible = min(SCOPE_ORDER.get(scope, 99) for scope in need.get("scope_options", []))
        if min_possible < route_len:
            opportunities.append(
                {
                    "household": household_id,
                    "need": need_id,
                    "current_route": route_len,
                    "min_possible": min_possible,
                    "saving": route_len - min_possible,
                    "target_node": target,
                }
            )
    return opportunities


def compute_score(routes):
    total = len(routes)
    if not total:
        return 100.0
    actual = sum(max(route_len, 0) for _, _, route_len, _ in routes)
    max_possible = max(SCOPE_ORDER.values(), default=0) * total
    if max_possible == 0:
        return 100.0
    return 100 * (1 - actual / max_possible)


def apply_whatif(routes, need_id, target_scope_code):
    target_scope = SCOPE_ORDER.get(target_scope_code, 0)
    updated = []
    for household_id, route_need_id, route_len, target_node in routes:
        if route_need_id == need_id and route_len > target_scope:
            updated.append((household_id, route_need_id, target_scope, f"(pushed to {target_scope_code})"))
        else:
            updated.append((household_id, route_need_id, route_len, target_node))
    return updated


def build_feasibility_rows(routes, needs_by_id):
    grouped = defaultdict(list)
    for opportunity in find_pushdown_opportunities(routes, needs_by_id):
        grouped[opportunity["need"]].append(opportunity)

    rows = []
    for need_id, opportunities in grouped.items():
        need = needs_by_id.get(need_id, {})
        feasibility = need.get("feasibility")
        if not feasibility:
            continue
        households = len({item["household"] for item in opportunities})
        total_hop_savings = sum(item["saving"] for item in opportunities)
        per_household_saving = opportunities[0]["saving"]
        investment = feasibility.get("investment_cost_band", 3)
        maintenance = feasibility.get("maintenance_cost_band", 3)
        difficulty = feasibility.get("implementation_difficulty_band", 3)
        effort_total = investment + maintenance + difficulty
        rows.append(
            {
                "need": need_id,
                "target_scope": feasibility.get("target_scope", "?"),
                "households": households,
                "per_household_saving": per_household_saving,
                "total_hop_savings": total_hop_savings,
                "investment": investment,
                "maintenance": maintenance,
                "difficulty": difficulty,
                "time_horizon": feasibility.get("time_horizon", "?"),
                "savings_per_cost": total_hop_savings / investment if investment else total_hop_savings,
                "savings_per_effort": total_hop_savings / effort_total if effort_total else total_hop_savings,
                "confidence": need.get("confidence", "provisional"),
                "evidence": need.get("evidence", []),
                "feasibility_notes": feasibility.get("notes", ""),
                "barriers": need.get("barriers", []),
            }
        )
    rows.sort(key=lambda row: (-row["savings_per_effort"], -row["total_hop_savings"], row["investment"]))
    return rows


def optimize_budget(rows, budget_band):
    budget_band = max(0, int(budget_band))
    dp = [(0, []) for _ in range(budget_band + 1)]
    for idx, row in enumerate(rows):
        cost = row["investment"]
        value = row["total_hop_savings"]
        for budget in range(budget_band, cost - 1, -1):
            prev_value, prev_items = dp[budget - cost]
            candidate_value = prev_value + value
            current_value, _ = dp[budget]
            if candidate_value > current_value:
                dp[budget] = (candidate_value, prev_items + [idx])
    best_value, best_items = max(dp, key=lambda item: item[0])
    selected = [rows[idx] for idx in best_items]
    total_cost = sum(item["investment"] for item in selected)
    return {
        "budget_band": budget_band,
        "total_hop_savings": best_value,
        "total_investment_cost": total_cost,
        "selected": selected,
    }


def build_budget_scenario_result(rows, scenario):
    result = optimize_budget(rows, scenario.get("budget_band", 0))
    result.update(
        {
            "id": scenario.get("id"),
            "name": scenario.get("name"),
            "objective": scenario.get("objective", "maximize_hop_savings"),
            "notes": scenario.get("notes", ""),
        }
    )
    return result


def print_report(routes, needs_by_id, label="CURRENT"):
    total_deps = len(routes)
    self_satisfied = sum(1 for _, _, route_len, _ in routes if route_len == 0)
    by_length = defaultdict(int)
    for _, _, route_len, _ in routes:
        by_length[route_len] += 1
    avg_route = sum(max(route_len, 0) for _, _, route_len, _ in routes) / total_deps if total_deps else 0
    dep_routes = [route_len for _, _, route_len, _ in routes if route_len > 0]
    avg_route_deps_only = sum(dep_routes) / len(dep_routes) if dep_routes else 0

    print("=" * 65)
    print(f"  DEPENDENCY ROUTE ANALYSIS - {label}")
    print("=" * 65)
    print()
    print(f"Total household need-entries:  {total_deps}")
    for length in sorted(length for length in by_length if length >= 0):
        if length == 0:
            label_name = "self"
        else:
            label_name = SCOPE_NAMES.get(length, f"layer {length}")
        print(f"  Route length {length} ({label_name}):{by_length.get(length, 0):>10}")
    if by_length.get(-1, 0):
        print(f"  Route unresolved (-1):{by_length.get(-1, 0):>15}")
    print()
    print(f"Average route length (all):    {avg_route:.2f}")
    print(f"Average route length (deps):   {avg_route_deps_only:.2f}")
    if total_deps:
        print(f"Self-sufficiency ratio:        {self_satisfied}/{total_deps} ({100 * self_satisfied / total_deps:.0f}%)")
    print()

    hh_routes = defaultdict(list)
    for household_id, _, route_len, _ in routes:
        hh_routes[household_id].append(route_len)
    print("-" * 65)
    print("  Per-Household Self-Sufficiency")
    print("-" * 65)
    print(f"{'Household':<12} {'Needs':>6} {'Self':>6} {'Dep':>6} {'Avg Route':>10} {'Self%':>6}")
    print("-" * 65)
    for household_id in sorted(hh_routes):
        household_routes = hh_routes[household_id]
        n_self = sum(1 for route_len in household_routes if route_len == 0)
        n_dep = sum(1 for route_len in household_routes if route_len > 0)
        avg = sum(max(route_len, 0) for route_len in household_routes) / len(household_routes) if household_routes else 0
        pct = 100 * n_self / len(household_routes) if household_routes else 0
        print(f"{household_id:<12} {len(household_routes):>6} {n_self:>6} {n_dep:>6} {avg:>10.2f} {pct:>5.0f}%")
    print()

    score = compute_score(routes)
    print("=" * 65)
    print(f"  SELF-SUFFICIENCY SCORE: {score:.1f}%")
    print("  (100% = all needs self-satisfied; lower scores indicate longer governance routes)")
    print("=" * 65)
    return score


def print_pushdown(routes, needs_by_id):
    opportunities = find_pushdown_opportunities(routes, needs_by_id)
    print()
    print("-" * 65)
    print("  Push-Down Opportunities")
    print("  (needs where actual route > minimum possible scope)")
    print("-" * 65)
    if not opportunities:
        print("  None - all needs are at their minimum possible scope.")
        return
    by_need = defaultdict(list)
    for opportunity in opportunities:
        by_need[opportunity["need"]].append(opportunity)
    print(f"{'Need':<35} {'Current':>8} {'Min':>8} {'Saving':>8} {'Households':>12}")
    print("-" * 65)
    for need_id in sorted(by_need):
        current = by_need[need_id][0]["current_route"]
        min_possible = by_need[need_id][0]["min_possible"]
        saving = by_need[need_id][0]["saving"]
        household_count = len({item["household"] for item in by_need[need_id]})
        print(f"{need_id:<35} {current:>8} {min_possible:>8} {saving:>8} {household_count:>12}")
        for barrier in needs_by_id.get(need_id, {}).get("barriers", []):
            removable = "removable" if barrier.get("removable", False) else "structural"
            holds_at = barrier.get("holds_at", "?")
            print(f"  {'':>35} ^ barrier ({removable}, holds_at={holds_at}): {barrier.get('type', '?')}: {barrier.get('description', '')}")


def print_barriers(needs_by_id):
    print()
    print("=" * 65)
    print("  ALL BARRIERS - What prevents push-down?")
    print("=" * 65)
    print()
    removable_count = 0
    structural_count = 0
    for need_id in sorted(needs_by_id):
        need = needs_by_id[need_id]
        barriers = need.get("barriers", [])
        if not barriers:
            continue
        min_scope = min(SCOPE_ORDER.get(scope, 99) for scope in need.get("scope_options", []))
        print(f"  {need_id}")
        print(f"    min possible scope: {SCOPE_NAMES.get(min_scope, '?')}")
        print(f"    confidence: {need.get('confidence', 'provisional')}")
        for evidence in need.get("evidence", []):
            citation = evidence.get("citation")
            print(f"    evidence[{evidence.get('kind')}]: {citation or evidence.get('notes', '')}")
        for barrier in barriers:
            removable = barrier.get("removable", False)
            tag = "REMOVABLE" if removable else "STRUCTURAL"
            if removable:
                removable_count += 1
            else:
                structural_count += 1
            print(f"    [{tag}] {barrier.get('type', '?')} (holds_at={barrier.get('holds_at', '?')}): {barrier.get('description', '')}")
        print()
    print(f"  Summary: {removable_count} removable barriers, {structural_count} structural barriers")
    print("  Removable barriers are the investment targets for self-sufficiency.")
    print()


def print_feasibility(routes, needs_by_id):
    rows = build_feasibility_rows(routes, needs_by_id)
    print("=" * 80)
    print("  FEASIBILITY RANKING - Route Savings vs Cost and Effort")
    print("=" * 80)
    print()
    if not rows:
        print("  No feasibility profiles documented for current push-down opportunities.")
        print()
        return
    print(f"{'Need':<30} {'Target':>6} {'HH':>4} {'Save':>6} {'Inv':>4} {'Maint':>5} {'Diff':>4} {'ROI':>6} {'Priority':>8}")
    print("-" * 80)
    for row in rows:
        print(f"{row['need']:<30} {row['target_scope']:>6} {row['households']:>4} {row['total_hop_savings']:>6} {row['investment']:>4} {row['maintenance']:>5} {row['difficulty']:>4} {row['savings_per_cost']:>6.2f} {row['savings_per_effort']:>8.2f}")
        print(f"  {'':<30} horizon={row['time_horizon']}, confidence={row['confidence']}, per-household saving={row['per_household_saving']}")
    print()
    print("  ROI = total hop savings / investment cost band")
    print("  Priority = total hop savings / (investment + maintenance + difficulty)")
    print()


def print_budget_plan(rows, budget_band):
    result = optimize_budget(rows, budget_band)
    print("=" * 80)
    print(f"  BUDGET PLAN - budget band {budget_band}")
    print("=" * 80)
    print(f"  Selected interventions: {len(result['selected'])}")
    print(f"  Total investment cost: {result['total_investment_cost']}")
    print(f"  Total hop savings:     {result['total_hop_savings']}")
    print()
    for item in result["selected"]:
        print(f"  - {item['need']} -> {item['target_scope']} | save={item['total_hop_savings']} | inv={item['investment']} | confidence={item['confidence']}")
    print()
    return result


def print_named_scenarios(rows, scenarios):
    print("=" * 80)
    print("  NAMED BUDGET SCENARIOS")
    print("=" * 80)
    print()
    for scenario in scenarios.get("budget_scenarios", []):
        result = build_budget_scenario_result(rows, scenario)
        print(f"  {result['name']} ({result['id']})")
        print(f"    budget_band: {result['budget_band']}")
        print(f"    total_hop_savings: {result['total_hop_savings']}")
        print(f"    total_investment_cost: {result['total_investment_cost']}")
        if result["notes"]:
            print(f"    notes: {result['notes']}")
        for item in result["selected"]:
            print(f"    - {item['need']} -> {item['target_scope']} | save={item['total_hop_savings']} | inv={item['investment']}")
        print()


def print_irreducible(routes, needs_by_id):
    print("-" * 65)
    print("  Irreducible Dependencies (min scope = current scope)")
    print("-" * 65)
    irreducible = set()
    for _, need_id, route_len, _ in routes:
        if route_len == 0:
            continue
        need = needs_by_id.get(need_id)
        if not need:
            continue
        min_possible = min(SCOPE_ORDER.get(scope, 99) for scope in need.get("scope_options", []))
        if min_possible >= route_len:
            irreducible.add((need_id, route_len, SCOPE_NAMES.get(min_possible, "?")))
    for need_id, route_len, scope_name in sorted(irreducible):
        print(f"  {need_id:<35} route={route_len}  min_scope={scope_name}")
    print()


def main():
    needs_data = load_needs()
    tree_data = load_tree()
    scenarios = load_scenarios()
    configure_scope_maps(needs_data)
    needs_by_id = {need["id"]: need for need in needs_data["needs"]}
    routes = collect_household_routes(tree_data, needs_by_id)
    rows = build_feasibility_rows(routes, needs_by_id)
    args = sys.argv[1:]

    if "--barriers" in args:
        print_barriers(needs_by_id)
        return
    if "--feasibility" in args:
        print_feasibility(routes, needs_by_id)
        return
    if "--budget" in args:
        idx = args.index("--budget")
        if idx + 1 >= len(args):
            print("Usage: --budget <band>")
            sys.exit(1)
        print_budget_plan(rows, int(args[idx + 1]))
        return
    if "--scenarios" in args:
        print_named_scenarios(rows, scenarios)
        return
    if "--whatif" in args:
        idx = args.index("--whatif")
        if idx + 2 >= len(args):
            print("Usage: --whatif <need_id> <target_scope>")
            print("  e.g.: --whatif food.processing.mill H")
            sys.exit(1)
        whatif_need = args[idx + 1]
        whatif_scope = args[idx + 2].upper()
        if whatif_need not in needs_by_id:
            print(f"Error: need '{whatif_need}' not found in village_needs_catalog.yaml")
            sys.exit(1)
        if whatif_scope not in SCOPE_ORDER:
            print(f"Error: scope '{whatif_scope}' not valid (use one of: {', '.join(sorted(SCOPE_ORDER))})")
            sys.exit(1)
        current_score = print_report(routes, needs_by_id, "CURRENT STATE")
        print()
        new_routes = apply_whatif(routes, whatif_need, whatif_scope)
        new_score = print_report(new_routes, needs_by_id, f"WHAT-IF: {whatif_need} -> {whatif_scope}")
        print()
        delta = new_score - current_score
        need = needs_by_id[whatif_need]
        print("=" * 65)
        print("  SCENARIO COMPARISON")
        print("=" * 65)
        print(f"  Need:            {whatif_need}")
        print(f"  Push to:         {whatif_scope} ({SCOPE_NAMES.get(SCOPE_ORDER[whatif_scope], '')})")
        print(f"  Score change:    {current_score:.1f}% -> {new_score:.1f}% (+{delta:.1f}%)")
        barriers = need.get("barriers", [])
        if barriers:
            print("  Barriers to overcome:")
            for barrier in barriers:
                tag = "removable" if barrier.get("removable") else "structural"
                print(f"    - [{tag}] {barrier.get('type')}: {barrier.get('description')}")
        feasibility = need.get("feasibility")
        if feasibility:
            print("  Feasibility:")
            for field in ["target_scope", "investment_cost_band", "maintenance_cost_band", "implementation_difficulty_band", "time_horizon"]:
                print(f"    - {field}: {feasibility.get(field, '?')}")
        print(f"  Confidence:      {need.get('confidence', 'provisional')}")
        print("=" * 65)
        return

    print_report(routes, needs_by_id, "Self-Sufficiency Report")
    print_pushdown(routes, needs_by_id)
    print_irreducible(routes, needs_by_id)
    print_barriers(needs_by_id)
    print_feasibility(routes, needs_by_id)
    print_named_scenarios(rows, scenarios)


if __name__ == "__main__":
    main()
