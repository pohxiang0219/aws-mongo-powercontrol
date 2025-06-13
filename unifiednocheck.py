import sys
import time
import boto3
import json
from botocore.exceptions import ClientError, WaiterError
import os
import concurrent.futures

# Configuration
WAITER_TIMEOUT_SECONDS = 300  # Reduced from 900 to 300 seconds (5 minutes)
CHECK_INTERVAL_SECONDS = 15   # Reduced from 30 to 15 seconds

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
        print(f"Updating service '{service_config['service']}' in cluster '{service_config['cluster']}' to desired count {desired_count}...")
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
    """Starts all resources in the correct order and verifies each step."""
    print("\n--- Phase 1: Starting Databases (RDS & Atlas) ---")
    
    # Start RDS Instances
    for db_id in RDS_INSTANCES:
        try:
            print(f"Starting RDS instance '{db_id}'...")
            rds_client.start_db_instance(DBInstanceIdentifier=db_id)
        except ClientError as e:
            if "InvalidDBInstanceState" in str(e):
                print(f"  -> Note: RDS instance '{db_id}' is already running or not in a stoppable state.")
            else:
                print(f"Error starting RDS instance '{db_id}': {e}")
                return False
    
    # Resume Atlas Clusters
    for cluster in ATLAS_CLUSTERS:
        print(f"Resuming Atlas cluster '{cluster}'...")
        os.system(f"atlas clusters start {cluster}")

    # Verify RDS Databases are available (with reduced timeout)
    print("\n--- Verifying Database Availability ---")
    rds_waiter = rds_client.get_waiter('db_instance_available')
    for db_id in RDS_INSTANCES:
        try:
            print(f"Waiting for RDS instance '{db_id}' to become available...")
            rds_waiter.wait(DBInstanceIdentifier=db_id, WaiterConfig={'Delay': 20, 'MaxAttempts': 15})  # 5 minutes max
            print(f"Success: RDS instance '{db_id}' is available.")
        except WaiterError as e:
            print(f"Timeout or error waiting for RDS instance '{db_id}': {e}")
            return False

    print("Atlas clusters started (not waiting for state verification)")

    print("\n--- Phase 2: Starting EC2 Bastion Host ---")
    try:
        print(f"Starting EC2 instances: {EC2_INSTANCES}...")
        ec2_client.start_instances(InstanceIds=EC2_INSTANCES)
        ec2_waiter = ec2_client.get_waiter('instance_running')
        print("Waiting for EC2 instances to enter 'running' state...")
        ec2_waiter.wait(InstanceIds=EC2_INSTANCES, WaiterConfig={'Delay': 10, 'MaxAttempts': 20})  # 200 seconds max
        print("Success: All specified EC2 instances are running.")
    except (ClientError, WaiterError) as e:
        print(f"Error starting or waiting for EC2 instances: {e}")
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
                print(f"Service update initiated: {service_name}")
            else:
                print(f"Error updating service '{service_name}': {error}")
                return False

    # Wait for all services to stabilize in parallel
    print("Skipped Checking.")

            
    return True

# --- Main Logic: Shutdown Sequence ---

def shutdown_sequence():
    """Stops all resources in reverse order and verifies each step."""
    print("\n--- Phase 1: Scaling Down ECS Services (Parallel) ---")
    
    # Scale down all ECS services in parallel
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        # Submit all service updates to 0
        update_futures = {executor.submit(update_ecs_service, s, 0): s for s in ECS_SERVICES}
        
        # Wait for all updates to complete
        for future in concurrent.futures.as_completed(update_futures):
            success, service_name, error = future.result()
            if success:
                print(f"Service scale-down initiated: {service_name}")
            else:
                print(f"Error scaling down service '{service_name}': {error}")
                return False

    # Wait for all services to scale down in parallel
    print("Skipped EC2 Checking")


    print("\n--- Phase 2: Stopping EC2 Bastion Host ---")
    try:
        print(f"Stopping EC2 instances: {EC2_INSTANCES}...")
        ec2_client.stop_instances(InstanceIds=EC2_INSTANCES)
        ec2_waiter = ec2_client.get_waiter('instance_stopped')
        print("Waiting for EC2 instances to enter 'stopped' state...")
        ec2_waiter.wait(InstanceIds=EC2_INSTANCES, WaiterConfig={'Delay': 10, 'MaxAttempts': 20})  # 200 seconds max
        print("Success: All specified EC2 instances are stopped.")
    except (ClientError, WaiterError) as e:
        print(f"Error stopping or waiting for EC2 instances: {e}")
        return False
        
    print("\n--- Phase 3: Stopping Databases (RDS & Atlas) ---")
    
    # Stop RDS Instances
    for db_id in RDS_INSTANCES:
        rds_client.stop_db_instance(DBInstanceIdentifier=db_id)
            
            

    # Pause Atlas Clusters
    for cluster in ATLAS_CLUSTERS:
        print(f"Pausing Atlas cluster '{cluster}'...")
        os.system(f"atlas clusters pause {cluster}")
        print(f"Atlas cluster '{cluster}' pause command sent (not waiting for state verification)")
            
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
        print(f"Sequence '{action.upper()}' completed successfully!")
    else:
        print(f"Sequence '{action.upper()}' FAILED. Please review logs above.")
        sys.exit(1)