#!/bin/bash

# MediMind AI - GCP Infrastructure Setup Script
# This script creates a VPC, Firewall Rules, and a Compute Engine Instance.

# --- Configuration ---
PROJECT_ID=$(gcloud config get-value project)
NETWORK_NAME="medimind-vpc"
SUBNET_NAME="medimind-subnet"
REGION="us-central1"
ZONE="us-central1-a"
INSTANCE_NAME="medimind-vm"
MACHINE_TYPE="e2-medium"
IMAGE_FAMILY="ubuntu-2204-lts"
IMAGE_PROJECT="ubuntu-os-cloud"

echo "Using Project ID: $PROJECT_ID"

# 1. Create VPC Network
echo "Creating VPC Network: $NETWORK_NAME..."
gcloud compute networks create $NETWORK_NAME --subnet-mode=custom

# 2. Create Subnet
echo "Creating Subnet: $SUBNET_NAME..."
gcloud compute networks subnets create $SUBNET_NAME \
    --network=$NETWORK_NAME \
    --range=10.0.1.0/24 \
    --region=$REGION

# 3. Create Firewall Rules
echo "Creating Firewall Rules..."

# Allow SSH
gcloud compute firewall-rules create allow-ssh \
    --network=$NETWORK_NAME \
    --allow=tcp:22 \
    --description="Allow SSH access" \
    --direction=INGRESS

# Allow HTTP/HTTPS and API Port 8000
gcloud compute firewall-rules create allow-http-https-api \
    --network=$NETWORK_NAME \
    --allow=tcp:80,tcp:443,tcp:8000 \
    --description="Allow HTTP, HTTPS, and Backend API" \
    --direction=INGRESS

# 4. Create GCE Instance with Startup Script
echo "Creating Compute Engine Instance: $INSTANCE_NAME..."

cat <<EOF > startup.sh
#!/bin/bash
# Install Docker
sudo apt-get update
sudo apt-get install -y apt-transport-https ca-certificates curl software-properties-common
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg
echo "deb [arch=\$(dpkg --print-architecture) signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/ubuntu \$(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io

# Install Nginx
sudo apt-get install -y nginx
EOF

gcloud compute instances create $INSTANCE_NAME \
    --zone=$ZONE \
    --machine-type=$MACHINE_TYPE \
    --network=$NETWORK_NAME \
    --subnet=$SUBNET_NAME \
    --image-family=$IMAGE_FAMILY \
    --image-project=$IMAGE_PROJECT \
    --metadata-from-file startup-script=startup.sh \
    --tags=http-server,https-server

# Cleanup temporary startup script
rm startup.sh

echo "Infrastructure setup complete!"
echo "Instance IP Address:"
gcloud compute instances describe $INSTANCE_NAME --zone=$ZONE --format='get(networkInterfaces[0].accessConfigs[0].natIP)'
