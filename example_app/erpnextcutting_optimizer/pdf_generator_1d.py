# example_app/erpnextcutting_optimizer/pdf_generator_1d.py

import io
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape, portrait
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas


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
            ("Yield:", f"{details.get('yield_percentage', 0):.2f} %"),
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
        
        headers = ["Stock ID", "Length (mm)", "Cost/Item", "Used Qty", "Total Cost", "Total Wt (kg)"]
        coords = [self.margins['left'] + x for x in [5*mm, 50*mm, 85*mm, 115*mm, 140*mm, 165*mm]]
        
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
                stock_id, f"{info.get('length', 0)}", f"{info.get('cost', 0):.2f}",
                count, f"{total_cost:.2f}", f"{total_weight:.2f}"
            ]
            for i, v in enumerate(values):
                self.c.drawString(coords[i], y_pos, str(v))
            y_pos -= self.line_height
        return y_pos

    def _draw_production_summary_table(self, y_pos, summary_data):
        self._set_font('header')
        self.c.drawString(self.margins['left'], y_pos, "Parts Production Summary")
        y_pos -= self.line_height * 1.5

        headers = ["Part ID", "Length (mm)", "Demand", "Produced", "Delta (+/-)", "Total Wt (kg)"]
        coords = [self.margins['left'] + x for x in [5*mm, 40*mm, 70*mm, 100*mm, 130*mm, 160*mm]]
        self._set_font('sub_header')
        for i, h in enumerate(headers):
            self.c.drawString(coords[i], y_pos, h)
        y_pos -= self.line_height

        self._set_font('body_small')
        for item in summary_data:
            delta = item.get('Delta (+/-)', 0)
            values = [
                item.get('Part ID', 'N/A'),
                f"{item.get('Length (mm)', 0)}",
                item.get('Demand', 0),
                item.get('Produced', 0),
                f"{delta:+.0f}",
                f"{item.get('Total Wt (kg)', 0):.2f}"
            ]
            for i, v in enumerate(values):
                self.c.drawString(coords[i], y_pos, str(v))
            y_pos -= self.line_height
        return y_pos
        
    def _draw_part_legend(self, y_pos):
        part_colors = [
            colors.HexColor("#ADD8E6"), colors.HexColor("#90EE90"), colors.HexColor("#FFB6C1"),
            colors.HexColor("#E6E6FA"), colors.HexColor("#FFDEAD"), colors.HexColor("#AFEEEE"),
            colors.HexColor("#F0E68C"), colors.HexColor("#DDA0DD"), colors.HexColor("#ff9999"),
        ]
        
        known_parts_by_name = {p['name']: p for p in self.parts_data if 'name' in p}
        length_to_name_map = {p['length']: p['name'] for p in self.parts_data if 'name' in p and 'length' in p}

        all_part_ids_in_solution = set(known_parts_by_name.keys())

        for pattern_details in self.all_patterns_dict.values():
            for piece in pattern_details.get('layout_pieces', []):
                part_id = piece.get('part_id')
                if not part_id or part_id not in known_parts_by_name:
                    part_length = piece.get('length')
                    if part_length in length_to_name_map:
                        piece['part_id'] = length_to_name_map[part_length]
                        all_part_ids_in_solution.add(piece['part_id'])
                elif part_id:
                     all_part_ids_in_solution.add(part_id)

        sorted_part_ids = sorted(list(all_part_ids_in_solution))

        part_meta_data = {
            part_id: {
                'short_id': f"P{i+1}",
                'color': part_colors[i % len(part_colors)],
                'length': known_parts_by_name[part_id].get('length', 0)
            } for i, part_id in enumerate(sorted_part_ids) if part_id in known_parts_by_name
        }
        self.part_meta_data = part_meta_data
        
        self._set_font('header')
        self.c.drawString(self.margins['left'], y_pos, "Part Legend")
        y_pos -= self.line_height

        self._set_font('body_small')
        for part_id, meta in self.part_meta_data.items():
            self.c.setFillColor(meta['color'])
            self.c.rect(self.margins['left'] + 2*mm, y_pos - 1*mm, 4*mm, 4*mm, stroke=1, fill=1)
            self.c.setFillColor(colors.black)
            legend_text = f"{meta['short_id']}: {part_id} ({meta['length']:.1f}mm)"
            self.c.drawString(self.margins['left'] + 8*mm, y_pos, legend_text)
            y_pos -= self.line_height * 0.9
            if y_pos < self.margins['bottom']:
                self.c.showPage()
                y_pos = self.height - self.margins['top']
                self._set_font('body_small') # Reset font on new page
        return y_pos

    def _draw_all_patterns(self):
        if not self.all_patterns_dict:
            return
            
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
        stock_id = pattern_details.get('stock_id_used')
        if not stock_id:
            return

        stock_info = self.stock_data.get(stock_id, {})
        stock_length = stock_info.get('length', 0)
        
        self._set_font('sub_header')
        
        usage = 0
        for details in self.solution_details_list:
            if pattern_id in details.get('pattern_usage', {}):
                usage = details['pattern_usage'][pattern_id]
                break
        
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
            part_id = piece.get('part_id')
            part_length = piece.get('length', 0)
            
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