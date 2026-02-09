import csv
from typing import List, Dict, Any
from .logger import Logger


class CSVHandler:
    
    HEADERS = [
        "AccountID", "AccountName", "Region", "ClusterName", "ClusterVersion",
        "InstanceID", "AMI_ID", "AMI_Age", "OS_Version", "InstanceType",
        "NodeState", "NodeUptime", "Latest_EKS_AMI", "PatchPendingStatus",
        "NodeReadinessStatus"
    ]
    
    @staticmethod
    def read_accounts(csv_file: str) -> List[Dict[str, str]]:
        accounts = []
        try:
            with open(csv_file, 'r', newline='') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    account_id = row["account_id"].strip()
                    
                    if "role_name" not in row or not row["role_name"].strip():
                        Logger.error(f"role_name is required for account {account_id}")
                        continue
                    
                    role_name = row["role_name"].strip()
                    regions = [r.strip() for r in row["region"].strip().split(",") if r.strip()]
                    accounts.extend({
                        "account_id": account_id,
                        "role_name": role_name,
                        "region": region
                    } for region in regions)
            return accounts
        except FileNotFoundError:
            Logger.error(f"CSV file '{csv_file}' not found")
            return []
        except KeyError as e:
            Logger.error(f"Missing required column in CSV: {e}")
            return []
        except Exception as e:
            Logger.error(f"Failed to read CSV file: {e}")
            return []
    
    @staticmethod
    def write_cluster_data(output_file: str, data: List[Dict[str, Any]]):
        if not data:
            Logger.warning("No data to write")
            return
        
        try:
            with open(output_file, 'w', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=CSVHandler.HEADERS)
                writer.writeheader()
                writer.writerows(data)
            Logger.success(f"Results written to {output_file}")
        except Exception as e:
            Logger.error(f"Failed to write CSV: {e}")
