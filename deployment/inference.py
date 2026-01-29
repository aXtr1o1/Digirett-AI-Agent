import boto3

sm = boto3.client("sagemaker")
print(
sm.describe_endpoint(
    EndpointName="embedding-bge-m3-endpoint"
)
)