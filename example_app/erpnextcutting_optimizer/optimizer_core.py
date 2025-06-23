#
# 1D Cutting Optimizer - Core Logic
#
from ortools.sat.python import cp_model

def run_1d_optimizer(stock_data, parts_data, saw_kerf, allow_overproduction=False):
    """
    Main function to run a single 1D optimization problem.
    This is the computational core.
    """
    all_patterns = _generate_all_patterns(stock_data, parts_data, saw_kerf)
    if not all_patterns:
        return None

    solution = _solve_cutting_problem(all_patterns, stock_data, parts_data, allow_overproduction)
    return solution

def _solve_cutting_problem(all_patterns, stock_data, parts_data, allow_overproduction):
    model = cp_model.CpModel()
    parts_map = {f"{part['length']}": part for part in parts_data}

    max_usage_heuristic = sum(p['demand'] for p in parts_data) + 10 # Safety buffer

    # Variable: How many times is each pattern used?
    num_times_pattern_used = [
        model.NewIntVar(0, max_usage_heuristic, f"pattern_{p['pattern_id']}") for p in all_patterns
    ]

    # Constraint: Produce at least the required number of each part.
    for part in parts_data:
        part_id = f"{part['length']}"
        constraint_expr = sum(
            num_times_pattern_used[i] * p['yield'].get(part_id, 0) for i, p in enumerate(all_patterns)
        )
        if allow_overproduction:
            model.Add(constraint_expr >= part['demand'])
        else:
            model.Add(constraint_expr == part['demand'])

    # Constraint: Don't use more stock than available (if specified).
    for stock_id, stock_info in stock_data.items():
        if 'available' in stock_info:
            model.Add(sum(
                num_times_pattern_used[i] for i, p in enumerate(all_patterns) if p['stock_id_used'] == stock_id
            ) <= stock_info['available'])

    # Objective: Minimize the total number of stock bars used.
    # A cost-based objective can be re-introduced later if needed.
    total_stock_used = sum(num_times_pattern_used)
    model.Minimize(total_stock_used)

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 30.0
    status = solver.Solve(model)

    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        # --- Package up the results ---
        total_bars_used_map = {sid: 0 for sid in stock_data}
        total_parts_produced_map = {f"{p['length']}": 0 for p in parts_data}
        
        used_patterns = []
        for i, pattern in enumerate(all_patterns):
            usage_count = solver.Value(num_times_pattern_used[i])
            if usage_count > 0:
                # Add usage count to the pattern dict for later reference
                pattern_with_usage = pattern.copy()
                pattern_with_usage['usage_count'] = usage_count
                used_patterns.append(pattern_with_usage)

                # Aggregate totals
                stock_id = pattern['stock_id_used']
                total_bars_used_map[stock_id] += usage_count
                for part_id, yielded_count in pattern['yield'].items():
                    total_parts_produced_map[part_id] += yielded_count * usage_count

        return {
            "status": "Success",
            "total_stock_items_used": total_bars_used_map,
            "total_parts_produced": total_parts_produced_map,
            "patterns": used_patterns
        }
    return None

def _generate_all_patterns(stock_data, parts_data, saw_kerf):
    all_patterns = []
    # Create a unique ID for each part based on length for the yield dict
    parts_map = {f"{part['length']}": part for part in parts_data}
    
    # Sort parts from longest to shortest.
    sorted_parts = sorted(parts_data, key=lambda p: p['length'], reverse=True)

    for stock_id, stock_info in stock_data.items():
        stock_length = stock_info['length']
        generated_for_stock, pattern_hashes = [], set()
        
        _generate_recursive(
            stock_length=stock_length,
            remaining_length=stock_length,
            current_yield={},
            current_layout=[], # Track the visual layout
            parts_to_try=sorted_parts,
            generated_patterns=generated_for_stock,
            pattern_hashes=pattern_hashes,
            stock_id=stock_id,
            saw_kerf=saw_kerf
        )
        all_patterns.extend(generated_for_stock)
    return all_patterns

def _add_pattern_if_new(current_yield, layout_details, generated_patterns, pattern_hashes, stock_id, stock_length, saw_kerf):
    if not current_yield:
        return

    yield_tuple = tuple(sorted(current_yield.items()))
    if yield_tuple in pattern_hashes:
        return

    pattern_hashes.add(yield_tuple)
    
    total_parts_len = sum(part['length'] for part in layout_details)
    num_cuts = len(layout_details)
    total_kerf_len = num_cuts * saw_kerf
    
    # Correct waste calculation considers that the last part doesn't always need a kerf cut from the remnant
    if layout_details:
        total_used = total_parts_len + (num_cuts - 1) * saw_kerf
        if total_used + saw_kerf < stock_length:
             total_kerf_len = num_cuts * saw_kerf
        else:
            total_kerf_len = (num_cuts -1) * saw_kerf
    
    total_used_len = total_parts_len + total_kerf_len
    waste = stock_length - total_used_len

    generated_patterns.append({
        'pattern_id': f"pat_{len(generated_patterns)}",
        'stock_id_used': stock_id,
        'yield': current_yield.copy(),
        'layout_pieces': layout_details,
        'total_used_length_in_pattern': total_used_len,
        'waste_length_in_pattern': waste,
        'num_cuts_in_pattern': num_cuts,
        'total_kerf_length_in_pattern': total_kerf_len,
        'total_parts_length_in_pattern': total_parts_len
    })


def _generate_recursive(stock_length, remaining_length, current_yield, current_layout, parts_to_try, generated_patterns, pattern_hashes, stock_id, saw_kerf):
    # A pattern is valid if it contains at least one part.
    if current_yield:
        _add_pattern_if_new(current_yield, current_layout, generated_patterns, pattern_hashes, stock_id, stock_length, saw_kerf)

    # Explore adding more parts.
    for i, part in enumerate(parts_to_try):
        length_needed = part['length']
        # Add a saw kerf for every cut, including the first.
        if current_layout: # No kerf needed before the first piece
            length_needed += saw_kerf

        if length_needed <= remaining_length:
            new_yield = current_yield.copy()
            part_id = f"{part['length']}"
            new_yield[part_id] = new_yield.get(part_id, 0) + 1
            
            new_layout = current_layout + [{'part_id': part_id, 'length': part['length']}]

            _generate_recursive(
                stock_length,
                remaining_length - length_needed,
                new_yield,
                new_layout,
                parts_to_try[i:], # We can reuse the same part
                generated_patterns,
                pattern_hashes,
                stock_id,
                saw_kerf
            ) 