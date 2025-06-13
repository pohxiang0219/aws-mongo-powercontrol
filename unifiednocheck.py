import sys
import time
import boto3
import json
from botocore.exceptions import ClientError
import os
import concurrent.futures

# Resource Definitions
RDS_INSTANCES = [
    'my-staging-main-hiredly-db',
    'my-staging-main-naikgaji-db' 
]
EC2_INSTANCES = ["i-048cda6b4dc31f3c9"]
ATLAS_CLUSTERS = ['wobb-api-staging']

ECS_SERVICES = [
    {'cluster': 'my-staging-ashley-ecs-cluster', 'service': 'my-staging-ashley-worker-ecs-service', 'count': 1},
    {'cluster': 'my-staging-ashley-ecs-cluster', 'service': 'my-staging-ashley-backend-ecs-service', 'count': 1},
    {'cluster': 'my-staging-hiredly-ecs-cluster', 'service': 'my-staging-hiredly-be-ecs-service', 'count': 1},
    {'cluster': 'my-staging-hiredly-ecs-cluster', 'service': 'my-staging-hiredly-urgent-worker-ecs-service', 'count': 1},
    {'cluster': 'my-staging-hiredly-ecs-cluster', 'service': 'my-staging-hiredly-worker-ecs-service', 'count': 1},
    {'cluster': 'my-staging-naikgaji-ecs-cluster', 'service': 'my-staging-naikgaji-be-ecs-service', 'count': 1},
    {'cluster': 'my-staging-naikgaji-ecs-cluster', 'service': 'my-staging-naikgaji-worker-ecs-service', 'count': 1},
]

# --- Boto3 Clients ---
session = boto3.Session()
rds_client = session.client('rds')
ec2_client = session.client('ec2')
ecs_client = session.client('ecs')

# --- Helper Functions ---

def update_ecs_service(service_config, desired_count):
    """Update a single ECS service"""
    try:
        ecs_client.update_service(
            cluster=service_config['cluster'],
            service=service_config['service'],
            desiredCount=desired_count
        )
        return True, service_config['service'], None
    except Exception as e:
        return False, service_config['service'], str(e)

# --- Main Logic: Startup Sequence ---

def startup_sequence():
    """Starts all resources - no waiting/checking."""
    print("\n--- Phase 1: Starting Databases (RDS & Atlas) ---")
    
    # Start RDS Instances
    for db_id in RDS_INSTANCES:
        try:
            print(f"Starting RDS instance '{db_id}'...")
            rds_client.start_db_instance(DBInstanceIdentifier=db_id)
            print(f"RDS start command sent for '{db_id}' (not waiting for completion)")
        except ClientError as e:
            if "InvalidDBInstanceState" in str(e):
                print(f"  -> Note: RDS instance '{db_id}' is already running.")
            else:
                print(f"Error starting RDS instance '{db_id}': {e}")
                return False
    
    # Resume Atlas Clusters
    for cluster in ATLAS_CLUSTERS:
        print(f"Resuming Atlas cluster '{cluster}'...")
        os.system(f"atlas clusters start {cluster}")
        print(f"Atlas cluster '{cluster}' start command sent (not waiting for completion)")

    print("\n--- Phase 2: Starting EC2 Bastion Host ---")
    try:
        print(f"Starting EC2 instances: {EC2_INSTANCES}...")
        ec2_client.start_instances(InstanceIds=EC2_INSTANCES)
        print("EC2 start command sent (not waiting for completion)")
    except ClientError as e:
        print(f"Error starting EC2 instances: {e}")
        return False
    
    print("\n--- Phase 3: Scaling Up ECS Services (Parallel) ---")
    
    # Start all ECS services in parallel
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        # Submit all service updates
        update_futures = {executor.submit(update_ecs_service, s, s['count']): s for s in ECS_SERVICES}
        
        # Wait for all updates to complete
        for future in concurrent.futures.as_completed(update_futures):
            success, service_name, error = future.result()
            if success:
                print(f"Service scale-up command sent: {service_name}")
            else:
                print(f"Error updating service '{service_name}': {error}")
                return False
            
    return True

# --- Main Logic: Shutdown Sequence ---

def shutdown_sequence():
    """Stops all resources - no waiting/checking."""
    print("\n--- Phase 1: Scaling Down ECS Services (Parallel) ---")
    
    # Scale down all ECS services in parallel
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        # Submit all service updates to 0
        update_futures = {executor.submit(update_ecs_service, s, 0): s for s in ECS_SERVICES}
        
        # Wait for all updates to complete
        for future in concurrent.futures.as_completed(update_futures):
            success, service_name, error = future.result()
            if success:
                print(f"Service scale-down command sent: {service_name}")
            else:
                print(f"Error scaling down service '{service_name}': {error}")
                return False

    print("\n--- Phase 2: Stopping EC2 Bastion Host ---")
    try:
        print(f"Stopping EC2 instances: {EC2_INSTANCES}...")
        ec2_client.stop_instances(InstanceIds=EC2_INSTANCES)
        print("EC2 stop command sent (not waiting for completion)")
    except ClientError as e:
        print(f"Error stopping EC2 instances: {e}")
        return False
        
    print("\n--- Phase 3: Stopping Databases (RDS & Atlas) ---")
    
    # Stop RDS Instances
    for db_id in RDS_INSTANCES:
        try:
            print(f"Stopping RDS instance '{db_id}'...")
            rds_client.stop_db_instance(DBInstanceIdentifier=db_id)
            print(f"RDS stop command sent for '{db_id}' (not waiting for completion)")
        except ClientError as e:
            print(f"Error stopping RDS instance '{db_id}': {e}")
            return False

    # Pause Atlas Clusters
    for cluster in ATLAS_CLUSTERS:
        print(f"Pausing Atlas cluster '{cluster}'...")
        os.system(f"atlas clusters pause {cluster}")
        print(f"Atlas cluster '{cluster}' pause command sent (not waiting for completion)")
            
    return True

# --- Script Entry Point ---

if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in ['start', 'stop']:
        print("Usage: python unified.py [start|stop]")
        sys.exit(1)
    
    action = sys.argv[1]
    start_time = time.time()
    
    if action == 'start':
        print("Initiating staging environment startup!")
        success = startup_sequence()
    else:
        print("Initiating staging environment shutdown!")
        success = shutdown_sequence()
    
    elapsed_time = time.time() - start_time
    print("\n" + "="*50)
    print(f"Total execution time: {elapsed_time:.1f} seconds")
    
    if success:
        print(f"All '{action.upper()}' commands sent successfully!")
    else:
        print(f"Sequence '{action.upper()}' FAILED. Please review logs above.")
        sys.exit(1)