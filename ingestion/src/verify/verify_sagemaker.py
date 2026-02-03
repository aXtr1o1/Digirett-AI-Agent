"""
SageMaker Endpoint Verification Script
Tests if BGE-M3 endpoint is deployed and working correctly

IMPORTANT: Update REGION to match where your endpoint is deployed
"""

import boto3
import json
import logging

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
logger = logging.getLogger("sagemaker-verify")

# ============================================================================
# CONFIGURATION - UPDATE THIS TO YOUR REGION
# ============================================================================

ENDPOINT_NAME = "embedding-bge-m3-endpoint"

# ⚠️ CHANGE THIS TO YOUR REGION!
# Common regions:
# - "us-east-1" (Virginia)
# - "us-west-2" (Oregon)
# - "eu-west-1" (Ireland)
# - "ap-south-1" (Mumbai) ← YOUR REGION
# - "ap-southeast-1" (Singapore)

REGION = "ap-south-1"  # ← UPDATE THIS!

# ============================================================================


def verify_sagemaker_endpoint():
    """
    Checks if SageMaker endpoint exists and is working.
    """
    
    logger.info("=" * 70)
    logger.info("🔍 SAGEMAKER ENDPOINT VERIFICATION")
    logger.info("=" * 70)
    logger.info(f"   Endpoint: {ENDPOINT_NAME}")
    logger.info(f"   Region: {REGION}")
    
    # ========================================================================
    # STEP 1: Check endpoint exists and status
    # ========================================================================
    
    try:
        sm_client = boto3.client('sagemaker', region_name=REGION)
        
        logger.info("\n📡 Checking endpoint status...")
        
        response = sm_client.describe_endpoint(
            EndpointName=ENDPOINT_NAME
        )
        
        status = response['EndpointStatus']
        creation_time = response['CreationTime']
        instance_type = response.get('ProductionVariants', [{}])[0].get('InstanceType', 'N/A')
        
        logger.info(f"   ✅ Endpoint exists")
        logger.info(f"   Status: {status}")
        logger.info(f"   Created: {creation_time}")
        logger.info(f"   Instance: {instance_type}")
        
        if status != 'InService':
            logger.error(f"   ❌ Endpoint is not ready! Status: {status}")
            logger.info("   Wait for endpoint to be 'InService' before using it.")
            return False
        
        logger.info("   ✅ Endpoint is InService (ready to use)")
        
    except sm_client.exceptions.ClientError as e:
        error_message = str(e)
        
        if 'Could not find endpoint' in error_message:
            logger.error(f"   ❌ Endpoint '{ENDPOINT_NAME}' does not exist in region '{REGION}'!")
            
            # Check if endpoint exists in other regions
            logger.info("\n🔍 Checking other regions...")
            check_other_regions(ENDPOINT_NAME)
            
            logger.info("\n   To deploy the endpoint in this region, run:")
            logger.info("   python model-deploy.py")
            return False
        else:
            logger.error(f"   ❌ Error checking endpoint: {e}")
            return False
    
    except Exception as e:
        logger.error(f"   ❌ Unexpected error: {e}")
        return False
    
    # ========================================================================
    # STEP 2: Test inference
    # ========================================================================
    
    logger.info("\n🧪 Testing inference...")
    
    try:
        runtime_client = boto3.client('sagemaker-runtime', region_name=REGION)
        
        # Test with Norwegian legal text
        test_texts = [
            "Dette er en test av norsk juridisk tekst.",
            "Aksjeloven regulerer aksjeselskaper i Norge."
        ]
        
        payload = {
            "inputs": test_texts
        }
        
        logger.info(f"   Sending {len(test_texts)} test texts...")
        
        response = runtime_client.invoke_endpoint(
            EndpointName=ENDPOINT_NAME,
            ContentType='application/json',
            Body=json.dumps(payload)
        )
        
        result = json.loads(response['Body'].read().decode())
        
        logger.info(f"   ✅ Inference successful!")
        
        # Check response format
        if isinstance(result, list) and len(result) == len(test_texts):
            embeddings = result
        elif isinstance(result, dict):
            if 'embeddings' in result:
                embeddings = result['embeddings']
            elif 'dense_vecs' in result:
                embeddings = result['dense_vecs']
            elif 'predictions' in result:
                embeddings = result['predictions']
            else:
                logger.error(f"   ❌ Unexpected response format: {result.keys()}")
                return False
        else:
            logger.error(f"   ❌ Unexpected response type: {type(result)}")
            return False
        
        logger.info(f"   Response format: {type(result).__name__}")
        logger.info(f"   Number of embeddings: {len(embeddings)}")
        logger.info(f"   Embedding dimension: {len(embeddings[0])}")
        
        # Verify dimension
        if len(embeddings[0]) == 1024:
            logger.info("   ✅ Correct dimension (BGE-M3 = 1024)")
        else:
            logger.warning(f"   ⚠️ Unexpected dimension: {len(embeddings[0])} (expected 1024)")
        
        # Show sample values
        logger.info(f"   Sample values (first 5): {embeddings[0][:5]}")
        
    except Exception as e:
        logger.error(f"   ❌ Inference test failed: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False
    
    # ========================================================================
    # STEP 3: Check costs
    # ========================================================================
    
    logger.info("\n💰 COST INFORMATION")
    logger.info("   Instance type: ml.g4dn.xlarge")
    logger.info("   Estimated cost: ~$0.70/hour (~$500/month if running 24/7)")
    logger.info("   ⚠️ Remember to DELETE endpoint when not in use to save costs!")
    logger.info(f"   Delete command: aws sagemaker delete-endpoint --endpoint-name {ENDPOINT_NAME} --region {REGION}")
    
    # ========================================================================
    # SUCCESS
    # ========================================================================
    
    logger.info("\n" + "=" * 70)
    logger.info("✅ SAGEMAKER ENDPOINT IS READY TO USE!")
    logger.info("=" * 70)
    logger.info("\nYou can now run the test pipeline:")
    logger.info("   python main_test.py")
    
    return True


def check_other_regions(endpoint_name):
    """Check if endpoint exists in other common regions."""
    common_regions = [
        "us-east-1",
        "us-west-2", 
        "eu-west-1",
        "ap-south-1",
        "ap-southeast-1",
        "eu-central-1"
    ]
    
    found_regions = []
    
    for region in common_regions:
        if region == REGION:
            continue
            
        try:
            sm = boto3.client('sagemaker', region_name=region)
            sm.describe_endpoint(EndpointName=endpoint_name)
            found_regions.append(region)
        except:
            pass
    
    if found_regions:
        logger.info(f"\n   ✅ Found endpoint in these regions: {', '.join(found_regions)}")
        logger.info(f"\n   💡 Update the REGION variable in this script to: \"{found_regions[0]}\"")
        logger.info(f"      Or set it in your environment/config files")
    else:
        logger.info("   No endpoint found in common regions")


if __name__ == "__main__":
    verify_sagemaker_endpoint()