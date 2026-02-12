from typing import List, Dict, Tuple
from datetime import datetime, timezone
from botocore.exceptions import ClientError
from .logger import Logger


class NodeOperations:
    
    PATCH_THRESHOLD_DAYS = 30
    
    def __init__(self, session, region: str):
        self.session = session
        self.region = region
        self.ec2_client = session.client("ec2", region_name=region)
    
    def get_cluster_nodes(self, cluster_name: str) -> Tuple[List[Dict], List[str]]:
        try:
            filters = [
                {"Name": "instance-state-name", "Values": ["running"]},
                {"Name": f"tag:kubernetes.io/cluster/{cluster_name}", "Values": ["owned", "shared"]}
            ]
            
            nodes, ami_ids, instance_ids = [], set(), []
            paginator = self.ec2_client.get_paginator("describe_instances")
            
            for page in paginator.paginate(Filters=filters):
                for reservation in page.get("Reservations", []):
                    for instance in reservation.get("Instances", []):
                        instance_id = instance.get("InstanceId")
                        if not instance_id:
                            Logger.warning("Found instance without InstanceId, skipping", indent=1)
                            continue
                        
                        ami_id = instance.get("ImageId")
                        if ami_id:
                            ami_ids.add(ami_id)
                        
                        instance_ids.append(instance_id)
                        nodes.append({
                            "InstanceID": instance_id,
                            "Current_AMI_ID": ami_id or "N/A",
                            "InstanceType": instance.get("InstanceType", "N/A"),
                            "NodeState": instance.get("State", {}).get("Name", "N/A"),
                            "NodeUptime": self._calculate_uptime(instance.get("LaunchTime"))
                        })
            
            if ami_ids:
                self._enrich_with_ami_data(nodes, list(ami_ids))
            
            return nodes, instance_ids
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', 'Unknown')
            if error_code == 'UnauthorizedOperation':
                Logger.error(f"Access denied to describe EC2 instances for cluster {cluster_name}")
                Logger.error("Check IAM permissions: ec2:DescribeInstances", indent=1)
            else:
                Logger.error(f"Failed to get nodes for cluster {cluster_name}: {e}")
            return [], []
    
    def _enrich_with_ami_data(self, nodes: List[Dict], ami_ids: List[str]):
        ami_data = self._get_ami_info(ami_ids)
        for node in nodes:
            if node["Current_AMI_ID"] in ami_data:
                ami_info = ami_data[node["Current_AMI_ID"]]
                node["AMI_Age"] = self._calculate_ami_age(ami_info.get("CreationDate"))
                node["Current_AMI_Publication_Date"] = self._format_publication_date(ami_info.get("CreationDate"))
                node["OS_Version"] = self._parse_os_version(ami_info.get("Description", ""))
            else:
                node["AMI_Age"] = "N/A"
                node["Current_AMI_Publication_Date"] = "N/A"
                node["OS_Version"] = "N/A"
    
    def _get_ami_info(self, ami_ids: List[str]) -> Dict[str, Dict]:
        try:
            response = self.ec2_client.describe_images(ImageIds=ami_ids)
            return {img["ImageId"]: {
                "CreationDate": img.get("CreationDate"),
                "Description": img.get("Description", "")
            } for img in response.get("Images", [])}
        except ClientError:
            return {}
    
    @staticmethod
    def _calculate_uptime(launch_time) -> str:
        if not launch_time:
            return "N/A"
        try:
            delta = datetime.now(timezone.utc) - launch_time.replace(tzinfo=timezone.utc)
            days, remainder = delta.days, delta.seconds
            hours = remainder // 3600
            return f"{days} days {hours} hours"
        except Exception:
            return "N/A"
    
    @staticmethod
    def _calculate_ami_age(creation_date_str: str) -> str:
        if not creation_date_str:
            return "N/A"
        try:
            creation_date = datetime.fromisoformat(creation_date_str.replace('Z', '+00:00'))
            delta = datetime.now(timezone.utc) - creation_date
            return f"{delta.days} days"
        except Exception:
            return "N/A"
    
    @staticmethod
    def _format_publication_date(creation_date_str: str) -> str:
        if not creation_date_str:
            return "N/A"
        try:
            creation_date = datetime.fromisoformat(creation_date_str.replace('Z', '+00:00'))
            return creation_date.strftime("%Y-%m-%d")
        except Exception:
            return "N/A"
    
    @staticmethod
    def _parse_os_version(description: str) -> str:
        desc_lower = description.lower()
        os_map = {
            "amazon linux 2023": "Amazon Linux 2023",
            "amazon linux 2": "Amazon Linux 2",
            "bottlerocket": "Bottlerocket",
            "ubuntu": "Ubuntu"
        }
        for key, value in os_map.items():
            if key in desc_lower:
                return value
        return "Unknown"
    
    @staticmethod
    def get_patch_status(ami_age_str: str) -> str:
        if ami_age_str and ami_age_str != "N/A":
            try:
                days = int(ami_age_str.split()[0])
                return "True" if days >= NodeOperations.PATCH_THRESHOLD_DAYS else "False"
            except (ValueError, IndexError):
                pass
        return "False"
