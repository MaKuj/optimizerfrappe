import frappe
import json
import os
from frappe.utils.pdf import get_pdf
from frappe import _
from ortools.sat.python import cp_model
from datetime import datetime
import re
import copy
from .optimizer_core import run_1d_optimizer
from .pdf_generator_1d import OneDCuttingPDFGenerator

# ==============================================================================
# 1. ENQUEUEING METHOD (WHITELISTED)
# ==============================================================================

@frappe.whitelist()
def get_job_result(job_id):
	"""
	Polls the RQ Job for the result of a background job.
	This is a whitelisted method to securely get the job result from the client.
	"""
	try:
		# The correct doctype for background jobs is "RQ Job"
		job = frappe.get_doc("RQ Job", job_id)
		
		# We need to access the underlying RQ Job object to get the result.
		# The .job property was added in the load_from_db method of the RQJob class
		rq_job_instance = job.job 
		job_output = rq_job_instance.result

		if job.status == "finished" and job_output:
			try:
				if isinstance(job_output, str):
					job_output = json.loads(job_output)
			except (json.JSONDecodeError, TypeError):
				pass

		return {
			"status": job.status,
			"output": job_output,
			"error": job.exc_info
		}
	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "Error in get_job_result")
		return {"status": "error", "error": str(e)}

@frappe.whitelist()
def enqueue_full_optimization(sales_order_name, config):
    """
    Receives the entire optimization configuration from the client and enqueues
    the main background job.
    """
    if not sales_order_name or not config:
        return {"error": "Missing sales_order_name or config."}

    # The config might come in as a string, ensure it's a dict
    if isinstance(config, str):
        config = json.loads(config)

    job = frappe.enqueue(
        "example_app.erpnextcutting_optimizer.api.run_full_optimization_job",
        queue='long',
        timeout=1500,
        sales_order_name=sales_order_name,
        config=config,
        user=frappe.session.user
    )
    return {"job_id": job.id}

# ==============================================================================
# 2. BACKGROUND JOB
# ==============================================================================

def run_full_optimization_job(sales_order_name, config, user):
    """
    This function runs in the background. It iterates through each profile,
    runs optimization, and generates a SEPARATE PDF report for each.
    Finally, it updates the Sales Order quantities.
    """
    try:
        job_id = frappe.local.job.name
        frappe.publish_realtime("update_job_status", {"job_id": job_id, "status": "running", "progress": 10, "message": "Starting job..."})

        has_errors = False
        profiles_to_run = config.get("profiles", {})
        total_profiles = len(profiles_to_run)
        updated_quantities = {}
        total_cuts = 0

        # --- Main Loop: Optimize and Generate PDF for each profile ---
        for i, item_code in enumerate(profiles_to_run):
            profile_config = profiles_to_run[item_code]
            progress = 20 + int((i / total_profiles) * 70)
            frappe.publish_realtime("update_job_status", {"job_id": job_id, "status": "running", "progress": progress, "message": f"Optimizing {item_code}"})

            stock_data = {item_code: {"length": profile_config["stock_length_mm"]}}
            parts_data = profile_config["parts"]
            saw_kerf = config.get("settings", {}).get("saw_kerf", 1)
            allow_overproduction = config.get("settings", {}).get("allow_overproduction", False)

            solution = run_1d_optimizer(stock_data, parts_data, saw_kerf, allow_overproduction=allow_overproduction)

            if solution:
                _generate_and_attach_profile_pdf(sales_order_name, item_code, profile_config, solution, saw_kerf)

                # Store the solution back into the config object for this profile
                profile_config['solution'] = solution
                
                # Sum up the total number of cuts from the current solution
                profile_cuts = 0
                for pattern in solution.get("patterns", []):
                    profile_cuts += pattern.get('num_cuts_in_pattern', 0) * pattern.get('usage_count', 1)
                total_cuts += profile_cuts
                
                # Calculate total length in meters and store for SO update
                stock_length_mm = profile_config.get("stock_length_mm", 0)
                qty_needed_in_pieces = solution.get("total_stock_items_used", {}).get(item_code, 0)
                total_length_in_meters = (qty_needed_in_pieces * stock_length_mm) / 1000.0
                updated_quantities[item_code] = total_length_in_meters
                
            else:
                has_errors = True
                frappe.log_error(f"No feasible solution found for profile {item_code}.", "Optimizer Job Warning")

        if has_errors:
             frappe.log_error("One or more profiles failed to optimize.", "Optimizer Job Warning")

        # --- Final Step: Update Sales Order item quantities ---
        frappe.publish_realtime("update_job_status", {"job_id": job_id, "status": "running", "progress": 90, "message": "Updating Sales Order..."})
        if updated_quantities or total_cuts > 0:
            _update_sales_order_items(sales_order_name, updated_quantities, config, total_cuts=total_cuts)

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Full Optimization Job Failed")
        frappe.publish_realtime("update_job_status", {"job_id": job_id, "status": "failed", "error": str(e)})
        return

    result = {"message": "Optimization complete."}
    frappe.publish_realtime("update_job_status", {"job_id": job_id, "status": "complete", "result": result})


