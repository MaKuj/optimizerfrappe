# Docker Installation Guide for 1D Cutting Optimizer

This guide provides detailed steps to install the 1D Cutting Optimizer app using Docker.

## Prerequisites

- Docker and Docker Compose installed on your system
- Git installed on your system
- Basic knowledge of Docker and command line

## Installation Steps

### 1. Clone the Frappe Docker Repository

```bash
git clone https://github.com/frappe/frappe_docker
cd frappe_docker
```

### 2. Set Up Custom App Configuration

Create a custom apps.json file:

```bash
cp example/custom-apps/apps.json .
```

Edit the apps.json file to include the 1D Cutting Optimizer app:

```json
{
  "example_app": {
    "resolution": {
      "branch": "main",
      "repo_url": "https://github.com/YOUR_USERNAME/erpnext-cutting-optimizer"
    }
  }
}
```

### 3. Create a Custom Dockerfile

```bash
cp example/custom-apps/Dockerfile .
```

Edit the Dockerfile to include the required Python packages:

```dockerfile
FROM frappe/erpnext:latest

# Install custom apps
COPY apps.json /tmp/apps.json
RUN install-app example_app

# Install additional Python packages
RUN pip install reportlab ortools
```

### 4. Build and Start the Containers

```bash
docker-compose -f compose.yaml -f overrides/compose.custom-apps.yaml up -d
```

### 5. Wait for the Setup to Complete

The initial setup may take some time as it downloads and installs all the necessary components.

### 6. Access Your ERPNext Instance

Once the setup is complete, you can access your ERPNext instance at:

```
http://localhost:8000
```

Log in with the default credentials:

- Username: Administrator
- Password: admin

### 7. Verify the App Installation

1. Go to the "Apps" section in ERPNext
2. Check if "1D Cutting Optimizer" is listed
3. Open a Sales Order to verify the "1D Cut Optimizer" button is available

## Troubleshooting

### Missing Dependencies

If you encounter errors related to missing Python packages:

```bash
docker-compose exec backend pip install reportlab ortools
```

### App Not Showing Up

If the app is not visible in ERPNext:

```bash
docker-compose exec backend bench --site site1.local install-app example_app
```

### Logs Inspection

To check the logs for any issues:

```bash
docker-compose logs -f backend
```

## Updating the App

To update the app to the latest version:

```bash
docker-compose exec backend bench update --pull
docker-compose exec backend bench --site site1.local migrate
```

## Backup and Restore

### Create a Backup

```bash
docker-compose exec backend bench --site site1.local backup
```

### Restore from Backup

```bash
docker-compose exec backend bench --site site1.local --force restore [backup-file]
``` 