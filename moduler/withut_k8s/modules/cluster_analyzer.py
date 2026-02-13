from typing import List, Dict, Any
from .eks_operations import EKSOperations
from .node_operations import NodeOperations
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
        # Kubernetes operations removed - requires cluster authentication access
    
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
        
        latest_supported_version = self.eks_ops.get_latest_supported_version()
        Logger.info(f"Latest supported EKS version: {latest_supported_version}", indent=1)
        
        latest_amis, error = self.eks_ops.get_latest_amis(cluster_version)
        if error:
            Logger.warning(f"Error fetching latest AMIs: {error}", indent=1)
        
        Logger.info("Fetching node details", indent=1)
        nodes, instance_ids = self.node_ops.get_cluster_nodes(cluster_name)
        
        if not nodes:
            Logger.info("No running nodes found", indent=1)
            return [self._create_empty_row(account_id, account_name, cluster_name, cluster_version, latest_supported_version)]
        
        Logger.success(f"Found {len(nodes)} node(s)", indent=1)
        
        # Skip Kubernetes readiness check (requires EKS cluster authentication)
        readiness_map = {iid: "N/A" for iid in instance_ids}
        
        # Log OS distribution for this cluster
        os_distribution = {}
        for node in nodes:
            os_ver = node.get("OS_Version", "Unknown")
            os_distribution[os_ver] = os_distribution.get(os_ver, 0) + 1
        Logger.info(f"OS distribution: {', '.join([f'{os}: {count}' for os, count in os_distribution.items()])}", indent=1)
        
        results = []
        for node in nodes:
            node_data = self._process_node(account_id, account_name, cluster_name, cluster_version, 
                                          node, latest_amis, readiness_map, latest_supported_version)
            results.append(node_data)
            Logger.info(f"Instance {node['InstanceID']}: {node['InstanceType']} "
                  f"({node.get('OS_Version', 'N/A')})", indent=2)
        
        return results
    
    def _process_node(self, account_id: str, account_name: str, cluster_name: str, cluster_version: str,
                     node: Dict, latest_amis: Dict, readiness_map: Dict, latest_supported_version: str) -> Dict[str, Any]:
        try:
            os_version = node.get("OS_Version", "Unknown")
            os_key = self.OS_MAPPING.get(os_version)
            
            latest_ami_id = "N/A"
            new_ami_publication_date = "N/A"
            if os_key and os_key in latest_amis:
                ami_info = latest_amis[os_key]
                latest_ami_id = ami_info.get("ami_id", "N/A")
                new_ami_publication_date = ami_info.get("publication_date", "N/A")
                Logger.debug(f"Node {node.get('InstanceID', 'N/A')}: Matched OS '{os_version}' to AMI {latest_ami_id}", indent=3)
            else:
                if os_version == "Unknown":
                    Logger.warning(f"OS version unknown for node {node.get('InstanceID', 'N/A')} - cannot determine latest AMI", indent=3)
                elif not os_key:
                    Logger.warning(f"No OS mapping for '{os_version}' on node {node.get('InstanceID', 'N/A')}", indent=3)
                elif os_key not in latest_amis:
                    Logger.warning(f"No AMI data available for OS '{os_version}' (path: {os_key})", indent=3)
            
            instance_id = node.get("InstanceID", "N/A")
            compliance = self.eks_ops.check_cluster_compliance(cluster_version, latest_supported_version)
            
            return {
                "AccountID": account_id,
                "AccountName": account_name,
                "Region": self.region,
                "ClusterName": cluster_name,
                "ClusterVersion": cluster_version,
                "InstanceID": instance_id,
                "Current_AMI_ID": node.get("Current_AMI_ID", "N/A"),
                "Current_AMI_Publication_Date": node.get("Current_AMI_Publication_Date", "N/A"),
                "AMI_Age(in days)": node.get("AMI_Age", "N/A"),
                "OS_Version": os_version,
                "InstanceType": node.get("InstanceType", "N/A"),
                "NodeState": node.get("NodeState", "N/A"),
                "NodeUptime": node.get("NodeUptime", "N/A"),
                "Latest_AMI_ID": latest_ami_id,
                "New_AMI_Publication_Date": new_ami_publication_date,
                "PatchPendingStatus": self.node_ops.get_patch_status(node.get("AMI_Age", "N/A")),
                "NodeReadinessStatus": readiness_map.get(instance_id, "Unknown"),
                "Cluster_Compliance": compliance
            }
        except Exception as e:
            Logger.warning(f"Error processing node data: {e}", indent=2)
            return self._create_empty_row(account_id, account_name, cluster_name, cluster_version)
    
    def _create_empty_row(self, account_id: str, account_name: str, cluster_name: str, 
                         cluster_version: str, latest_supported_version: str) -> Dict[str, Any]:
        base_data = {
            "AccountID": account_id,
            "AccountName": account_name,
            "Region": self.region,
            "ClusterName": cluster_name,
            "ClusterVersion": cluster_version
        }
        empty_fields = dict.fromkeys([
            "InstanceID", "Current_AMI_ID", "Current_AMI_Publication_Date", "AMI_Age(in days)", 
            "OS_Version", "InstanceType", "NodeState", "NodeUptime", 
            "Latest_AMI_ID", "New_AMI_Publication_Date", "PatchPendingStatus",
            "NodeReadinessStatus"
        ], "N/A")
        
        # Set AMI_Age to 0 for clusters with no nodes
        empty_fields["AMI_Age(in days)"] = "0"
        # Set PatchPendingStatus to 0 for clusters with no nodes
        empty_fields["PatchPendingStatus"] = "0"
        
        compliance = self.eks_ops.check_cluster_compliance(cluster_version, latest_supported_version)
        empty_fields["Cluster_Compliance"] = compliance
        
        return {**base_data, **empty_fields}
