# 1D Cutting Optimizer for ERPNext

A powerful 1D cutting optimization app for ERPNext that helps you minimize waste when cutting linear materials like bars, pipes, profiles, etc.

## Features

- Adds a "1D Cut Optimizer" button to Sales Orders
- Calculates optimal cutting patterns to minimize waste
- Generates detailed PDF reports with cutting diagrams
- Supports material weight calculations
- Works with any linear material (bars, pipes, profiles, etc.)

## Screenshots

![Optimizer Dialog](screenshots/optimizer_dialog.png)
![PDF Report](screenshots/pdf_report.png)

## Requirements

- ERPNext 14+
- Python 3.10+
- Python packages:
  - reportlab
  - ortools

## Installation

### Standard Installation

You can install this app using the [bench](https://github.com/frappe/bench) CLI:

```bash
cd $PATH_TO_YOUR_BENCH
bench get-app https://github.com/yourusername/erpnext-cutting-optimizer
bench install-app example_app
```

After installation, install the required Python packages:

```bash
pip install reportlab ortools
```

### Docker Installation

To install this app using [Frappe Docker](https://github.com/frappe/frappe_docker), follow these steps:

1. Clone the Frappe Docker repository:
   ```bash
   git clone https://github.com/frappe/frappe_docker
   cd frappe_docker
   ```

2. Create a custom `apps.json` file:
   ```bash
   cp example/custom-apps/apps.json .
   ```

3. Edit the `apps.json` file to include this app:
   ```json
   {
     "example_app": {
       "resolution": {
         "branch": "main",
         "repo_url": "https://github.com/yourusername/erpnext-cutting-optimizer"
       }
     }
   }
   ```

4. Create a custom `Dockerfile`:
   ```bash
   cp example/custom-apps/Dockerfile .
   ```

5. Edit the `Dockerfile` to install the required Python packages:
   ```dockerfile
   FROM frappe/erpnext:latest

   # Install custom apps
   COPY apps.json /tmp/apps.json
   RUN install-app example_app

   # Install additional Python packages
   RUN pip install reportlab ortools
   ```

6. Build and start the containers:
   ```bash
   docker-compose -f compose.yaml -f overrides/compose.custom-apps.yaml up -d
   ```

For more detailed instructions, refer to the [Frappe Docker documentation](https://github.com/frappe/frappe_docker/blob/main/docs/custom-apps.md).

## Usage

1. Open any Sales Order
2. Click on "Create" > "1D Cut Optimizer"
3. Enter your stock materials and parts to cut
4. Click "Run Optimization"
5. A PDF with the cutting plan will be attached to the Sales Order

## Contributing

This app uses `pre-commit` for code formatting and linting. Please [install pre-commit](https://pre-commit.com/#installation) and enable it for this repository:

```bash
cd apps/example_app
pre-commit install
```

Pre-commit is configured to use the following tools for checking and formatting your code:

- ruff
- eslint
- prettier
- pyupgrade

### CI

This app can use GitHub Actions for CI. The following workflows are configured:

- CI: Installs this app and runs unit tests on every push to `develop` branch.
- Linters: Runs [Frappe Semgrep Rules](https://github.com/frappe/semgrep-rules) and [pip-audit](https://pypi.org/project/pip-audit/) on every pull request.

## License

MIT