def _update_sales_order_items(doc_name, quantities_map, final_config=None, total_cuts=0):
    """Updates the quantities of specified items in a Sales Order."""
    so_doc = frappe.get_doc("Sales Order", doc_name)
    updated = False
    op_cut_item_found = False
    for item in so_doc.items:
        if item.item_code in quantities_map:
            new_qty = quantities_map[item.item_code]
            if item.qty != new_qty:
                item.qty = new_qty
                updated = True
        
        if item.item_code == "OP-CUT":
            op_cut_item_found = True
            if item.qty != total_cuts:
                item.qty = total_cuts
                updated = True
    
    # If OP-CUT item doesn't exist and there are cuts, add it as a new line.
    # Note: The item 'OP-CUT' must exist in the system as a non-stock item.
    if not op_cut_item_found and total_cuts > 0:
        so_doc.append("items", {
            "item_code": "OP-CUT",
            "qty": total_cuts,
            "rate": 0,
            "uom": "ks"
        })
        updated = True

    if final_config:
        try:
            config_json = json.dumps(final_config, indent=2, sort_keys=True, default=str)
            so_doc.custom_optimizer_output = config_json
            updated = True
        except Exception as e:
            frappe.log_error(f"Failed to serialize solution data for Optimizer Output: {e}", "Optimizer JSON Error")

    if updated:
        so_doc.save(ignore_permissions=True)
        frappe.db.commit()


def _generate_and_attach_profile_pdf(doc_name, item_code, profile_config, solution, saw_kerf):
    """
    Generates and attaches a PDF report for a single profile's optimization solution.
    """
    prepared_data = _prepare_single_profile_for_pdf(solution, profile_config, item_code)

    pdf_gen = OneDCuttingPDFGenerator(
        stock_data=prepared_data["stock_data"],
        parts_data=prepared_data["parts_data"],
        all_patterns_dict=prepared_data["patterns"],
        solution_details_list=[prepared_data["solution_details"]],
        parts_production_summary_list=prepared_data["production_summary"],
        saw_kerf=saw_kerf
    )
    
    pdf_buffer = pdf_gen.generate_pdf()
    pdf_buffer.seek(0)
    
    file_name = f"Optimizer_Report_{item_code}.pdf"
    _attach_pdf_to_document(pdf_buffer, doc_name, file_name)


