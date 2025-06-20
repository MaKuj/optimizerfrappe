// sales_order_optimizer_client.js
// This script adds a button to the Sales Order doctype to run the 1D optimizer.
console.log("Optimizer script for Sales Order loaded!");
// frappe.msgprint("Optimizer Script Loaded!"); // This is a temporary debug message. Removing it now.

frappe.ui.form.on('Sales Order', {
	refresh: function(frm) {
		console.log("Inside Sales Order refresh event.");
		console.log("Current document status (frm.doc.docstatus):", frm.doc.docstatus);
		
		// Only show the button on Draft (0) and Submitted (1) documents.
		if (frm.doc.docstatus > 1) { // 2 is Cancelled
			console.log("Condition met: docstatus is Cancelled. Button will not be shown.");
            return;
        }
		
		console.log("Condition passed: docstatus is 0 or 1. Attempting to add button now.");
        frm.add_custom_button(__('1D Cut Optimizer'), function() {
			// When button is clicked, open the dialog
            show_optimizer_dialog(frm);
        }, __("Create"));
		console.log("Button should have been added to the 'Create' menu.");
	}
});

function show_optimizer_dialog(frm) {
    let stock_items = [];
    let part_items = [];

    // Heuristic to separate stock from parts from the Sales Order items table
    frm.doc.items.forEach(item => {
        // A simple heuristic: items with 'bar' or 'stock' in their name are stock.
        // You might need a more robust way to distinguish them, like a custom field.
        if (item.item_code.toLowerCase().includes('bar') || item.item_code.toLowerCase().includes('stock')) {
            stock_items.push({
                name: item.item_code,
                length: item.custom_length || 0, // Assuming a custom field 'custom_length'
                available: 9999, // Assuming infinite for now
                cost: item.rate || 0,
                weight: item.weight_per_unit || 0 // Added weight field
            });
        } else {
            part_items.push({
                name: item.item_code,
                length: item.custom_length || 0, // Assuming a custom field 'custom_length'
                demand: item.qty || 0,
                weight: item.weight_per_unit || 0 // Added weight field
            });
        }
    });


    const dialog = new frappe.ui.Dialog({
        title: __('1D Cutting Optimizer'),
        fields: [
            {
                fieldname: 'settings_section',
                fieldtype: 'Section Break',
                label: __('Optimization Settings')
            },
            {
                label: 'Project Name / Description',
                fieldname: 'project_description',
                fieldtype: 'Data',
                default: frm.doc.title || frm.doc.name,
                reqd: 1
            },
            {
                label: 'Saw Kerf (mm)',
                fieldname: 'saw_kerf',
                fieldtype: 'Float',
                default: 3,
                reqd: 1,
                description: 'The thickness of the saw blade.'
            },
            {
                label: 'Allow Overproduction',
                fieldname: 'allow_overproduction',
                fieldtype: 'Check',
                default: 0,
                description: 'Allow producing more parts than demanded if it reduces total stock usage.'
            },
            {
                fieldname: 'parts_section',
                fieldtype: 'Section Break',
                label: __('Parts to Cut (pre-filled from SO)')
            },
            {
                fieldname: 'parts_html',
                fieldtype: 'HTML'
            },
            {
                fieldname: 'stock_section',
                fieldtype: 'Section Break',
                label: __('Stock Material')
            },
            {
                fieldname: 'stock_html',
                fieldtype: 'HTML'
            }
        ],
        primary_action_label: __('Run Optimization'),
        primary_action(values) {
            run_optimization(frm, values);
            dialog.hide();
        },
        // Set a wider size for better visibility
        size: 'large'
    });

    const parts_html = `
        <div class="table-responsive">
            <table class="table table-bordered table-striped" id="parts_table">
                <thead>
                    <tr>
                        <th>Part Code</th>
                        <th>Length (mm)</th>
                        <th>Required Qty</th>
                        <th>Weight (kg/m)</th>
                        <th></th>
                    </tr>
                </thead>
                <tbody></tbody>
            </table>
        </div>
        <div class="mt-3">
            <button id="btn-add-part" class="btn btn-sm btn-default">
                <i class="fa fa-plus"></i> Add Part
            </button>
        </div>
    `;
    dialog.get_field('parts_html').$wrapper.html(parts_html);

    const stock_html = `
        <div class="table-responsive">
            <table class="table table-bordered table-striped" id="stock_table">
                <thead>
                    <tr>
                        <th>Stock Code</th>
                        <th>Length (mm)</th>
                        <th>Available Qty</th>
                        <th>Cost</th>
                        <th>Weight (kg/m)</th>
                        <th></th>
                    </tr>
                </thead>
                <tbody></tbody>
            </table>
        </div>
        <div class="mt-3">
            <button id="btn-add-stock" class="btn btn-sm btn-default">
                <i class="fa fa-plus"></i> Add Stock
            </button>
        </div>
    `;
    dialog.get_field('stock_html').$wrapper.html(stock_html);

    // Bind events correctly using jQuery
    dialog.$wrapper.find('#btn-add-part').on('click', () => {
        add_part_row(dialog, {});
    });
    dialog.$wrapper.find('#btn-add-stock').on('click', () => {
        add_stock_row(dialog, {});
    });

    // Pre-fill dialog tables
    part_items.forEach(item => add_part_row(dialog, item));
    stock_items.forEach(item => add_stock_row(dialog, item));

    // Add responsive CSS
    dialog.$wrapper.find('head').append(`
        <style>
            @media (max-width: 767px) {
                .modal-dialog {
                    width: 95% !important;
                    margin: 10px auto !important;
                }
                .table-responsive {
                    border: none;
                    margin-bottom: 0;
                }
                #parts_table input, #stock_table input {
                    min-width: 60px;
                }
                .form-control {
                    font-size: 14px;
                    height: 32px;
                    padding: 5px;
                }
            }
        </style>
    `);

    dialog.show();
}

