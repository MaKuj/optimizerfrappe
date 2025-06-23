// sales_order_optimizer_client.js
// This script adds a button to the Sales Order doctype to run the 1D optimizer.
console.log("Optimizer script for Sales Order loaded!");

// =================================================================================================
// 1. ATTACH BUTTON TO SALES ORDER FORM
// =================================================================================================
frappe.ui.form.on('Sales Order', {
	refresh: function(frm) {
		console.log("Inside Sales Order refresh event.");
		
		// Button should be available on new or draft documents.
		if (frm.doc.docstatus > 0 && !frm.is_dirty()) { 
			console.log("Condition met: docstatus is not 0. Button will not be shown.");
            return;
        }
		
		console.log("Attempting to add optimizer button.");
        frm.add_custom_button(__('1D Cut Optimizer'), function() {
            // If the document is new or has been modified, it needs a customer to be valid.
            // The logic now populates the SO, so we don't need to save first.
            show_master_optimizer_dialog(frm);
        }, __("Create"));
		console.log("Button should have been added to the 'Create' menu.");
	}
});


// =================================================================================================
// 2. STATE MANAGEMENT & CONFIGURATION
// =================================================================================================

/**
 * Creates a fresh, empty configuration object.
 */
function get_initial_config() {
    return {
        version: "2.0",
        profiles: {}, // Keyed by item_code. Stores parts lists and settings for each profile.
        settings: {
            saw_kerf: 3.0, // Global setting for saw kerf.
            allow_overproduction: 0
        },
        results: {} // To store the output from the optimizer.
    };
}

/**
 * Reads the configuration from the form's custom field.
 * If the field is empty or invalid, it returns a fresh config object.
 * @param {object} frm - The Sales Order form object.
 * @returns {object} The optimizer configuration object.
 */
function load_config_from_form(frm) {
    let config;
    try {
        config = JSON.parse(frm.doc.custom_optimizer_output);
        if (!config || config.version !== "2.0" || !config.profiles) {
            throw "Invalid config format or version.";
        }
    } catch (e) {
        config = get_initial_config();
    }
    return config;
}

/**
 * Saves the configuration object back to the form's custom field as a JSON string.
 * @param {object} frm - The Sales Order form object.
 * @param {object} config - The optimizer configuration object.
 */
function save_config_to_form(frm, config) {
    frm.set_value('custom_optimizer_output', JSON.stringify(config, null, 2));
}

/**
 * Synchronizes the configuration with the items currently in the Sales Order grid.
 * - Adds new profiles for items that are in the SO but not in the config.
 * - Removes profiles from the config if they are no longer in the SO.
 * @param {object} frm - The Sales Order form object.
 * @param {object} config - The optimizer configuration object.
 */
async function sync_config_with_so_items(frm, config) {
    const so_item_codes = new Set(frm.doc.items.map(item => item.item_code).filter(Boolean));

    for (const item_code of so_item_codes) {
        if (!config.profiles[item_code]) {
            try {
                const item_doc = await frappe.db.get_doc('Item', item_code);
                let length_in_meters = 0;
                
                if (item_doc.uoms && item_doc.uoms.length) {
                    const ks_uom_entry = item_doc.uoms.find(uom => uom.uom === 'ks');
                    if (ks_uom_entry) {
                        length_in_meters = ks_uom_entry.conversion_factor;
                    }
                }

                config.profiles[item_code] = {
                    item_code: item_code,
                    stock_length_mm: length_in_meters > 0 ? length_in_meters * 1000 : 6000,
                    cost_per_meter: item_doc.valuation_rate || 0,
                    weight_per_meter: item_doc.weight_per_unit || 0,
                    cost_per_piece: (item_doc.valuation_rate || 0) * (length_in_meters || 1),
                    weight_per_piece: (item_doc.weight_per_unit || 0) * (length_in_meters || 1),
                    parts: [],
                    solution: {}
                };
            } catch (e) {
                console.error("Failed to fetch item details for", item_code, e);
            }
        }
    }

    for (const item_code in config.profiles) {
        if (!so_item_codes.has(item_code)) {
            delete config.profiles[item_code];
        }
    }
}


