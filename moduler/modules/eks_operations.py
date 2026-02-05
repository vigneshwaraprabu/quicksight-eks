from typing import List, Dict, Tuple
from botocore.exceptions import ClientError


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
    
    def list_clusters(self) -> List[str]:
        try:
            paginator = self.eks_client.get_paginator("list_clusters")
            clusters = []
            for page in paginator.paginate():
                clusters.extend(page.get("clusters", []))
            return clusters
        except ClientError as e:
            print(f"ERROR: Failed to list EKS clusters in {self.region}: {e}")
            return []
    
    def get_cluster_version(self, cluster_name: str) -> str:
        try:
            response = self.eks_client.describe_cluster(name=cluster_name)
            return response["cluster"]["version"]
        except ClientError:
            return "N/A"
    
    def get_latest_amis(self, version: str) -> Tuple[Dict[str, str], str]:
        os_amis = {}
        try:
            for os_path in self.OS_PATHS:
                param_name = f"/aws/service/eks/optimized-ami/{version}/{os_path}/recommended/image_id"
                try:
                    response = self.ssm_client.get_parameter(Name=param_name)
                    os_amis[os_path] = response["Parameter"]["Value"]
                except ClientError:
                    continue
            return os_amis, ""
        except ClientError as e:
            return {}, str(e)
