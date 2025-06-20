"""Configuration for docs."""

source_link = "https://github.com/ealu-pl/cutting_optimizer"
docs_base_url = "https://ealu-pl.github.io/cutting_optimizer"
headline = "1D Cutting Optimizer for ERPNext"
sub_heading = "Optimize the cutting of materials into parts with minimal waste"

def get_context(context):
	context.brand_html = "Cutting Optimizer"
	context.favicon = 'octicon octicon-file-binary'
	context.app_title = "Cutting Optimizer" 
	context.app_publisher = "ealu.pl"
	context.app_description = "1D Cutting Optimizer for ERPNext"
	context.app_email = "ealu@ealu.pl" 