"""
test_sagemaker_embedding.py
Test AWS SageMaker BGE-M3 Embedding Endpoint

Run this BEFORE starting your application to verify:
✅ AWS credentials are configured
✅ SageMaker endpoint is accessible
✅ Embeddings are generated correctly
✅ Dimension matches Milvus (1024)
"""

import sys
import os
import boto3
import json
import time
from typing import List

# ✅ CRITICAL: Load .env file FIRST
try:
    from dotenv import load_dotenv
    load_dotenv()  # Load environment variables from .env file
    print("✅ Loaded .env file")
except ImportError:
    print("⚠️  python-dotenv not installed, skipping .env loading")
    print("   Install with: pip install python-dotenv")

# ✅ Verify AWS credentials are loaded
if os.getenv("AWS_ACCESS_KEY_ID"):
    print(f"✅ AWS_ACCESS_KEY_ID loaded: {os.getenv('AWS_ACCESS_KEY_ID')[:10]}...")
else:
    print("❌ AWS_ACCESS_KEY_ID not found in environment")

if os.getenv("AWS_SECRET_ACCESS_KEY"):
    print(f"✅ AWS_SECRET_ACCESS_KEY loaded: ***hidden***")
else:
    print("❌ AWS_SECRET_ACCESS_KEY not found in environment")

print()

# Colors for terminal output
class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    RESET = '\033[0m'

def print_success(msg: str):
    print(f"{Colors.GREEN}✅ {msg}{Colors.RESET}")

def print_error(msg: str):
    print(f"{Colors.RED}❌ {msg}{Colors.RESET}")

def print_warning(msg: str):
    print(f"{Colors.YELLOW}⚠️  {msg}{Colors.RESET}")

def print_info(msg: str):
    print(f"{Colors.BLUE}ℹ️  {msg}{Colors.RESET}")


