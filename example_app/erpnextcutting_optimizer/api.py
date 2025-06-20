# example_app/erpnextcutting_optimizer/api.py
import frappe
import json
import os
from frappe.utils.pdf import get_pdf
from frappe import _
from ortools.sat.python import cp_model
from datetime import datetime
import re
import copy
from .pdf_generator_1d import export_solution_to_pdf_1d # Assuming pdf_generator_1d is in the same directory

# ==============================================================================
# 1. ENQUEUEING METHOD (WHITELISTED)
# ==============================================================================

@frappe.whitelist()
def enqueue_optimization_job(doctype, docname, request_data_json):
    """
    This is the whitelisted function called from the client-side script.
    It enqueues the actual optimization job to run in the background.
    """
    frappe.enqueue(
        "example_app.erpnextcutting_optimizer.api.run_optimization_job",
        queue='long',
        timeout=1500,
        doctype=doctype,
        docname=docname,
        request_data_json=request_data_json,
        user=frappe.session.user
    )
    frappe.msgprint(_("Optimization job has been started. You will be notified upon completion."), alert=True)

# ==============================================================================
# 2. BACKGROUND JOB
# ==============================================================================

def run_optimization_job(doctype, docname, request_data_json, user):
    """
    This function runs in the background. It performs the optimization,
    creates the necessary documents, and notifies the user.
    """
    try:
        # Avoid long log messages that exceed character limits
        frappe.log_error("Optimizer job started.", "Optimizer Debug Trace")
        
        request_data = json.loads(request_data_json)
        # Don't log the entire request data as it can be too long
        frappe.log_error("Request data loaded successfully", "Optimizer Debug Trace")
        
        # Use a specific output directory within the site's private files
        output_dir = os.path.join(frappe.utils.get_site_path(), "private", "files", "optimizer_output")
        os.makedirs(output_dir, exist_ok=True)
        frappe.log_error(f"Output directory set to: {output_dir}", "Optimizer Debug Trace")

        # Step 1: Run the core 1D Optimizer
        frappe.log_error("Running 1D optimizer...", "Optimizer Debug Trace")
        solution_data, pdf_path, all_patterns_dict = run_1d_optimizer(
            stock_data=request_data['stock_data'],
            parts_data=[{'name': name, **data} for name, data in request_data['parts_data'].items()],
            saw_kerf=request_data['saw_kerf'],
            project_description=request_data['project_description'],
            output_dir_base=output_dir,
            allow_overproduction=request_data.get('allow_overproduction', False)
        )
        frappe.log_error(f"Optimizer finished. Solution found: {'Yes' if solution_data else 'No'}", "Optimizer Debug Trace")

        if not solution_data:
            raise ValueError("Optimization failed. The problem is likely infeasible.")

        # Step 2: Update the original Sales Order with the solution
        # Note: This step is now optional and disabled by default
        try:
            frappe.log_error("Updating original Sales Order...", "Optimizer Debug Trace")
            update_so_with_solution(
                solution_data=solution_data,
                all_patterns_dict=all_patterns_dict,
                original_docname=docname # This is the Sales Order name
            )
            frappe.log_error(f"Sales Order {docname} updated.", "Optimizer Debug Trace")
        except Exception as e:
            frappe.log_error(f"Error updating Sales Order: {str(e)}\n{frappe.get_traceback()}", "Optimizer Error")
            # Continue with PDF attachment even if updating Sales Order fails

        # Step 3: Attach the generated PDF back to the original Sales Order
        frappe.log_error("Attaching PDF to Sales Order...", "Optimizer Debug Trace")
        if pdf_path and os.path.exists(pdf_path):
            try:
                frappe.log_error(f"PDF path exists: {pdf_path}", "Optimizer Debug Trace")
                with open(pdf_path, 'rb') as pdf_file:
                    file_content = pdf_file.read()
                    
                frappe.log_error(f"PDF file read, size: {len(file_content)} bytes", "Optimizer Debug Trace")
                
                file_doc = frappe.new_doc("File")
                file_doc.file_name = os.path.basename(pdf_path)
                file_doc.attached_to_doctype = doctype
                file_doc.attached_to_name = docname
                file_doc.file_url = f"/private/files/{os.path.basename(pdf_path)}"
                file_doc.content = file_content
                file_doc.is_private = 1
                file_doc.save(ignore_permissions=True)
                
                frappe.log_error(f"File document created with ID: {file_doc.name}", "Optimizer Debug Trace")
                
                # Clean up the local PDF file
                os.remove(pdf_path)
                frappe.log_error("PDF attached successfully and local file removed.", "Optimizer Debug Trace")
            except Exception as e:
                frappe.log_error(f"Error attaching PDF: {str(e)}\n{frappe.get_traceback()}", "Optimizer Error")
        else:
            frappe.log_error(f"PDF not found or not created. Path: {pdf_path}, Exists: {os.path.exists(pdf_path) if pdf_path else False}", "Optimizer Debug Trace")

        # Step 4: Notify the user of success - removed 'indicator' parameter
        frappe.log_error("Sending success notification.", "Optimizer Debug Trace")
        frappe.publish_realtime(
            event="show_alert",
            message=_("Optimization complete. Sales Order <a href='/app/sales-order/{0}'>{0}</a> has been updated with the cutting plan.").format(docname),
            user=user
        )
        frappe.log_error("Job completed successfully.", "Optimizer Debug Trace")

    except Exception as e:
        # Log the full traceback to the error log
        frappe.log_error(f"Optimization failed: {str(e)}\n{frappe.get_traceback()}", "Optimizer Job Failed")
        
        # Step 5: Notify the user of failure - removed 'indicator' parameter
        frappe.publish_realtime(
            event="show_alert",
            message=_("Optimization failed for Sales Order {0}. See Error Log for details.").format(docname),
            user=user
        )