function add_stock_row(dialog, defaults = {}) {
    const row = $(`
        <tr>
            <td><input type="text" class="form-control" data-key="name" value="${defaults.name || ''}"></td>
            <td><input type="number" class="form-control" data-key="length" value="${defaults.length || ''}"></td>
            <td><input type="number" class="form-control" data-key="available" value="${defaults.available || '9999'}"></td>
            <td><input type="number" step="0.01" class="form-control" data-key="cost" value="${defaults.cost || '0'}"></td>
            <td><input type="number" step="0.001" class="form-control" data-key="weight" value="${defaults.weight || '0'}"></td>
            <td><button class="btn btn-danger btn-xs" onclick="$(this).closest('tr').remove()"><i class="fa fa-trash"></i></button></td>
        </tr>
    `).appendTo(dialog.get_field('stock_html').$wrapper.find('tbody'));
}

function add_part_row(dialog, defaults = {}) {
    const row = $(`
        <tr>
            <td><input type="text" class="form-control" data-key="name" value="${defaults.name || ''}"></td>
            <td><input type="number" class="form-control" data-key="length" value="${defaults.length || ''}"></td>
            <td><input type="number" class="form-control" data-key="demand" value="${defaults.demand || ''}"></td>
            <td><input type="number" step="0.001" class="form-control" data-key="weight" value="${defaults.weight || '0'}"></td>
            <td><button class="btn btn-danger btn-xs" onclick="$(this).closest('tr').remove()"><i class="fa fa-trash"></i></button></td>
        </tr>
    `).appendTo(dialog.get_field('parts_html').$wrapper.find('tbody'));
}

function run_optimization(frm, dialog_values) {
    frappe.show_alert({ message: 'Collecting data from dialog...', indicator: 'blue' });

    const $dialog_wrapper = $(".modal.show").last();

    const stock_data = {};
    $dialog_wrapper.find('#stock_table tbody tr').each(function() {
        const row = $(this);
        const name = row.find('input[data-key="name"]').val();
        if (name) {
            stock_data[name] = {
                length: parseFloat(row.find('input[data-key="length"]').val() || 0),
                cost: parseFloat(row.find('input[data-key="cost"]').val() || 0),
                available: parseInt(row.find('input[data-key="available"]').val() || 0),
                weight: parseFloat(row.find('input[data-key="weight"]').val() || 0),
            };
        }
    });

    const parts_data = {};
    $dialog_wrapper.find('#parts_table tbody tr').each(function() {
        const row = $(this);
        const name = row.find('input[data-key="name"]').val();
        if (name) {
            parts_data[name] = {
                length: parseFloat(row.find('input[data-key="length"]').val() || 0),
                demand: parseInt(row.find('input[data-key="demand"]').val() || 0),
                weight: parseFloat(row.find('input[data-key="weight"]').val() || 0),
            };
        }
    });
    
    if (Object.keys(stock_data).length === 0 || Object.keys(parts_data).length === 0) {
        frappe.throw(__("Please enter at least one stock item and one part to cut."));
    }
    
    // This is the complete data payload needed by the background job.
    const request_data = {
        stock_data: stock_data,
        parts_data: parts_data,
        saw_kerf: dialog_values.saw_kerf,
        project_description: dialog_values.project_description,
        // We no longer need attach_to_doctype/docname here, as it's passed separately
        allow_overproduction: dialog_values.allow_overproduction == 1,
    };

    // Show a loading indicator
    frappe.show_alert({
        message: __('Starting optimization job. This may take a few minutes...'),
        indicator: 'blue'
    });

    // Call the whitelisted method to start the background job
    frappe.call({
        method: "example_app.erpnextcutting_optimizer.api.enqueue_optimization_job",
        args: {
            doctype: frm.doc.doctype,
            docname: frm.doc.name,
            request_data_json: JSON.stringify(request_data)
        },
        callback: function(r) {
            // The success message is now handled on the server, which will
            // send a realtime notification. No need to do anything here.
            if (r.exc) {
                // If the enqueue call itself fails, show an error.
                frappe.msgprint({
                    title: __('Error Starting Job'),
                    indicator: 'red',
                    message: __('Could not start the optimization background job. Please check the Error Log.')
                });
            }
        }
    });
} 