class SageMakerEmbeddingTester:
    """Test SageMaker embedding endpoint"""
    
    def __init__(
        self,
        endpoint_name: str = "embedding-bge-m3-endpoint",
        region_name: str = "ap-south-1"
    ):
        self.endpoint_name = endpoint_name
        self.region_name = region_name
        self.expected_dimension = 1024  # BGE-M3 dimension
        
        print_info(f"Endpoint: {endpoint_name}")
        print_info(f"Region: {region_name}")
        print()
    
    def test_aws_credentials(self) -> bool:
        """Test 1: Check AWS credentials"""
        print("=" * 60)
        print("TEST 1: AWS Credentials")
        print("=" * 60)
        
        try:
            session = boto3.Session()
            credentials = session.get_credentials()
            
            if credentials is None:
                print_error("No AWS credentials found!")
                print_warning("Configure credentials using one of:")
                print("   - AWS CLI: aws configure")
                print("   - Environment variables: AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY")
                print("   - IAM role (if running on EC2)")
                return False
            
            print_success("AWS credentials found")
            print_info(f"Access Key: {credentials.access_key[:10]}...")
            
            # Test STS to verify credentials work
            sts = boto3.client('sts', region_name=self.region_name)
            identity = sts.get_caller_identity()
            print_info(f"Account ID: {identity['Account']}")
            print_info(f"User ARN: {identity['Arn']}")
            
            return True
            
        except Exception as e:
            print_error(f"AWS credentials check failed: {e}")
            return False
    
    def test_endpoint_exists(self) -> bool:
        """Test 2: Check if endpoint exists"""
        print("\n" + "=" * 60)
        print("TEST 2: SageMaker Endpoint Existence")
        print("=" * 60)
        
        try:
            client = boto3.client('sagemaker', region_name=self.region_name)
            
            response = client.describe_endpoint(EndpointName=self.endpoint_name)
            
            status = response['EndpointStatus']
            
            if status == 'InService':
                print_success(f"Endpoint is InService")
            elif status == 'Creating':
                print_warning(f"Endpoint is still Creating")
            else:
                print_warning(f"Endpoint status: {status}")
            
            print_info(f"Endpoint ARN: {response['EndpointArn']}")
            print_info(f"Created: {response['CreationTime']}")
            
            return status == 'InService'
            
        except client.exceptions.ClientError as e:
            if 'Could not find endpoint' in str(e):
                print_error(f"Endpoint '{self.endpoint_name}' does not exist!")
                print_warning("Check endpoint name or deploy the model first")
            else:
                print_error(f"Error: {e}")
            return False
        except Exception as e:
            print_error(f"Unexpected error: {e}")
            return False
    def unwrap_embeddings(self, result):
        """
        Unwrap nested SageMaker embedding responses like [[[[embedding]]]]
        Returns: List[List[float]]
        """
        unwrapped = result

        while (
            isinstance(unwrapped, list)
            and len(unwrapped) == 1
            and isinstance(unwrapped[0], list)
        ):
            # Stop if this level is the actual embedding
            if (
                len(unwrapped[0]) > 0
                and isinstance(unwrapped[0][0], (int, float))
            ):
                break

            unwrapped = unwrapped[0]

        return unwrapped

    def test_single_embedding(self) -> bool:
        """Test 3: Generate single embedding"""
        print("\n" + "=" * 60)
        print("TEST 3: Single Text Embedding")
        print("=" * 60)
        
        test_text = "This is a test sentence for embedding generation."
        print_info(f"Test text: '{test_text}'")
        
        try:
            client = boto3.client('sagemaker-runtime', region_name=self.region_name)
            
            payload = {"inputs": [test_text]}
            
            print_info("Calling SageMaker endpoint...")
            start_time = time.time()
            
            response = client.invoke_endpoint(
                EndpointName=self.endpoint_name,
                ContentType="application/json",
                Body=json.dumps(payload)
            )
            
            elapsed_time = time.time() - start_time
            
            result = json.loads(response["Body"].read().decode())
            
            # DEBUG: Show response structure
            print_info(f"Response type: {type(result)}")
            print_info(f"Response structure: {str(result)[:200]}...")
            
            if isinstance(result, list):
                print_info(f"Result is a list with {len(result)} items")
                if len(result) > 0:
                    print_info(f"First item type: {type(result[0])}")
                    if isinstance(result[0], dict):
                        print_info(f"First item keys: {result[0].keys()}")
                    elif isinstance(result[0], list):
                        print_info(f"First item length: {len(result[0])}")
            elif isinstance(result, dict):
                print_info(f"Result is a dict with keys: {result.keys()}")
            
            # Extract embedding
            embedding = None
            
            if isinstance(result, list):
                if isinstance(result[0], list):
                    embeddings = self.unwrap_embeddings(result)
                    embedding = embeddings[0]

                elif isinstance(result[0], dict):
                    # Try common keys
                    for key in ['embedding', 'embeddings', 'dense_vecs', 'vector']:
                        if key in result[0]:
                            embedding = result[0][key]
                            print_info(f"Found embedding in key: {key}")
                            break
            elif isinstance(result, dict):
                for key in ['embeddings', 'dense_vecs', 'vectors', 'output']:
                    if key in result:
                        if isinstance(result[key], list):
                            embedding = result[key][0] if isinstance(result[key][0], list) else result[key]
                            print_info(f"Found embedding in key: {key}")
                            break
            
            if embedding is None:
                print_error(f"Could not extract embedding from response")
                print_info(f"Full response: {json.dumps(result, indent=2)[:500]}")
                return False
            
            # Validate dimension
            if len(embedding) != self.expected_dimension:
                print_error(
                    f"Wrong dimension! Expected {self.expected_dimension}, "
                    f"got {len(embedding)}"
                )
                print_info(f"Embedding sample: {embedding[:10]}")
                return False
            
            print_success(f"Embedding generated in {elapsed_time:.2f}s")
            print_info(f"Dimension: {len(embedding)}")
            print_info(f"Sample values: {embedding[:5]}")
            
            # Check if embedding is not all zeros
            if all(v == 0.0 for v in embedding):
                print_warning("Embedding is all zeros!")
                return False
            
            return True
            
        except Exception as e:
            print_error(f"Embedding generation failed: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def test_batch_embedding(self) -> bool:
        """Test 4: Generate batch embeddings"""
        print("\n" + "=" * 60)
        print("TEST 4: Batch Embedding")
        print("=" * 60)
        
        test_texts = [
            "Norwegian company law regulates business activities.",
            "Aksjeloven gjelder for aksjeselskaper i Norge.",
            "Legal compliance is important for all companies."
        ]
        
        print_info(f"Testing with {len(test_texts)} texts")
        
        try:
            client = boto3.client('sagemaker-runtime', region_name=self.region_name)
            
            payload = {"inputs": test_texts}
            
            print_info("Calling SageMaker endpoint...")
            start_time = time.time()
            
            response = client.invoke_endpoint(
                EndpointName=self.endpoint_name,
                ContentType="application/json",
                Body=json.dumps(payload)
            )
            
            elapsed_time = time.time() - start_time
            
            result = json.loads(response["Body"].read().decode())
            
            # Extract embeddings
            if isinstance(result, list):
                embeddings = self.unwrap_embeddings(result)
                embeddings = embeddings[2]
            elif isinstance(result, dict) and "embeddings" in result:
                embeddings = result["embeddings"]
            else:
                print_error(f"Unexpected response format: {type(result)}")
                return False
            
            # Validate count
            if len(embeddings) != len(test_texts):
                print_error(
                    f"Wrong count! Expected {len(test_texts)}, "
                    f"got {len(embeddings)}"
                )
                return False
            
            # Validate dimensions
            for i, emb in enumerate(embeddings):
                if len(emb) != self.expected_dimension:
                    print_error(
                        f"Embedding {i}: Wrong dimension! "
                        f"Expected {self.expected_dimension}, got {len(emb)}"
                    )
                    return False
            
            print_success(f"Batch embeddings generated in {elapsed_time:.2f}s")
            print_info(f"Average time per text: {elapsed_time / len(test_texts):.3f}s")
            print_info(f"All {len(embeddings)} embeddings have correct dimension")
            
            return True
            
        except Exception as e:
            print_error(f"Batch embedding failed: {e}")
            return False
    
    def test_norwegian_text(self) -> bool:
        """Test 5: Norwegian legal text"""
        print("\n" + "=" * 60)
        print("TEST 5: Norwegian Legal Text")
        print("=" * 60)
        
        norwegian_text = (
            "§ 1-1. Lovens virkeområde\n"
            "Loven gjelder for aksjeselskaper som er stiftet i Norge."
        )
        
        print_info(f"Test text: {norwegian_text[:50]}...")
        
        try:
            client = boto3.client('sagemaker-runtime', region_name=self.region_name)
            
            payload = {"inputs": [norwegian_text]}
            
            response = client.invoke_endpoint(
                EndpointName=self.endpoint_name,
                ContentType="application/json",
                Body=json.dumps(payload)
            )
            
            result = json.loads(response["Body"].read().decode())
            
            if isinstance(result, list):
                embeddings = self.unwrap_embeddings(result)
                embedding = embeddings[0]

            elif isinstance(result, dict) and "embeddings" in result:
                embedding = result["embeddings"][0]
            else:
                print_error(f"Unexpected response format")
                return False
            
            if len(embedding) != self.expected_dimension:
                print_error(f"Wrong dimension: {len(embedding)}")
                return False
            
            print_success("Norwegian text embedded successfully")
            print_info(f"Dimension: {len(embedding)}")
            
            return True
            
        except Exception as e:
            print_error(f"Norwegian text embedding failed: {e}")
            return False
    
    def run_all_tests(self) -> bool:
        """Run all tests"""
        print("\n" + "🚀 " * 20)
        print("SAGEMAKER EMBEDDING ENDPOINT TEST SUITE")
        print("🚀 " * 20 + "\n")
        
        tests = [
            ("AWS Credentials", self.test_aws_credentials),
            ("Endpoint Exists", self.test_endpoint_exists),
            ("Single Embedding", self.test_single_embedding),
            ("Batch Embedding", self.test_batch_embedding),
            ("Norwegian Text", self.test_norwegian_text),
        ]
        
        results = []
        
        for test_name, test_func in tests:
            try:
                result = test_func()
                results.append((test_name, result))
            except Exception as e:
                print_error(f"Test '{test_name}' crashed: {e}")
                results.append((test_name, False))
        
        # Summary
        print("\n" + "=" * 60)
        print("TEST SUMMARY")
        print("=" * 60)
        
        for test_name, result in results:
            if result:
                print_success(f"{test_name}: PASSED")
            else:
                print_error(f"{test_name}: FAILED")
        
        passed = sum(1 for _, result in results if result)
        total = len(results)
        
        print("\n" + "=" * 60)
        if passed == total:
            print_success(f"ALL TESTS PASSED ({passed}/{total})")
            print_success("SageMaker endpoint is ready for production!")
            return True
        else:
            print_error(f"SOME TESTS FAILED ({passed}/{total} passed)")
            print_warning("Fix the issues above before using in production")
            return False


if __name__ == "__main__":
    # Configuration
    ENDPOINT_NAME = "embedding-bge-m3-endpoint"
    REGION_NAME = "ap-south-1"
    
    # Allow override from command line
    if len(sys.argv) > 1:
        ENDPOINT_NAME = sys.argv[1]
    if len(sys.argv) > 2:
        REGION_NAME = sys.argv[2]
    
    # Run tests
    tester = SageMakerEmbeddingTester(
        endpoint_name=ENDPOINT_NAME,
        region_name=REGION_NAME
    )
    
    success = tester.run_all_tests()
    
    sys.exit(0 if success else 1)