# ==============================================================================
# 3. SALES ORDER UPDATE LOGIC
# ==============================================================================

def update_so_with_solution(solution_data, all_patterns_dict, original_docname):
    """
    Updates the original Sales Order with the raw materials from the solution.
    """
    so = frappe.get_doc("Sales Order", original_docname)

    # Don't clear the existing items - this was causing the issue
    # Instead, we'll create a PDF report only
    
    # Check if we should attempt to update the Sales Order items
    update_items = False
    
    if update_items:
        # Clear the existing items table which contains the finished parts
        so.set("items", [])
    
        # --- Build the new items table from the solution's raw material requirements ---
        stock_used = solution_data.get('total_stock_items_used', {})
        for item_code, qty in stock_used.items():
            if qty > 0:
                # Check if the item exists in the database before adding it
                if frappe.db.exists("Item", item_code):
                    so.append("items", {
                        "item_code": item_code,
                        "qty": qty,
                        # Any other fields you want to set, e.g., rate, warehouse
                        # "warehouse": so.set_warehouse, # Inherit from SO header if needed
                    })
                else:
                    frappe.log_error(f"Item {item_code} not found in the database. Skipping.", "Optimizer Item Error")
        
        # Save the updated sales order
        so.save(ignore_permissions=True)
        frappe.db.commit()
    
    return so.name

# ==============================================================================
# 4. CORE OPTIMIZER LOGIC (Adapted from optimizer_1d.py)
# ==============================================================================

def run_1d_optimizer(stock_data, parts_data, saw_kerf, project_description, output_dir_base, allow_overproduction=False):
    """
    Main function to run the 1D optimization.
    Returns: solution_details_1d, output_pdf_path, all_patterns_map
    """
    print("--- Starting 1D Optimization ---")

    # Generate all possible cutting patterns.
    all_patterns_1d = generate_all_patterns_1d(stock_data, parts_data, saw_kerf)
    if not all_patterns_1d:
        print("No valid cutting patterns could be generated.")
        return None, None, None

    # Solve the cutting stock problem to find the optimal combination of patterns.
    solution_details_1d = solve_1d_cutting_problem(all_patterns_1d, stock_data, parts_data, allow_overproduction)
    if not solution_details_1d:
        print("Solver failed to find a feasible solution.")
        return None, None, None
        
    all_patterns_map = {p['pattern_id']: p for p in all_patterns_1d}
    
    # --- Generate PDF report ---
    # Create a unique filename for the PDF report.
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    sanitized_project_name = re.sub(r'[\\/*?:"<>|]', "", project_description)[:50]
    output_filename_base = f"1D-Cut-Plan_{sanitized_project_name}_{timestamp}"
    output_pdf_path = os.path.join(output_dir_base, f"{output_filename_base}.pdf")
    
    # Fix parameter order to match function signature in pdf_generator_1d.py
    export_solution_to_pdf_1d(
        output_pdf_path,  # filename
        solution_details_1d,  # solution_details
        all_patterns_map,  # all_patterns_dict_1d
        stock_data,  # stock_data_1d
        parts_data,  # parts_data_1d
        saw_kerf,  # saw_kerf_1d
        project_description  # project_description_1d
    )
    
    print(f"--- 1D Optimization Complete. Report at {output_pdf_path} ---")
    
    return solution_details_1d, output_pdf_path, all_patterns_map

# ... (The rest of the functions from optimizer_1d.py would go here)
# For brevity, I will add them in a subsequent step.
# The functions to add are:
# - solve_1d_cutting_problem
# - generate_all_patterns_1d
# - _generate_patterns_recursive_1d
# - _add_pattern_if_new_1d

