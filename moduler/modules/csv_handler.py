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
                
                if not reader.fieldnames:
                    Logger.error("CSV file is empty or has no headers")
                    return []
                
                required_columns = {"account_id", "role_name", "region"}
                missing_columns = required_columns - set(reader.fieldnames)
                if missing_columns:
                    Logger.error(f"CSV missing required columns: {', '.join(missing_columns)}")
                    return []
                
                line_num = 1
                for row in reader:
                    line_num += 1
                    
                    account_id = row.get("account_id", "").strip()
                    if not account_id:
                        Logger.warning(f"Line {line_num}: Empty account_id, skipping row")
                        continue
                    
                    if not account_id.isdigit() or len(account_id) != 12:
                        Logger.warning(f"Line {line_num}: Invalid account_id '{account_id}' (must be 12 digits), skipping")
                        continue
                    
                    role_name = row.get("role_name", "").strip()
                    if not role_name:
                        Logger.error(f"Line {line_num}: role_name is required for account {account_id}, skipping")
                        continue
                    
                    region_value = row.get("region", "").strip()
                    if not region_value:
                        Logger.error(f"Line {line_num}: region is required for account {account_id}, skipping")
                        continue
                    
                    regions = [r.strip() for r in region_value.split(",") if r.strip()]
                    if not regions:
                        Logger.error(f"Line {line_num}: No valid regions found for account {account_id}, skipping")
                        continue
                    
                    for region in regions:
                        if not region.startswith(("us-", "eu-", "ap-", "sa-", "ca-", "me-", "af-")):
                            Logger.warning(f"Line {line_num}: Region '{region}' may be invalid for account {account_id}")
                        
                        accounts.append({
                            "account_id": account_id,
                            "role_name": role_name,
                            "region": region
                        })
                
                if not accounts:
                    Logger.error("No valid accounts found in CSV file")
                    
            return accounts
        except FileNotFoundError:
            Logger.error(f"CSV file '{csv_file}' not found")
            return []
        except KeyError as e:
            Logger.error(f"Missing required column in CSV: {e}")
            return []
        except PermissionError:
            Logger.error(f"Permission denied reading CSV file '{csv_file}'")
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
