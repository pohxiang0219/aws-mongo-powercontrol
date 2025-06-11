import sys
import time
import boto3
import json
from botocore.exceptions import ClientError, WaiterError
import os

# Map CI


WAITER_TIMEOUT_SECONDS = 900
CHECK_INTERVAL_SECONDS = 30 

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
# We define them once to be reused.
session = boto3.Session()
rds_client = session.client('rds')
ec2_client = session.client('ec2')
ecs_client = session.client('ecs')

# --- Main Logic: Startup Sequence ---

def startup_sequence():
    """Starts all resources in the correct order and verifies each step."""
    print("\n--- Step 1: Starting Databases (RDS & Atlas) ---")
    
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
    
    # Resume Atlas Cluster
    for cluster in ATLAS_CLUSTERS:
        print(f"Resuming Atlas cluster '{cluster}'...")
        os.system(f"atlas clusters start {cluster}")

    # Verify Databases are available
    print("\n--- Verifying Database Availability ---")
    rds_waiter = rds_client.get_waiter('db_instance_available')
    for db_id in RDS_INSTANCES:
        try:
            print(f"Waiting for RDS instance '{db_id}' to become available...")
            rds_waiter.wait(DBInstanceIdentifier=db_id, WaiterConfig={'Delay': 30, 'MaxAttempts': 30})
            print(f"Success: RDS instance '{db_id}' is available.")
        except WaiterError as e:
            print(f"Timeout or error waiting for RDS instance '{db_id}': {e}")
            return False

    # Removed Atlas cluster state checking
    print("Atlas clusters started (not waiting for state verification)")

    print("\n--- Step 2: Starting EC2 Bastion Host ---")
    try:
        print(f"Starting EC2 instances: {EC2_INSTANCES}...")
        ec2_client.start_instances(InstanceIds=EC2_INSTANCES)
        ec2_waiter = ec2_client.get_waiter('instance_running')
        print("Waiting for EC2 instances to enter 'running' state...")
        ec2_waiter.wait(InstanceIds=EC2_INSTANCES, WaiterConfig={'Delay': 15, 'MaxAttempts': 40})
        print("Success: All specified EC2 instances are running.")
    except (ClientError, WaiterError) as e:
        print(f"Error starting or waiting for EC2 instances: {e}")
        return False
    
    print("\n--- Step 3: Scaling Up ECS Services ---")
    ecs_waiter = ecs_client.get_waiter('services_stable')
    for s in ECS_SERVICES:
        try:
            print(f"Updating service '{s['service']}' in cluster '{s['cluster']}' to desired count {s['count']}...")
            ecs_client.update_service(
                cluster=s['cluster'],
                service=s['service'],
                desiredCount=s['count']
            )
            ecs_waiter.wait(
                cluster=s['cluster'],
                services=[s['service']],
                WaiterConfig={'Delay': 15, 'MaxAttempts': 40}
            )
            print(f"Success: Service '{s['service']}' is stable with {s['count']} running tasks.")
        except (ClientError, WaiterError) as e:
            print(f"Error updating or waiting for service '{s['service']}': {e}")
            return False
            
    return True


# --- Main Logic: Shutdown Sequence ---
def shutdown_sequence():
    """Stops all resources in reverse order and verifies each step."""
    print("\n--- Step 1: Scaling Down ECS Services ---")
    ecs_waiter = ecs_client.get_waiter('services_stable')
    for s in ECS_SERVICES:
        try:
            print(f"Updating service '{s['service']}' in cluster '{s['cluster']}' to desired count 0...")
            ecs_client.update_service(
                cluster=s['cluster'],
                service=s['service'],
                desiredCount=0
            )
            # Wait for the service to stabilize with 0 tasks
            ecs_waiter.wait(
                cluster=s['cluster'],
                services=[s['service']],
                WaiterConfig={'Delay': 15, 'MaxAttempts': 40}
            )
            print(f"Success: Service '{s['service']}' has scaled down to 0.")
        except (ClientError, WaiterError) as e:
            print(f"Error scaling down service '{s['service']}': {e}")
            return False

    print("\n--- Step 2: Stopping EC2 Bastion Host ---")
    try:
        print(f"Stopping EC2 instances: {EC2_INSTANCES}...")
        ec2_client.stop_instances(InstanceIds=EC2_INSTANCES)
        ec2_waiter = ec2_client.get_waiter('instance_stopped')
        print("Waiting for EC2 instances to enter 'stopped' state...")
        ec2_waiter.wait(InstanceIds=EC2_INSTANCES, WaiterConfig={'Delay': 15, 'MaxAttempts': 40})
        print("Success: All specified EC2 instances are stopped.")
    except (ClientError, WaiterError) as e:
        print(f"Error stopping or waiting for EC2 instances: {e}")
        return False
        
    print("\n--- Step 3: Stopping Databases (RDS & Atlas) ---")
    # Stop RDS Instances
    rds_waiter = rds_client.get_waiter('db_instance_stopped')
    for db_id in RDS_INSTANCES:
        try:
            print(f"Stopping RDS instance '{db_id}'...")
            rds_client.stop_db_instance(DBInstanceIdentifier=db_id)
            rds_waiter.wait(DBInstanceIdentifier=db_id, WaiterConfig={'Delay': 30, 'MaxAttempts': 30})
            print(f"Success: RDS instance '{db_id}' is stopped.")
        except (ClientError, WaiterError) as e:
            if "InvalidDBInstanceState" in str(e):
                 print(f"  -> Note: RDS instance '{db_id}' was already stopped or not in a running state.")
            else:
                print(f"Error stopping RDS instance '{db_id}': {e}")
                return False

    # Pause Atlas Cluster
    for cluster in ATLAS_CLUSTERS:
        print(f"Pausing Atlas cluster '{cluster}'...")
        os.system(f"atlas clusters pause {cluster}")
        # Removed Atlas cluster state checking
        print(f"Atlas cluster '{cluster}' pause command sent (not waiting for state verification)")
            
    return True

# --- Script Entry Point ---
if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in ['start', 'stop']:
        print("Usage: python control_environment.py [start|stop]")
        sys.exit(1)
    
    action = sys.argv[1]
    
    # The Boto3 session handles the profile, no need for os.environ
    
    if action == 'start':
        print("Initiating staging environment startup!")
        success = startup_sequence()
    else:
        print("Initiating staging environment shutdown!")
        success = shutdown_sequence()
    
    print("\n" + "="*50)
    if success:
        print(f"Sequence '{action.upper()}' completed successfully!")
    else:
        print(f"Sequence '{action.upper()}' FAILED. Please review logs above.")
        sys.exit(1)
