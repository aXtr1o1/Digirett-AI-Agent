import sagemaker
from sagemaker.huggingface import HuggingFaceModel

session = sagemaker.Session()

role = "ARN-Value"

hub = {
    "HF_MODEL_ID": "BAAI/bge-m3",
    "HF_TASK": "feature-extraction",
    "HF_MODEL_REVISION": "main",
}

model = HuggingFaceModel(
    env=hub,
    role=role,
    transformers_version="4.37.0",
    pytorch_version="2.1.0",
    py_version="py310",
)

predictor = model.deploy(
    endpoint_name="embedding-bge-m3-endpoint",
    initial_instance_count=1,
    instance_type="ml.g4dn.xlarge",  # GPU
)
