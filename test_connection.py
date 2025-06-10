#!/usr/bin/env python3
import boto3
import sys
import os
from botocore.exceptions import ClientError, NoCredentialsError, ProfileNotFound

def test_aws_connection():
    """Test AWS connection for GitHub Actions"""
    print("🔧 Testing AWS Connection for GitHub Actions\n")
    
    try:
        # For GitHub Actions, use default credentials (no profile needed)
        # AWS credentials should be set via environment variables:
        # AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_SESSION_TOKEN
        
        print("📋 Creating AWS session...")
        session = boto3.Session()
        
        # Test 1: Check AWS Identity
        print("\n1️⃣ Testing AWS Identity (STS)...")
        sts_client = session.client('sts')
        identity = sts_client.get_caller_identity()
        print(f"   ✅ Account ID: {identity.get('Account')}")
        print(f"   ✅ User ARN: {identity.get('Arn')}")
        print(f"   ✅ Current Region: {session.region_name or 'ap-southeast-1'}")
        
        # Test 2: Basic S3 Access
        print("\n2️⃣ Testing S3 Access...")
        s3_client = session.client('s3')
        buckets = s3_client.list_buckets()
        bucket_count = len(buckets['Buckets'])
        print(f"   ✅ S3 accessible - Found {bucket_count} buckets")
        
        # Test 3: ECS Access
        print("\n3️⃣ Testing ECS Access...")
        ecs_client = session.client('ecs')
        clusters = ecs_client.list_clusters()
        cluster_count = len(clusters['clusterArns'])
        print(f"   ✅ ECS accessible - Found {cluster_count} clusters")
        
        # Test 4: EC2 Access
        print("\n4️⃣ Testing EC2 Access...")
        ec2_client = session.client('ec2')
        instances = ec2_client.describe_instances()
        instance_count = sum(len(reservation['Instances']) for reservation in instances['Reservations'])
        print(f"   ✅ EC2 accessible - Found {instance_count} instances")
        
        # Test 5: RDS Access
        print("\n5️⃣ Testing RDS Access...")
        rds_client = session.client('rds')
        databases = rds_client.describe_db_instances()
        db_count = len(databases['DBInstances'])
        print(f"   ✅ RDS accessible - Found {db_count} databases")
        
        print("\n🎉 All AWS connection tests PASSED!")
        print("✅ GitHub Actions can successfully connect to AWS")
        return True
        
    except NoCredentialsError:
        print("❌ Error: No AWS credentials found")
        print("💡 In GitHub Actions, set these secrets:")
        print("   - AWS_ACCESS_KEY_ID")
        print("   - AWS_SECRET_ACCESS_KEY")
        print("   - AWS_SESSION_TOKEN (if using temporary credentials)")
        return False
        
    except ClientError as e:
        error_code = e.response['Error']['Code']
        if error_code == 'UnauthorizedOperation':
            print("❌ Error: Insufficient permissions")
            print("💡 Check IAM permissions for the AWS credentials")
        elif error_code == 'AccessDenied':
            print("❌ Error: Access denied")
            print("💡 Verify the AWS credentials have the required permissions")
        else:
            print(f"❌ AWS Client Error: {e}")
        return False
        
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False


def test_atlas_cli():
    """Test MongoDB Atlas CLI availability"""
    print("\n🍃 Testing MongoDB Atlas CLI...")
    
    try:
        import subprocess
        result = subprocess.run(
            ["atlas", "--version"], 
            capture_output=True, 
            text=True, 
            timeout=10
        )
        
        if result.returncode == 0:
            version = result.stdout.strip()
            print(f"   ✅ Atlas CLI available: {version}")
            return True
        else:
            print("   ❌ Atlas CLI command failed")
            return False
            
    except FileNotFoundError:
        print("   ❌ Atlas CLI not found")
        print("   💡 Install with: curl -fsSL https://www.mongodb.com/try/download/atlascli | sh")
        return False
        
    except Exception as e:
        print(f"   ❌ Error testing Atlas CLI: {e}")
        return False


if __name__ == "__main__":
    print("🚀 GitHub Actions AWS Connection Test\n")
    print("="*50)
    
    # Test AWS connection
    aws_success = test_aws_connection()
    
    # Test Atlas CLI (optional)
    atlas_success = test_atlas_cli()
    
    print("\n" + "="*50)
    print("📊 Test Results:")
    print(f"   AWS Connection: {'✅ PASS' if aws_success else '❌ FAIL'}")
    print(f"   Atlas CLI: {'✅ PASS' if atlas_success else '❌ FAIL'}")
    
    if aws_success:
        print("\n🎉 Ready for GitHub Actions deployment!")
        sys.exit(0)
    else:
        print("\n💥 Fix AWS connection before running in GitHub Actions")
        sys.exit(1)
