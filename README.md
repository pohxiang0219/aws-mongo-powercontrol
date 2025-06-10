# aws-mongo-powercontrol
Purpose of this script is it can be triggered to scale down the ECS and turn off the EC2 bastion instances followed by pausing MongoDB staging cluster.
This is achieved by using AWS Cli and Atlas Cli.
boto3 is used to handle the AWS which is a native python SDK 
subprocess is paired with atlas CLI to execute external command-line for MongoDB


# Usage
