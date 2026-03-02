import csv
from datetime import datetime
from typing import List, Dict, Any
from .logger import Logger


class CSVHandler:
    
    HEADERS = [
        "AccountID", "AccountName", "Region", "ClusterName", "ClusterVersion",
        "InstanceID", "Current_AMI_ID", "Current_AMI_Publication_Date", "AMI_Age(in days)", 
        "OS_Version", "InstanceType", "NodeState", "NodeUptime", 
        "Latest_AMI_ID", "New_AMI_Publication_Date", "PatchPendingStatus",
        "NodeReadinessStatus", "Cluster_Compliance", "Audit_Timestamp"
    ]
    
    @staticmethod
    def write_cluster_data(output_file: str, data: List[Dict[str, Any]]):
        if not data:
            Logger.warning("No data to write")
            return
        
        # Add current date as Audit_Timestamp to each row
        current_date = datetime.now().strftime("%d/%m/%y")
        for row in data:
            row["Audit_Timestamp"] = current_date
        
        try:
            with open(output_file, 'w', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=CSVHandler.HEADERS)
                writer.writeheader()
                writer.writerows(data)
            Logger.success(f"Results written to {output_file}")
        except Exception as e:
            Logger.error(f"Failed to write CSV: {e}")
