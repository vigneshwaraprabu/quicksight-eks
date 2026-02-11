from typing import List, Dict, Tuple
from botocore.exceptions import ClientError
from .logger import Logger


class EKSOperations:
    
    OS_PATHS = [
        "amazon-linux-2/x86_64/standard",
        "amazon-linux-2023/x86_64/standard",
        "bottlerocket/x86_64/standard",
        "ubuntu/x86_64/standard",
    ]
    
    def __init__(self, session, region: str):
        self.session = session
        self.region = region
        self.eks_client = session.client("eks", region_name=region)
        self.ssm_client = session.client("ssm", region_name=region)
        self.ec2_client = session.client("ec2", region_name=region)
    
    def list_clusters(self) -> List[str]:
        try:
            paginator = self.eks_client.get_paginator("list_clusters")
            clusters = []
            for page in paginator.paginate():
                clusters.extend(page.get("clusters", []))
            return clusters
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', 'Unknown')
            if error_code == 'AccessDeniedException':
                Logger.error(f"Access denied to list EKS clusters in {self.region}")
                Logger.error("Check IAM permissions: eks:ListClusters", indent=1)
            elif error_code == 'ExpiredTokenException':
                Logger.error("AWS credentials expired. Re-authenticate with SSO")
            elif error_code == 'InvalidParameterException':
                Logger.error(f"Invalid region '{self.region}' for EKS")
            else:
                Logger.error(f"Failed to list EKS clusters in {self.region}: {e}")
            return []
    
    def get_cluster_version(self, cluster_name: str) -> str:
        try:
            response = self.eks_client.describe_cluster(name=cluster_name)
            return response.get("cluster", {}).get("version", "N/A")
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', 'Unknown')
            if error_code == 'ResourceNotFoundException':
                Logger.warning(f"Cluster '{cluster_name}' not found", indent=1)
            elif error_code == 'AccessDeniedException':
                Logger.warning(f"Access denied to describe cluster '{cluster_name}'", indent=1)
            else:
                Logger.warning(f"Failed to get version for cluster '{cluster_name}': {e}", indent=1)
            return "N/A"
        except Exception:
            return "N/A"
    
    def get_latest_supported_version(self) -> str:
        try:
            for version in range(40, 20, -1):
                version_str = f"1.{version}"
                test_param = f"/aws/service/eks/optimized-ami/{version_str}/amazon-linux-2023/x86_64/standard/recommended/image_id"
                try:
                    self.ssm_client.get_parameter(Name=test_param)
                    Logger.debug(f"Latest supported EKS version found: {version_str}", indent=2)
                    return version_str
                except ClientError:
                    continue
            return "1.31"
        except Exception:
            return "1.31"
    
    @staticmethod
    def check_cluster_compliance(cluster_version: str, latest_version: str) -> str:
        try:
            if cluster_version == "N/A" or latest_version == "N/A":
                return "0"
            
            cluster_minor = int(cluster_version.split(".")[1])
            latest_minor = int(latest_version.split(".")[1])
            
            if cluster_minor >= (latest_minor - 2):
                return "1"
            else:
                return "0"
        except Exception:
            return "0"
    
    def get_latest_amis(self, version: str) -> Tuple[Dict[str, Dict[str, str]], str]:
        os_amis = {}
        errors = []
        try:
            Logger.info(f"Fetching latest AMIs for EKS version {version}", indent=1)
            
            ami_ids_to_describe = []
            ami_to_os_map = {}
            
            for os_path in self.OS_PATHS:
                ami_id_param = f"/aws/service/eks/optimized-ami/{version}/{os_path}/recommended/image_id"
                try:
                    ami_response = self.ssm_client.get_parameter(Name=ami_id_param)
                    ami_id = ami_response["Parameter"]["Value"]
                    os_amis[os_path] = {
                        "ami_id": ami_id,
                        "publication_date": "N/A"
                    }
                    ami_ids_to_describe.append(ami_id)
                    ami_to_os_map[ami_id] = os_path
                    Logger.debug(f"Found AMI for {os_path}: {ami_id}", indent=2)
                except ClientError as e:
                    error_code = e.response.get('Error', {}).get('Code', 'Unknown')
                    error_msg = f"{os_path}: {error_code}"
                    errors.append(error_msg)
                    Logger.debug(f"SSM parameter not found: {ami_id_param}", indent=2)
            
            if not os_amis:
                error_summary = f"No AMI data found for version {version}. Errors: {', '.join(errors)}"
                Logger.warning(error_summary, indent=1)
                return {}, error_summary
            
            if ami_ids_to_describe:
                try:
                    Logger.debug(f"Describing {len(ami_ids_to_describe)} AMI(s) to get publication dates", indent=2)
                    ami_details = self.ec2_client.describe_images(ImageIds=ami_ids_to_describe)
                    for image in ami_details.get("Images", []):
                        ami_id = image.get("ImageId")
                        creation_date = image.get("CreationDate")
                        if ami_id in ami_to_os_map:
                            os_path = ami_to_os_map[ami_id]
                            if creation_date:
                                from datetime import datetime
                                try:
                                    creation_dt = datetime.fromisoformat(creation_date.replace('Z', '+00:00'))
                                    formatted_date = creation_dt.strftime("%Y-%m-%d")
                                    os_amis[os_path]["publication_date"] = formatted_date
                                except Exception:
                                    os_amis[os_path]["publication_date"] = "N/A"
                except ClientError as e:
                    Logger.warning(f"Failed to describe AMIs for publication dates: {e}", indent=2)
            
            Logger.success(f"Found AMI data for {len(os_amis)} OS type(s)", indent=1)
            return os_amis, ""
        except ClientError as e:
            error_msg = f"SSM client error: {str(e)}"
            Logger.error(error_msg, indent=1)
            return {}, error_msg
        except Exception as e:
            error_msg = f"Unexpected error fetching AMIs: {str(e)}"
            Logger.error(error_msg, indent=1)
            return {}, error_msg