// =================================================================================================
// 3. MASTER DIALOG (Profile List)
// =================================================================================================

/**
 * The main entry point. Shows the master dialog listing all unique profiles from the SO.
 * @param {object} frm - The Sales Order form object.
 */
async function show_master_optimizer_dialog(frm) {
    const config = load_config_from_form(frm);
    await sync_config_with_so_items(frm, config);

    const dialog = new frappe.ui.Dialog({
        title: __('Optimizer Configuration'),
        fields: [
            {
                label: 'Saw Kerf (mm)',
                fieldname: 'saw_kerf',
                fieldtype: 'Float',
                default: config.settings.saw_kerf,
                reqd: 1,
                onchange: () => config.settings.saw_kerf = dialog.get_value('saw_kerf')
            },
            {
                label: 'Allow Overproduction',
                fieldname: 'allow_overproduction',
                fieldtype: 'Check',
                default: config.settings.allow_overproduction || 0,
                description: 'If checked, the optimizer can produce more parts than demanded to minimize waste.',
                onchange: () => config.settings.allow_overproduction = dialog.get_value('allow_overproduction')
            },
            {
                fieldtype: 'Section Break',
                label: __('Profiles to Optimize')
            },
            {
                fieldname: 'profiles_html',
                fieldtype: 'HTML'
            }
        ],
        primary_action_label: __('Run Optimization & Update SO'),
        primary_action: () => {
            save_config_to_form(frm, config);
            run_full_optimization(frm, config);
            dialog.hide();
        },
        secondary_action_label: __('Save Configuration Only'),
        secondary_action: () => {
            save_config_to_form(frm, config);
            dialog.hide();
            frappe.show_alert({ message: 'Configuration saved.', indicator: 'green' });
        },
        size: 'large'
    });

    render_profiles_html(dialog, frm, config);
    dialog.show();
}

/**
 * Renders the list of profiles inside the master dialog.
 * @param {object} dialog - The master dialog instance.
 * @param {object} frm - The Sales Order form object.
 * @param {object} config - The optimizer configuration object.
 */
function render_profiles_html(dialog, frm, config) {
    const wrapper = dialog.get_field('profiles_html').$wrapper;
    wrapper.empty();

    const table_html = `
        <table class="table table-bordered">
            <thead>
                <tr>
                    <th>Profile Item Code</th>
                    <th>Summary</th>
                    <th style="width: 120px;">Actions</th>
                </tr>
            </thead>
            <tbody>
                ${Object.keys(config.profiles).map(item_code => {
                    const profile = config.profiles[item_code];
                    const total_parts = profile.parts.reduce((sum, part) => sum + part.demand, 0);
                    const summary = total_parts > 0 
                        ? `${profile.parts.length} part types, ${total_parts} total pieces.`
                        : `<span class="text-muted">No parts defined.</span>`;

                    return `
                        <tr>
                            <td><strong>${profile.item_code}</strong></td>
                            <td>${summary}</td>
                            <td>
                                <button class="btn btn-xs btn-default btn-define-cuts" data-item-code="${item_code}">
                                    <i class="fa fa-list"></i> Define Cuts
                                </button>
                            </td>
                        </tr>
                    `;
                }).join('')}
            </tbody>
        </table>
    `;
    wrapper.html(table_html);

    // Attach event listeners for the "Define Cuts" buttons.
    wrapper.find('.btn-define-cuts').on('click', function() {
        const item_code = $(this).data('item-code');
        show_parts_entry_dialog(config.profiles[item_code], () => {
            render_profiles_html(dialog, frm, config); // Re-render to update summary.
        });
    });
}


