import boto3
from typing import Dict, Optional
from .logger import Logger


class AWSSession:
    
    def __init__(self, region: str, profile_name: Optional[str] = None):
        self.region = region
        self.profile_name = profile_name
        self._identity_cache = None
        self._account_name_cache = None
        try:
            if profile_name:
                self.session = boto3.Session(profile_name=profile_name, region_name=region)
            else:
                self.session = boto3.Session(region_name=region)
        except Exception as e:
            Logger.error(f"Failed to create AWS session: {e}")
            raise
    
    def get_caller_identity(self) -> Dict[str, str]:
        if self._identity_cache:
            return self._identity_cache
        try:
            sts = self.session.client("sts", region_name=self.region)
            self._identity_cache = sts.get_caller_identity()
            return self._identity_cache
        except Exception as e:
            Logger.error(f"Failed to get caller identity: {e}")
            Logger.error("This usually means authentication failed or credentials expired", indent=1)
            raise
    
    def get_account_name(self) -> str:
        if self._account_name_cache:
            return self._account_name_cache
        
        identity = self.get_caller_identity()
        account_id = identity["Account"]
        
        try:
            iam = self.session.client("iam", region_name=self.region)
            response = iam.list_account_aliases()
            aliases = response.get("AccountAliases", [])
            if aliases:
                self._account_name_cache = aliases[0]
                return self._account_name_cache
        except Exception:
            pass
        
        try:
            organizations = self.session.client("organizations", region_name=self.region)
            response = organizations.describe_account(AccountId=account_id)
            account_name = response["Account"].get("Name", account_id)
            self._account_name_cache = account_name
            return self._account_name_cache
        except Exception:
            pass
        
        self._account_name_cache = account_id
        return self._account_name_cache
    
    def print_identity(self, account_id: str):
        try:
            identity = self.get_caller_identity()
            account_name = self.get_account_name()
            Logger.info(f"Account: {account_id} ({account_name}) | Region: {self.region}")
            Logger.info(f"UserId: {identity.get('UserId', 'N/A')}", indent=1)
            Logger.info(f"Arn: {identity.get('Arn', 'N/A')}", indent=1)
        except Exception as e:
            Logger.error(f"Failed to retrieve identity: {e}")
            raise