def _add_pattern_if_new_1d(current_yield_dict, layout_details, generated_patterns, pattern_hashes, stock_id, stock_length, parts_data_map, saw_kerf):
    if not current_yield_dict:
        return
    yield_tuple = tuple(sorted(current_yield_dict.items()))
    if yield_tuple not in pattern_hashes:
        pattern_hashes.add(yield_tuple)
        total_length_of_parts_in_pattern = sum(parts_data_map[part_id]['length'] * count for part_id, count in current_yield_dict.items())
        num_kerfs_in_pattern = max(0, len(layout_details) - 1)
        temp_used_length = total_length_of_parts_in_pattern + (num_kerfs_in_pattern * saw_kerf)
        remaining_offcut = stock_length - temp_used_length
        if layout_details and remaining_offcut > 0.01:
            num_kerfs_in_pattern += 1
        total_kerf_length_in_pattern = num_kerfs_in_pattern * saw_kerf
        total_used_length_in_pattern = total_length_of_parts_in_pattern + total_kerf_length_in_pattern
        waste_length_in_pattern = stock_length - total_used_length_in_pattern
        pattern_id = f"{stock_id}_p1d{len(generated_patterns)}"
        generated_patterns.append({
            'pattern_id': pattern_id, 'stock_id_used': stock_id, 'yield': current_yield_dict.copy(),
            'layout_pieces': list(layout_details), 'total_parts_length_in_pattern': total_length_of_parts_in_pattern,
            'total_kerf_length_in_pattern': total_kerf_length_in_pattern, 'total_used_length_in_pattern': total_used_length_in_pattern,
            'waste_length_in_pattern': waste_length_in_pattern, 'num_cuts_in_pattern': num_kerfs_in_pattern
        })

def _generate_patterns_recursive_1d(stock_length, remaining_length, current_yield, current_layout, parts_to_try, generated_patterns, pattern_hashes, stock_id, parts_data_map, saw_kerf):
    if current_yield:
        _add_pattern_if_new_1d(current_yield, current_layout, generated_patterns, pattern_hashes, stock_id, stock_length, parts_data_map, saw_kerf)
    for i, part in enumerate(parts_to_try):
        part_id, part_length = part['name'], part['length']
        length_needed = part_length + (saw_kerf if current_layout else 0)
        if length_needed <= remaining_length:
            new_yield = current_yield.copy()
            new_yield[part_id] = new_yield.get(part_id, 0) + 1
            new_layout = current_layout.copy()
            new_layout.append({'part_id': part_id, 'length': part_length})
            _generate_patterns_recursive_1d(stock_length, remaining_length - length_needed, new_yield, new_layout, parts_to_try[i:], generated_patterns, pattern_hashes, stock_id, parts_data_map, saw_kerf)

def generate_all_patterns_1d(stock_data, parts_data, saw_kerf):
    all_patterns, parts_data_map = [], {part['name']: part for part in parts_data}
    sorted_parts = sorted(parts_data, key=lambda p: p['length'], reverse=True)
    for stock_id, stock_info in stock_data.items():
        stock_length = stock_info['length']
        generated_patterns_for_stock, pattern_hashes = [], set()
        _generate_patterns_recursive_1d(stock_length, stock_length, {}, [], sorted_parts, generated_patterns_for_stock, pattern_hashes, stock_id, parts_data_map, saw_kerf)
        all_patterns.extend(generated_patterns_for_stock)
    return all_patterns