// =================================================================================================
// 4. DETAIL DIALOG (Parts Entry)
// =================================================================================================

/**
 * Shows the detail dialog for defining the parts to be cut from a single profile.
 * @param {object} profile_config - The specific profile object from the main config.
 * @param {function} on_save_callback - A function to call after parts are confirmed, to refresh the master view.
 */
function show_parts_entry_dialog(profile_config, on_save_callback) {
    const parts_dialog = new frappe.ui.Dialog({
        title: `Define Cuts for: ${profile_config.item_code}`,
        fields: [
            {
                label: 'Stock Length (mm)',
                fieldname: 'stock_length_mm',
                fieldtype: 'Float',
                default: profile_config.stock_length_mm || 6000,
                reqd: 1,
                description: "The length of a single raw material bar for this profile."
            },
            {
                fieldname: 'parts_table',
                fieldtype: 'Table',
                label: 'Parts to Cut',
                fields: [
                    { label: 'Length (mm)', fieldname: 'length', fieldtype: 'Float', in_list_view: 1, reqd: 1 },
                    { label: 'Required Qty', fieldname: 'demand', fieldtype: 'Int', in_list_view: 1, reqd: 1 }
                ],
                data: profile_config.parts || []
            }
        ],
        primary_action_label: __('Confirm Parts'),
        primary_action: (values) => {
            profile_config.stock_length_mm = values.stock_length_mm;
            profile_config.parts = values.parts_table || []; // Ensure it's an array
            parts_dialog.hide();
            on_save_callback();
        }
    });
    parts_dialog.show();
}


// =================================================================================================
// 5. BACKEND COMMUNICATION
// =================================================================================================

/**
 * Sends the entire configuration to the backend to run the full optimization process.
 * Handles the async job polling and result display.
 * @param {object} frm - The Sales Order form object.
 * @param {object} config - The optimizer configuration object.
 */
function run_full_optimization(frm, config) {
    frappe.call({
        method: 'example_app.erpnextcutting_optimizer.api.enqueue_full_optimization',
        args: {
            sales_order_name: frm.doc.name,
            config: config
        },
        callback: function(r) {
            if (r.message && r.message.job_id) {
                const job_id = r.message.job_id;
                frappe.show_alert(`Optimization job <strong>${job_id}</strong> started.`);
                
                // Start polling for the job status.
                poll_for_job_completion(job_id, (result) => {
                    frappe.show_alert({
                        message: `Optimization for ${frm.doc.name} complete. The required quantities have been updated.`,
                        indicator: 'green'
                    }, 10);
                    frm.reload_doc(); // Refresh the SO to show new quantities and attachments.
                });
            } else {
                frappe.msgprint({
                    title: __('Error'),
                    indicator: 'red',
                    message: __('Failed to start optimization job. Please check the Error Log.')
                });
            }
        }
    });
}

/**
 * Polls the backend every few seconds to check the status of the background job.
 * @param {string} job_id - The ID of the job to poll.
 * @param {function} on_complete_callback - Function to execute when the job is finished successfully.
 */
function poll_for_job_completion(job_id, on_complete_callback) {
    const poll_interval = 4000; // 4 seconds

    const poller = setInterval(() => {
        frappe.call({
            method: 'example_app.erpnextcutting_optimizer.api.get_job_result',
            args: {
                job_id: job_id
            },
            callback: (r) => {
                if (r.message) {
                    const job = r.message;
                    if (job.status === 'finished') {
                        clearInterval(poller);
                        on_complete_callback(job.output);

                    } else if (job.status === 'failed') {
                        clearInterval(poller);
                        console.error("Job Failed:", job.error);
                        frappe.msgprint({
                            title: __('Optimization Failed'),
                            indicator: 'red',
                            message: `Job ${job_id} failed. Please check the Error Log for details.`
                        });
                    }
                    // If status is 'queued' or 'started', do nothing and wait for the next poll.
                }
            }
        });
    }, poll_interval);
}