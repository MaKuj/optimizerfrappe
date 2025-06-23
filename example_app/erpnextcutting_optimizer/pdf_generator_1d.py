# example_app/erpnextcutting_optimizer/pdf_generator_1d.py

from reportlab.lib.pagesizes import A4, landscape, portrait
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
from reportlab.lib import colors
from datetime import datetime
import os
from reportlab.platypus import Paragraph
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
import io

class OneDCuttingPDFGenerator:
    def __init__(self, stock_data, parts_data, all_patterns_dict, solution_details_list, parts_production_summary_list, saw_kerf=1):
        self.buffer = io.BytesIO()
        self.stock_data = stock_data
        self.parts_data = parts_data
        self.all_patterns_dict = all_patterns_dict
        self.solution_details_list = solution_details_list
        self.parts_production_summary_list = parts_production_summary_list
        self.saw_kerf = saw_kerf
        
        self.width, self.height = portrait(A4)
        self.c = canvas.Canvas(self.buffer, pagesize=portrait(A4))
        self.styles = {
            'main_title': ('Helvetica-Bold', 14),
            'header': ('Helvetica-Bold', 11),
            'sub_header': ('Helvetica-Bold', 9),
            'body': ('Helvetica', 9),
            'body_small': ('Helvetica', 8),
            'body_bold_small': ('Helvetica-Bold', 8),
        }
        self.margins = {'left': 20 * mm, 'right': 20 * mm, 'top': 25 * mm, 'bottom': 20 * mm}
        self.line_height = 5.5 * mm

    def _set_font(self, style):
        font_name, size = self.styles[style]
        self.c.setFont(font_name, size)

    def generate_pdf(self):
        self._draw_header_footer()
        
        y_pos = self.height - self.margins['top']

        for solution_details in self.solution_details_list:
            profile_id = solution_details.get('profile_id', 'Unnamed Profile')
            y_pos = self._draw_profile_summary_section(y_pos, solution_details, profile_id)
            
            # Since the generator now handles one profile at a time in the loop,
            # we need to filter the production summary for the current profile.
            current_production_summary = [
                s for s in self.parts_production_summary_list 
                if s.get('Part ID', '').endswith(profile_id[:4])
            ]
            y_pos = self._draw_production_summary_table(y_pos, current_production_summary)
            y_pos -= self.line_height * 2

        self._draw_part_legend(y_pos)
        self._draw_all_patterns()

        self.c.save()
        self.buffer.seek(0)
        return self.buffer

    def _draw_header_footer(self):
        self.c.saveState()
        self._set_font('main_title')
        self.c.drawCentredString(self.width / 2, self.height - self.margins['top'] + 10*mm, "1D Cutting Optimizer Report")
        self._set_font('body_small')
        self.c.drawString(self.width - 50 * mm, self.height - 15 * mm, f"by MaKuj ❤ {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        self.c.restoreState()

    def _draw_profile_summary_section(self, y_pos, details, profile_id):
        self._set_font('header')
        self.c.drawString(self.margins['left'], y_pos, f"Summary for Profile: {profile_id}")
        y_pos -= self.line_height * 1.5
        
        summary_items = [
            ("Total Stock Cost:", f"{details.get('total_stock_cost', 0):.2f}"),
            ("Unique Patterns Used:", len(details.get('pattern_usage', {}))),
            ("Total Parts Length:", f"{details.get('total_length_all_parts_produced_mm', 0):.0f} mm"),
            ("Total Stock Used Length:", f"{details.get('total_length_all_stock_used_mm', 0):.0f} mm"),
            ("Total Parts Weight:", f"{details.get('total_weight_all_parts_produced_kg', 0):.2f} kg"),
            ("Total Stock Used Weight:", f"{details.get('total_weight_all_stock_used_kg', 0):.2f} kg"),
            ("Total Waste Length:", f"{details.get('total_waste_length_mm', 0):.0f} mm"),
            ("Total Kerf Length:", f"{details.get('total_kerf_length_mm', 0):.0f} mm"),
            ("Total Number of Cuts:", f"{details.get('total_number_of_cuts', 0)}"),
        ]

        self._set_font('body')
        for label, value in summary_items:
            self.c.drawString(self.margins['left'] + 5*mm, y_pos, label)
            self.c.drawRightString(self.width - self.margins['right'], y_pos, str(value))
            y_pos -= self.line_height

        y_pos -= self.line_height
        y_pos = self._draw_stock_consumption_table(y_pos, details)
        return y_pos

    def _draw_stock_consumption_table(self, y_pos, details):
        self._set_font('header')
        self.c.drawString(self.margins['left'], y_pos, "Stock Items Consumption")
        y_pos -= self.line_height * 1.5
        
        headers = ["Stock ID", "Length", "Cost", "Used Qty", "Total Cost", "Total Wt"]
        coords = [self.margins['left'] + x for x in [0, 130, 180, 240, 300, 360]]
        
        self._set_font('sub_header')
        for i, h in enumerate(headers):
            self.c.drawString(coords[i], y_pos, h)
        y_pos -= self.line_height
        
        self._set_font('body_small')
        stock_usage = details.get('total_stock_items_used', {})
        for stock_id, count in stock_usage.items():
            info = self.stock_data.get(stock_id, {})
            total_cost = count * info.get('cost', 0)
            total_weight = count * info.get('weight', 0)
            values = [
                stock_id, f"{info.get('length', 0)} mm", f"{info.get('cost', 0):.2f}",
                count, f"{total_cost:.2f}", f"{total_weight:.2f} kg"
            ]
            for i, v in enumerate(values):
                self.c.drawString(coords[i], y_pos, str(v))
            y_pos -= self.line_height
        return y_pos

    def _draw_production_summary_table(self, y_pos, summary_data):
        self._set_font('header')
        self.c.drawString(self.margins['left'], y_pos, "Parts Production Summary")
        y_pos -= self.line_height * 1.5

        headers = ["Part ID", "Length", "Demand", "Produced", "Delta", "Total Wt"]
        coords = [self.margins['left'] + x for x in [0, 130, 180, 240, 300, 360]]
        self._set_font('sub_header')
        for i, h in enumerate(headers):
            self.c.drawString(coords[i], y_pos, h)
        y_pos -= self.line_height

        self._set_font('body_small')
        for item in summary_data:
            values = [
                item['Part ID'], f"{item['Length (mm)']} mm", item['Demand'],
                item['Produced'], f"{item['Delta (+/-)']:+.0f}", f"{item['Total Wt (kg)']:.2f} kg"
            ]
            for i, v in enumerate(values):
                self.c.drawString(coords[i], y_pos, str(v))
            y_pos -= self.line_height
        return y_pos
        
    def _draw_part_legend(self, y_pos):
        # This part remains mostly the same, just using class variables
        part_colors = [
            colors.HexColor("#ADD8E6"), colors.HexColor("#90EE90"), colors.HexColor("#FFB6C1"),
            colors.HexColor("#E6E6FA"), colors.HexColor("#FFDEAD"), colors.HexColor("#AFEEEE"),
            colors.HexColor("#F0E68C"), colors.HexColor("#DDA0DD"), colors.HexColor("#ff9999"),
        ]
        part_meta_data = {
            part['name']: {
                'short_id': f"P{i+1}", 'color': part_colors[i % len(part_colors)],
                'length': part['length']
            } for i, part in enumerate(self.parts_data)
        }
        self.part_meta_data = part_meta_data # Save for use in pattern drawing
        
        self._set_font('header')
        self.c.drawString(self.margins['left'], y_pos, "Part Legend")
        y_pos -= self.line_height

        self._set_font('body_small')
        for part_id, meta in part_meta_data.items():
            self.c.setFillColor(meta['color'])
            self.c.rect(self.margins['left'] + 2*mm, y_pos - 1*mm, 4*mm, 4*mm, stroke=1, fill=1)
            self.c.setFillColor(colors.black)
            self.c.drawString(self.margins['left'] + 8*mm, y_pos, f"{meta['short_id']}: {part_id} ({meta['length']:.1f}mm)")
            y_pos -= self.line_height * 0.9
            if y_pos < self.margins['bottom']:
                self.c.showPage()
                y_pos = self.height - self.margins['top']
        return y_pos

    def _draw_all_patterns(self):
        self.c.showPage()
        self.c.setPageSize(landscape(A4))
        width, height = landscape(A4)
        
        max_patterns_per_page = 4
        y_start_offset = 30 * mm
        y_pos_pattern = height - y_start_offset
        
        for i, (pattern_id, pattern_details) in enumerate(self.all_patterns_dict.items()):
            if i > 0 and i % max_patterns_per_page == 0:
                self.c.showPage()
                self.c.setPageSize(landscape(A4))
                y_pos_pattern = height - y_start_offset

            self._draw_single_pattern(y_pos_pattern, pattern_id, pattern_details, width)
            y_pos_pattern -= (height - 40*mm) / max_patterns_per_page
            
    def _draw_single_pattern(self, y_pos, pattern_id, pattern_details, page_width):
        stock_id = pattern_details['stock_id_used']
        stock_info = self.stock_data.get(stock_id, {})
        stock_length = stock_info.get('length', 0)
        
        self._set_font('sub_header')
        usage = self.solution_details_list[0]['pattern_usage'].get(pattern_id, 1) # Simplified for now
        title = f"Pattern: {pattern_id} (used {usage} times on stock '{stock_id}')"
        self.c.drawString(self.margins['left'], y_pos, title)
        
        bar_y = y_pos - 25*mm
        bar_height = 15*mm
        
        if stock_length <= 0: return

        draw_scale = (page_width - self.margins['left'] * 2) / stock_length
        self.c.setFillColor(colors.lightgrey)
        self.c.rect(self.margins['left'], bar_y, stock_length * draw_scale, bar_height, stroke=1, fill=1)
        
        current_x_abs = self.margins['left']
        num_pieces = len(pattern_details.get('layout_pieces', []))
        for i, piece in enumerate(pattern_details.get('layout_pieces', [])):
            part_id = piece['part_id']
            part_length = piece['length']
            
            meta = self.part_meta_data.get(part_id, {})
            if meta:
                self.c.setFillColor(meta.get('color', colors.white))
                self.c.rect(current_x_abs, bar_y, part_length * draw_scale, bar_height, stroke=1, fill=1)
            
            self.c.setFillColor(colors.black)
            self._set_font('body_small')
            short_id = meta.get('short_id', '?')
            self.c.drawCentredString(current_x_abs + (part_length * draw_scale / 2), bar_y + 5*mm, f"{short_id}")
            
            # Conditionally draw the length label to prevent overlapping text
            length_label = f"({part_length:.1f}mm)"
            text_width = self.c.stringWidth(length_label, self.styles['body_small'][0], self.styles['body_small'][1])
            if text_width < (part_length * draw_scale):
                self.c.drawCentredString(current_x_abs + (part_length * draw_scale / 2), bar_y - 5*mm, length_label)
                
            current_x_abs += part_length * draw_scale
            
            # Draw kerf after the piece, but not for the last piece
            if i < num_pieces - 1:
                self.c.setFillColor(colors.red)
                self.c.rect(current_x_abs, bar_y, self.saw_kerf * draw_scale, bar_height, stroke=0, fill=1)
                current_x_abs += self.saw_kerf * draw_scale
        
        waste = pattern_details.get('waste_length_in_pattern', 0)
        if waste > 0:
            self.c.setFillColor(colors.black)
            # To draw a dashed line, you must set the dash on the canvas state
            self.c.setDash(1, 2)
            # A fill of 1 would obscure the text, so we use fill=0 for a transparent rectangle
            self.c.rect(current_x_abs, bar_y, waste * draw_scale, bar_height, stroke=1, fill=0)
            # Reset the dash to not affect other elements
            self.c.setDash([])
            self.c.drawCentredString(current_x_abs + (waste * draw_scale / 2), bar_y + bar_height/2, f"Waste: {waste:.1f}mm")


def export_solution_to_pdf_1d(filename, solution_details, all_patterns_dict_1d,
                              stock_data_1d, parts_data_1d, saw_kerf_1d, project_description_1d):
    """
    Exports the 1D cutting solution to a PDF file.
    """
    c = WatermarkedCanvas(filename, pagesize=portrait(A4))
    width_a4_portrait, height_a4_portrait = portrait(A4)

    c.setFont("Helvetica-Bold", 14)
    c.drawCentredString(width_a4_portrait / 2, height_a4_portrait - 20 * mm, "1D Cutting Optimizer Report")
    c.setFont("Helvetica", 8)
    c.drawString(width_a4_portrait - 50 * mm, height_a4_portrait - 15 * mm, f"by MaKuj ❤ {datetime.now().strftime('%Y-%m-%d %H:%M')}")

    y_pos = height_a4_portrait - 35 * mm
    line_height = 5.5 * mm
    left_margin = 20 * mm
    right_margin_val_x = width_a4_portrait - 25 * mm
    value_indent_x = 70 * mm

    c.setFont("Helvetica-Bold", 11)
    c.drawString(left_margin, y_pos, "Summary of Optimization (1D)")
    y_pos -= line_height * 1.5
    c.setFont("Helvetica", 9)
    
    # Use .get with a default for every value to prevent KeyErrors
    summary_items = [
        ("Project Description:", project_description_1d),
        ("Total Stock Cost:", f"{solution_details.get('total_stock_cost', 0):.2f}"),
        ("Unique Patterns Used:", len(solution_details.get('pattern_usage', {}))),
        ("Total Parts Length:", f"{solution_details.get('total_length_all_parts_produced_mm', 0):.0f} mm"),
        ("Total Stock Used Length:", f"{solution_details.get('total_length_all_stock_used_mm', 0):.0f} mm"),
        ("Total Parts Weight:", f"{solution_details.get('total_weight_all_parts_produced_kg', 0):.2f} kg"),
        ("Total Stock Used Weight:", f"{solution_details.get('total_weight_all_stock_used_kg', 0):.2f} kg"),
        ("Total Waste Length:", f"{solution_details.get('total_waste_length_mm', 0):.0f} mm"),
        ("Total Kerf Length:", f"{solution_details.get('total_kerf_length_mm', 0):.0f} mm"),
        ("Total Kerf Weight:", f"{solution_details.get('total_weight_kerf_kg', 0):.2f} kg"),
        ("Total Number of Cuts:", f"{solution_details.get('total_number_of_cuts', 0)}"),
    ]

    for label, value in summary_items:
        c.drawString(left_margin + 5*mm, y_pos, f"{label}")
        c.drawRightString(right_margin_val_x, y_pos, str(value))
        y_pos -= line_height
    
    y_pos -= line_height

    c.setFont("Helvetica-Bold", 11)
    c.drawString(left_margin, y_pos, "Stock Items Consumption")
    y_pos -= line_height * 1.5
    c.setFont("Helvetica-Bold", 9)
    c.drawString(left_margin + 5*mm, y_pos, "Stock ID")
    c.drawString(left_margin + 50*mm, y_pos, "Length (mm)")
    c.drawString(left_margin + 85*mm, y_pos, "Cost/Item")
    c.drawString(left_margin + 115*mm, y_pos, "Used Qty")
    c.drawString(left_margin + 140*mm, y_pos, "Total Cost")
    c.drawString(left_margin + 165*mm, y_pos, "Total Wt (kg)")
    y_pos -= line_height
    c.setFont("Helvetica", 8)

    total_cost_from_stock = 0
    total_weight_from_stock_kg = 0
    stock_usage_counts = solution_details.get('total_stock_items_used', {})
    if not stock_usage_counts:
        c.drawString(left_margin + 5*mm, y_pos, "No stock items were consumed in this solution.")
        y_pos -= line_height
    else:
        for stock_id, count_used in stock_usage_counts.items():
            if count_used > 0:
                stock_info = stock_data_1d.get(stock_id)
                if stock_info:
                    item_total_cost = count_used * stock_info.get('cost', 0)
                    item_total_weight_kg = count_used * stock_info.get('weight', 0)
                    total_cost_from_stock += item_total_cost
                    total_weight_from_stock_kg += item_total_weight_kg
                    c.drawString(left_margin + 5*mm, y_pos, str(stock_id))
                    c.drawString(left_margin + 50*mm, y_pos, str(stock_info['length']))
                    c.drawString(left_margin + 85*mm, y_pos, f"{stock_info.get('cost', 0):.2f}")
                    c.drawString(left_margin + 115*mm, y_pos, str(count_used))
                    c.drawString(left_margin + 140*mm, y_pos, f"{item_total_cost:.2f}")
                    c.drawString(left_margin + 165*mm, y_pos, f"{item_total_weight_kg:.2f}")
                else:
                    c.drawString(left_margin + 5*mm, y_pos, f"{stock_id} (Info N/A)")
                y_pos -= line_height
        c.setFont("Helvetica-Bold", 8)
        c.drawString(left_margin + 115*mm, y_pos, "Total:")
        c.drawString(left_margin + 140*mm, y_pos, f"{total_cost_from_stock:.2f}")
        c.drawString(left_margin + 165*mm, y_pos, f"{total_weight_from_stock_kg:.2f}")
        y_pos -= line_height * 1.5

    c.setFont("Helvetica-Bold", 11)
    c.drawString(left_margin, y_pos, "Parts Production Summary")
    y_pos -= line_height * 1.5
    c.setFont("Helvetica-Bold", 9)
    header_x_coords_parts = [left_margin + 5*mm, left_margin + 40*mm, left_margin + 70*mm, left_margin + 100*mm, left_margin + 130*mm, left_margin + 160*mm]
    headers_parts = ["Part ID", "Length (mm)", "Demand", "Produced", "Delta (+/-)", "Total Wt (kg)"]
    for i, header in enumerate(headers_parts):
        c.drawString(header_x_coords_parts[i], y_pos, header)
    y_pos -= line_height
    c.setFont("Helvetica", 8)

    total_parts_produced_map = solution_details.get('total_parts_produced', {})
    total_weight_produced_per_part_map_kg = solution_details.get('weight_produced_per_part_kg', {})
    for part_info in parts_data_1d:
        part_id = part_info['name']
        demand = part_info['demand']
        produced = total_parts_produced_map.get(part_id, 0)
        delta = produced - demand
        part_total_weight_kg = total_weight_produced_per_part_map_kg.get(part_id, 0)

        c.drawString(header_x_coords_parts[0], y_pos, str(part_id))
        c.drawString(header_x_coords_parts[1], y_pos, str(part_info['length']))
        c.drawString(header_x_coords_parts[2], y_pos, str(demand))
        c.drawString(header_x_coords_parts[3], y_pos, str(produced))
        c.drawString(header_x_coords_parts[4], y_pos, f"{delta:+.0f}")
        c.drawString(header_x_coords_parts[5], y_pos, f"{part_total_weight_kg:.2f}")
        y_pos -= line_height
    
    y_pos -= line_height

    part_colors_1d = [
        colors.HexColor("#ADD8E6"), colors.HexColor("#90EE90"), colors.HexColor("#FFB6C1"),
        colors.HexColor("#E6E6FA"), colors.HexColor("#FFDEAD"), colors.HexColor("#AFEEEE"),
        colors.HexColor("#F0E68C"), colors.HexColor("#DDA0DD"), colors.HexColor("#ff9999"),
        colors.HexColor("#66b3ff"), colors.HexColor("#99ff99"), colors.HexColor("#ffcc99"),
        colors.HexColor("#c2c2f0"), colors.HexColor("#ffb3e6")
    ]
    part_meta_data = {
        part['name']: {
            'short_id': f"P{i+1}", 'color': part_colors_1d[i % len(part_colors_1d)],
            'length': part['length']
        } for i, part in enumerate(parts_data_1d)
    }

    c.setFont("Helvetica-Bold", 11)
    c.drawString(left_margin, y_pos, "Part Legend")
    y_pos -= line_height
    c.setFont("Helvetica", 8)
    
    legend_col_width = (width_a4_portrait - 2 * left_margin) / 2
    legend_y_start = y_pos
    
    item_count = 0
    for part_id, meta in part_meta_data.items():
        if item_count > 0 and item_count % 16 == 0:
             legend_y_start = y_pos
        
        col_index = item_count // 16
        current_x = left_margin + (col_index * legend_col_width)
        current_y = legend_y_start - ((item_count % 16) * (line_height * 0.8))

        c.setFillColor(meta['color'])
        c.rect(current_x + 2*mm, current_y - 1*mm, 4*mm, 4*mm, stroke=1, fill=1)

        c.setFillColor(colors.black)
        legend_text = f"{meta['short_id']}: {part_id} ({meta['length']:.1f}mm)"
        c.drawString(current_x + 8*mm, current_y, legend_text)
        item_count += 1

    solution_pattern_usage = solution_details.get('pattern_usage', {})
    if solution_pattern_usage:
        c.showPage()
        c.setPageSize(landscape(A4))
        width_a4_landscape, height_a4_landscape = landscape(A4)

        patterns_on_current_page = 0
        max_patterns_per_page = 4
        
        layout_y_start_offset = 30 * mm
        layout_height_per_pattern = (height_a4_landscape - 40*mm) / max_patterns_per_page 
        bar_height = 15 * mm
        text_offset_y = -4 * mm
        kerf_vis_height = bar_height * 1.2

        for pattern_id, times_used in solution_pattern_usage.items():
            if times_used == 0: continue

            pattern_details = all_patterns_dict_1d.get(pattern_id)
            if not pattern_details: continue

            if patterns_on_current_page >= max_patterns_per_page:
                c.showPage()
                c.setPageSize(landscape(A4))
                patterns_on_current_page = 0
            
            y_pos_layout = height_a4_landscape - layout_y_start_offset - (patterns_on_current_page * layout_height_per_pattern)
            
            stock_id = pattern_details['stock_id_used']
            stock_info = stock_data_1d.get(stock_id, {})
            stock_length = stock_info.get('length', 0)
            
            c.setFont("Helvetica-Bold", 10)
            title = f"Pattern: {pattern_id} (used {times_used} times on stock '{stock_id}')"
            c.drawString(left_margin, y_pos_layout, title)
            
            if stock_length > 0:
                draw_scale = (width_a4_landscape - left_margin * 2) / stock_length
                
                c.setFillColor(colors.lightgrey)
                c.rect(left_margin, y_pos_layout - bar_height - 10*mm, stock_length * draw_scale, bar_height, stroke=1, fill=1)
                
                current_x = left_margin
                for piece in pattern_details.get('layout_pieces', []):
                    part_id = piece['part_id']
                    part_length = piece['length']
                    meta = part_meta_data.get(part_id, {})
                    
                    part_width_on_pdf = part_length * draw_scale
                    
                    c.setFillColor(meta.get('color', colors.whitesmoke))
                    c.rect(current_x, y_pos_layout - bar_height - 10*mm, part_width_on_pdf, bar_height, stroke=1, fill=1)
                    
                    c.setFillColor(colors.black)
                    c.setFont("Helvetica", 7)
                    part_text = f"{meta.get('short_id', '?')} ({part_length:.0f}mm)"
                    c.drawCentredString(current_x + part_width_on_pdf / 2, y_pos_layout - bar_height - 10*mm + text_offset_y, part_text)
                    
                    current_x += part_width_on_pdf
                    
                    if saw_kerf_1d > 0 and current_x < (left_margin + stock_length * draw_scale - 1):
                        c.setFillColor(colors.red, alpha=0.5)
                        c.rect(current_x, y_pos_layout - bar_height - 10*mm - (kerf_vis_height-bar_height)/2, saw_kerf_1d * draw_scale, kerf_vis_height, fill=1, stroke=0)
                        current_x += saw_kerf_1d * draw_scale
                
                waste = pattern_details.get('waste_length_in_pattern', 0)
                if waste > 0.1:
                    c.setFont("Helvetica-Oblique", 8)
                    c.setFillColor(colors.darkred)
                    c.drawCentredString(current_x + (waste*draw_scale)/2, y_pos_layout - bar_height - 10*mm + text_offset_y, f"Waste: {waste:.1f}mm")

            patterns_on_current_page += 1

    c.save() 