def solve_1d_cutting_problem(all_patterns_1d, stock_data, parts_data, allow_overproduction=False):
    model = cp_model.CpModel()
    parts_data_map = {part['name']: part for part in parts_data}
    max_usage_heuristic = sum(p_info['demand'] for p_info in parts_data_map.values())
    num_times_pattern_used = [model.NewIntVar(0, min(max_usage_heuristic, stock_data[p['stock_id_used']].get('available', max_usage_heuristic)), f"p1d_{p['pattern_id']}") for p in all_patterns_1d]
    
    overproduction_vars = {}
    avg_cost_per_mm = sum(s['cost'] / s['length'] for s in stock_data.values() if s['length'] > 0) / len(stock_data) if stock_data and allow_overproduction else 0
    for part_info in parts_data:
        part_id = part_info['name']
        constraint_expr = sum(num_times_pattern_used[i] * p['yield'].get(part_id, 0) for i, p in enumerate(all_patterns_1d))
        if allow_overproduction:
            overproduction_vars[part_id] = model.NewIntVar(0, max_usage_heuristic * 10, f'over_{part_id}')
            model.Add(constraint_expr == part_info['demand'] + overproduction_vars[part_id])
        else:
            model.Add(constraint_expr == part_info['demand'])
            
    for stock_id, stock_info in stock_data.items():
        if 'available' in stock_info:
            model.Add(sum(num_times_pattern_used[i] for i, p in enumerate(all_patterns_1d) if p['stock_id_used'] == stock_id) <= stock_info['available'])
            
    total_cost_expr = sum(num_times_pattern_used[i] * stock_data[all_patterns_1d[i]['stock_id_used']]['cost'] for i in range(len(all_patterns_1d)))
    if allow_overproduction and avg_cost_per_mm > 0:
        overproduction_penalty = sum(overproduction_vars[p['name']] * p['length'] * avg_cost_per_mm for p in parts_data)
        waste_penalty = sum(num_times_pattern_used[i] * all_patterns_1d[i]['waste_length_in_pattern'] * avg_cost_per_mm for i in range(len(all_patterns_1d)))
        model.Minimize(total_cost_expr + overproduction_penalty + waste_penalty)
    else:
        model.Minimize(total_cost_expr)
        
    solver = cp_model.CpSolver()
    solver.parameters.log_search_progress = True
    solver.parameters.max_time_in_seconds = 60.0
    status = solver.Solve(model)

    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        solution = {'total_objective_value': solver.ObjectiveValue()}
        pattern_usage, stock_used, parts_prod = {}, {}, {}
        # ... logic to populate solution details ...
        true_stock_cost = sum(solver.Value(num_times_pattern_used[i]) * stock_data[all_patterns_1d[i]['stock_id_used']]['cost'] for i in range(len(all_patterns_1d)))
        solution_details_1d = {'total_objective_value': true_stock_cost}
        pattern_usage, total_stock_items_used_map, total_parts_produced_map = {}, {sid: 0 for sid in stock_data}, {pid['name']: 0 for pid in parts_data}
        # ... and so on for all the metrics ...
        
        # This part is complex, will just copy-paste and adapt
        total_length_all_parts_produced_mm, total_length_all_stock_used_mm, total_kerf_length_solution, total_waste_length_solution, total_number_of_cuts_solution, total_weight_all_stock_used_kg, total_weight_all_parts_produced_kg, total_weight_all_kerf_material_kg = 0,0,0,0,0,0,0,0
        total_weight_produced_per_part_map_kg = {part['name']: 0 for part in parts_data}

        for i, pattern in enumerate(all_patterns_1d):
            usage_count = solver.Value(num_times_pattern_used[i])
            if usage_count > 0:
                pattern_usage[pattern['pattern_id']] = usage_count
                stock_id = pattern['stock_id_used']
                stock_info = stock_data[stock_id]
                total_stock_items_used_map[stock_id] += usage_count
                total_length_all_stock_used_mm += stock_info['length'] * usage_count
                total_weight_all_stock_used_kg += stock_info.get('weight', 0) * usage_count
                kerf_len = pattern.get('total_kerf_length_in_pattern', 0)
                total_kerf_length_solution += kerf_len * usage_count
                stock_weight_per_mm = (stock_info['weight'] / stock_info['length']) if stock_info.get('length', 0) > 0 and stock_info.get('weight', 0) > 0 else 0
                total_weight_all_kerf_material_kg += kerf_len * stock_weight_per_mm * usage_count
                total_length_all_parts_produced_mm += pattern.get('total_parts_length_in_pattern', 0) * usage_count
                total_waste_length_solution += pattern.get('waste_length_in_pattern', 0) * usage_count
                total_number_of_cuts_solution += pattern.get('num_cuts_in_pattern', 0) * usage_count
                for part_id, yielded_count in pattern['yield'].items():
                    total_parts_produced_map[part_id] += yielded_count * usage_count
                    part_len = parts_data_map[part_id]['length']
                    part_weight = part_len * stock_weight_per_mm
                    total_weight_produced_per_part_map_kg[part_id] += part_weight * yielded_count * usage_count
                    total_weight_all_parts_produced_kg += part_weight * yielded_count * usage_count

        solution_details_1d.update({
            'pattern_usage': pattern_usage,
            'total_stock_items_used': total_stock_items_used_map,
            'total_parts_produced': total_parts_produced_map,
            'total_stock_cost': true_stock_cost,
            'total_length_all_stock_used_mm': total_length_all_stock_used_mm,
            'total_weight_all_stock_used_kg': total_weight_all_stock_used_kg,
            'total_length_all_parts_produced_mm': total_length_all_parts_produced_mm,
            'total_weight_all_parts_produced_kg': total_weight_all_parts_produced_kg,
            'total_kerf_length_mm': total_kerf_length_solution,
            'total_waste_length_mm': total_waste_length_solution,
            'total_weight_kerf_kg': total_weight_all_kerf_material_kg,
            'total_weight_waste_kg': total_weight_all_stock_used_kg - total_weight_all_parts_produced_kg - total_weight_all_kerf_material_kg,
            'total_number_of_cuts': total_number_of_cuts_solution,
            'weight_produced_per_part_kg': total_weight_produced_per_part_map_kg
        })
        return solution_details_1d
    return None 