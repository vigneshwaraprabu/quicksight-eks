import boto3
from typing import Dict, Optional


class AWSSession:
    
    def __init__(self, region: str, profile_name: Optional[str] = None):
        self.region = region
        self.profile_name = profile_name
        if profile_name:
            self.session = boto3.Session(profile_name=profile_name, region_name=region)
        else:
            self.session = boto3.Session(region_name=region)
    
    def get_caller_identity(self) -> Dict[str, str]:
        sts = self.session.client("sts", region_name=self.region)
        return sts.get_caller_identity()
    
    def get_account_name(self) -> str:
        try:
            iam = self.session.client("iam", region_name=self.region)
            response = iam.list_account_aliases()
            aliases = response.get("AccountAliases", [])
            if aliases:
                return aliases[0]
        except Exception:
            pass
        
        try:
            organizations = self.session.client("organizations", region_name=self.region)
            account_id = self.get_caller_identity()["Account"]
            response = organizations.describe_account(AccountId=account_id)
            return response["Account"].get("Name", account_id)
        except Exception:
            pass
        
        return self.get_caller_identity()["Account"]
    
    def print_identity(self, account_id: str):
        identity = self.get_caller_identity()
        account_name = self.get_account_name()
        print(f"INFO: Account: {account_id} ({account_name}) | Region: {self.region} | "
              f"UserId: {identity['UserId']} | Arn: {identity['Arn']}")
