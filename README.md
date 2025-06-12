# ⚡aws-mongo-powercontrol
Purpose of this script is it can be triggered to scale down the ECS and turn off the EC2 bastion instances followed by pausing MongoDB staging cluster.
This is achieved by using AWS Cli and Atlas Cli.
boto3 is used to handle the AWS which is a native python SDK 
subprocess is paired with atlas CLI to execute external command-line for MongoDB


# 🔧 Usage
1. Go to Actions tab
2. On the left hand sidebar click on Control Staging Environment
3. Click run workflow
4. "Start" is to upscale the ECS and start the EC2 instances and mongoDB staging cluster while "Stop" is to downscale the ECS and stop the EC2 instance and mongoDB staging cluster

# 🏠Running Manually 
1. Go to actions tab
2. Click on "Control Staging Environment"
3. Choose state (Start/Stop)
4. Run Workflow
