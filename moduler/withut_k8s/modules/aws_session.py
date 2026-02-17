import boto3
from typing import Dict, Optional
from .logger import Logger


class AWSSession:
    
    # Static map of Account ID to Account Name
    ACCOUNT_NAME_MAP = {
        "175504091457": "MMPay - QA",
        "212055980189": "Global - MM K8s",
        "983058792752": "MMI - Sandbox - MM K8s Performance",
        "874823723256": "MMI - Production - EMA Primary",
        "556664958801": "MMPay - Staging",
        "170478468157": "MMPay - Production",
        "562238536321": "MMI - Production - MM K8s",
        "244564253140": "MMI - QA - MM K8s",
        "125190407919": "MMI - Sandbox - MM K8s Dev",
        # Add more account mappings here as needed
    }
    
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
        
        # Look up account name from static map, default to account ID if not found
        self._account_name_cache = self.ACCOUNT_NAME_MAP.get(account_id, account_id)
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