def _prepare_single_profile_for_pdf(solution, profile_config, item_code):
    """
    Takes the solution for a single profile and calculates the rich, 
    detailed statistics required by the PDF generator.
    """
    saw_kerf = profile_config.get("saw_kerf_mm", 1)
    
    # Use a deepcopy to prevent modifying the original solution object,
    # which could cause issues in subsequent loops.
    patterns_for_pdf = copy.deepcopy(solution.get("patterns", []))

    # The PDF generator needs a 'name' for each part. We'll create one from the length.
    parts_data_1d = [
        {'name': f"part_{p['length']}_{item_code[:4]}", 'length': p['length'], 'demand': p['demand']}
        for p in profile_config.get("parts", [])
    ]
    parts_map_len_to_name = {f"{p['length']}": p['name'] for p in parts_data_1d}
    parts_map_name_to_info = {p['name']: p for p in parts_data_1d}

    # Remap layout_pieces to use the generated part name for PDF rendering
    for pattern in patterns_for_pdf:
        for piece in pattern.get("layout_pieces", []):
            piece["part_id"] = parts_map_len_to_name.get(str(piece["part_id"]), "?")

    stock_data_1d = {
        item_code: {
            "length": profile_config.get("stock_length_mm", 6000),
            "cost": profile_config.get("cost_per_piece", 0),
            "weight": profile_config.get("weight_per_piece", 0)
        }
    }
    
    stock_info = stock_data_1d[item_code]
    stock_weight_per_mm = (stock_info.get('weight', 0) / stock_info['length']) if stock_info.get('length', 0) > 0 else 0
    
    total_stock_items_used = solution.get('total_stock_items_used', {}).get(item_code, 0)
    
    stats = {
        'profile_id': item_code,
        'total_length_all_parts_produced_mm': 0, 'total_length_all_stock_used_mm': 0,
        'total_kerf_length_mm': 0, 'total_waste_length_mm': 0,
        'total_number_of_cuts': 0, 'total_weight_all_stock_used_kg': 0,
        'total_weight_all_parts_produced_kg': 0, 'total_weight_kerf_kg': 0,
        'weight_produced_per_part_kg': {p['name']: 0 for p in parts_data_1d}
    }

    used_patterns_from_solution = patterns_for_pdf
    for pattern in used_patterns_from_solution:
        usage_count = pattern.get('usage_count', 1)
        stats['total_length_all_stock_used_mm'] += stock_info['length'] * usage_count
        stats['total_weight_all_stock_used_kg'] += stock_info.get('weight', 0) * usage_count
        stats['total_kerf_length_mm'] += pattern.get('total_kerf_length_in_pattern', 0) * usage_count
        stats['total_waste_length_mm'] += pattern.get('waste_length_in_pattern', 0) * usage_count
        stats['total_number_of_cuts'] += pattern.get('num_cuts_in_pattern', 0) * usage_count
        stats['total_length_all_parts_produced_mm'] += pattern.get('total_parts_length_in_pattern', 0) * usage_count
        
        stats['total_weight_kerf_kg'] += pattern.get('total_kerf_length_in_pattern', 0) * stock_weight_per_mm * usage_count
        
        for part_name, part_info in parts_map_name_to_info.items():
            yield_count = pattern.get('yield', {}).get(f"{part_info['length']}", 0)
            if yield_count > 0:
                part_weight = part_info['length'] * stock_weight_per_mm
                stats['weight_produced_per_part_kg'][part_name] += part_weight * yield_count * usage_count
                stats['total_weight_all_parts_produced_kg'] += part_weight * yield_count * usage_count

    stats['total_weight_waste_kg'] = stats['total_weight_all_stock_used_kg'] - stats['total_weight_all_parts_produced_kg'] - stats['total_weight_kerf_kg']
    
    if stats['total_length_all_stock_used_mm'] > 0:
        stats['yield_percentage'] = (stats['total_length_all_parts_produced_mm'] / stats['total_length_all_stock_used_mm']) * 100
    else:
        stats['yield_percentage'] = 0

    solution_details_for_pdf = {
        'total_stock_items_used': solution.get('total_stock_items_used'),
        'total_parts_produced': solution.get('total_parts_produced'),
        'pattern_usage': {p['pattern_id']: p['usage_count'] for p in used_patterns_from_solution},
        'total_stock_cost': total_stock_items_used * stock_info.get('cost', 0),
        **stats
    }

    all_patterns_dict_1d = {p['pattern_id']: p for p in used_patterns_from_solution}

    # --- Create Parts Production Summary for this profile ---
    parts_production_summary = []
    total_parts_produced_map = solution.get("total_parts_produced", {})
    for part_info in parts_data_1d:
        part_name = part_info['name']
        demand = part_info['demand']
        produced = total_parts_produced_map.get(f"{part_info['length']}", 0)
        delta = produced - demand
        part_total_weight = stats['weight_produced_per_part_kg'].get(part_name, 0)
        
        parts_production_summary.append({
            'Part ID': part_name,
            'Length (mm)': part_info['length'],
            'Demand': demand,
            'Produced': produced,
            'Delta (+/-)': delta,
            'Total Wt (kg)': part_total_weight
        })
    
    return {
        "solution_details": solution_details_for_pdf,
        "patterns": all_patterns_dict_1d,
        "stock_data": stock_data_1d,
        "parts_data": parts_data_1d,
        "production_summary": parts_production_summary
    }


def _attach_pdf_to_document(pdf_buffer, doc_name, file_name):
    """Attaches a PDF from a buffer to a Frappe document."""
    file_doc = frappe.new_doc("File")
    file_doc.file_name = file_name
    file_doc.attached_to_doctype = "Sales Order"
    file_doc.attached_to_name = doc_name
    file_doc.content = pdf_buffer.getvalue()
    file_doc.is_private = 1
    file_doc.insert(ignore_permissions=True)

# =================================================================================================
# 4. CORE OPTIMIZER LOGIC (Placeholder - This should be in its own file)
# =================================================================================================

# The core optimizer functions (run_1d_optimizer, solve_1d_cutting_problem, etc.)
# have been moved to a separate file: optimizer_core.py for better organization. 