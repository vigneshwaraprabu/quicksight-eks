import boto3
from typing import Dict


class AWSSession:
    
    def __init__(self, region: str):
        self.region = region
        self.session = boto3.Session(region_name=region)
    
    def get_caller_identity(self) -> Dict[str, str]:
        sts = self.session.client("sts", region_name=self.region)
        return sts.get_caller_identity()
    
    def print_identity(self, account_id: str):
        identity = self.get_caller_identity()
        print(f"INFO: Account: {account_id} | Region: {self.region} | "
              f"UserId: {identity['UserId']} | Arn: {identity['Arn']}")
