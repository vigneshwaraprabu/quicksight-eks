from typing import List, Dict, Any
from .eks_operations import EKSOperations
from .node_operations import NodeOperations
from .kubernetes_operations import KubernetesOperations
from .logger import Logger


class ClusterAnalyzer:
    
    OS_MAPPING = {
        "Amazon Linux 2": "amazon-linux-2/x86_64/standard",
        "Amazon Linux 2023": "amazon-linux-2023/x86_64/standard",
        "Bottlerocket": "bottlerocket/x86_64/standard",
        "Ubuntu": "ubuntu/x86_64/standard"
    }
    
    def __init__(self, session, region: str):
        self.session = session
        self.region = region
        self.eks_ops = EKSOperations(session, region)
        self.node_ops = NodeOperations(session, region)
        self.k8s_ops = KubernetesOperations(session, region)
    
    def analyze_clusters(self, account_id: str, account_name: str = None) -> List[Dict[str, Any]]:
        if account_name is None:
            account_name = account_id
        
        clusters = self.eks_ops.list_clusters()
        
        if not clusters:
            Logger.info("No EKS clusters found")
            return []
        
        Logger.success(f"Found {len(clusters)} cluster(s)")
        results = []
        
        for cluster_name in clusters:
            Logger.subsection(f"Analyzing cluster: {cluster_name}")
            cluster_results = self._analyze_single_cluster(account_id, account_name, cluster_name)
            results.extend(cluster_results)
        
        return results
    
    def _analyze_single_cluster(self, account_id: str, account_name: str, cluster_name: str) -> List[Dict[str, Any]]:
        cluster_version = self.eks_ops.get_cluster_version(cluster_name)
        Logger.info(f"Version: {cluster_version}", indent=1)
        
        latest_amis, error = self.eks_ops.get_latest_amis(cluster_version)
        if error:
            Logger.warning(f"Error fetching latest AMIs: {error}", indent=1)
        
        Logger.info("Fetching node details", indent=1)
        nodes, instance_ids = self.node_ops.get_cluster_nodes(cluster_name)
        
        if not nodes:
            Logger.info("No running nodes found", indent=1)
            return [self._create_empty_row(account_id, account_name, cluster_name, cluster_version)]
        
        Logger.success(f"Found {len(nodes)} node(s)", indent=1)
        readiness_map = self.k8s_ops.get_node_readiness(instance_ids, cluster_name)
        
        results = []
        for node in nodes:
            node_data = self._process_node(account_id, account_name, cluster_name, cluster_version, 
                                          node, latest_amis, readiness_map)
            results.append(node_data)
            Logger.info(f"Instance {node['InstanceID']}: {node['InstanceType']} "
                  f"({node.get('OS_Version', 'N/A')})", indent=2)
        
        return results
    
    def _process_node(self, account_id: str, account_name: str, cluster_name: str, cluster_version: str,
                     node: Dict, latest_amis: Dict, readiness_map: Dict) -> Dict[str, Any]:
        os_version = node.get("OS_Version", "Unknown")
        os_key = self.OS_MAPPING.get(os_version)
        latest_ami = latest_amis.get(os_key, "N/A") if latest_amis and os_key else "N/A"
        patch_status = self.node_ops.get_patch_status(node.get("AMI_Age", "N/A"))
        readiness_status = readiness_map.get(node["InstanceID"], "Unknown")
        
        return {
            "AccountID": account_id,
            "AccountName": account_name,
            "Region": self.region,
            "ClusterName": cluster_name,
            "ClusterVersion": cluster_version,
            "InstanceID": node.get("InstanceID", "N/A"),
            "AMI_ID": node.get("AMI_ID", "N/A"),
            "AMI_Age": node.get("AMI_Age", "N/A"),
            "OS_Version": os_version,
            "InstanceType": node.get("InstanceType", "N/A"),
            "NodeState": node.get("NodeState", "N/A"),
            "NodeUptime": node.get("NodeUptime", "N/A"),
            "Latest_EKS_AMI": latest_ami,
            "PatchPendingStatus": patch_status,
            "NodeReadinessStatus": readiness_status
        }
    
    def _create_empty_row(self, account_id: str, account_name: str, cluster_name: str, 
                         cluster_version: str) -> Dict[str, Any]:
        base_data = {
            "AccountID": account_id,
            "AccountName": account_name,
            "Region": self.region,
            "ClusterName": cluster_name,
            "ClusterVersion": cluster_version
        }
        empty_fields = dict.fromkeys([
            "InstanceID", "AMI_ID", "AMI_Age", "OS_Version", "InstanceType",
            "NodeState", "NodeUptime", "Latest_EKS_AMI", "PatchPendingStatus",
            "NodeReadinessStatus"
        ], "N/A")
        return {**base_data, **empty_fields}
