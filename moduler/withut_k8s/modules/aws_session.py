import boto3
from typing import Dict, Optional
from .logger import Logger


class AWSSession:
    
    # Static map of Account ID to Account Name
    # ACCOUNT_NAME_MAP = {
    #     "175504091457": "MMPay - QA",
    #     "212055980189": "Global - MM K8s",
    #     "983058792752": "MMI - Sandbox - MM K8s Performance",
    #     "874823723256": "MMI - Production - EMA Primary",
    #     "556664958801": "MMPay - Staging",
    #     "170478468157": "MMPay - Production",
    #     "562238536321": "MMI - Production - MM K8s",
    #     "244564253140": "MMI - QA - MM K8s",
    #     "125190407919": "MMI - Sandbox - MM K8s Dev",
    #     # Add more account mappings here as needed
    # }
    ACCOUNT_NAME_MAP = {
        "491210323927": "master-payer",
        "908676838269": "security-audit",
        "017145527355": "security-log-archive",
        "794617637947": "digit-exp-prod-corpit",
        "448266111448": "digit-exp-prod-corpops",
        "891612581829": "digit-exp-sandbox-corpit",
        "759888234558": "global-account-factory",
        "650251707215": "global-identity-center",
        "920373008061": "global-ipam",
        "300759652823": "global-domain",
        "182399726717": "global-deployment",
        "212055980189": "global-mmk8s",
        "734989938994": "global-network",
        "941377128799": "klara-infrastructure-global-network",
        "390844777265": "klara-infrastructure-deployment",
        "539247485890": "klara-infrastructure-production-network",
        "985539763473": "klara-infrastructure-rc-network",
        "145023115632": "klara-infrastructure-staging-network",
        "888577048142": "klara-production",
        "215788330218": "klara-production-live",
        "619071333237": "klara-rc",
        "140023363330": "klara-sandbox-nebula",
        "137068238505": "klara-staging",
        "253490785039": "klara-staging-qa",
        "825200688358": "mmema-prod-common",
        "690099127610": "mmema-prod",
        "202413277349": "mmema-rc",
        "909208902952": "mmema-sbx",
        "568790269670": "mmema-stg",
        "013218823041": "mmi-mmema-infra-deployment",
        "518955992879": "mmi-production-big-data-services",
        "874823723256": "mmi-production-ema-primary",
        "562238536321": "mmi-production-mmk8s",
        "897138222775": "mmi-qa-ema-pods",
        "244564253140": "mmi-qa-mmk8s",
        "555756951579": "mmi-qa-modmed",
        "924796780481": "mmi-qa-performance",
        "258531305540": "mmi-qa-ept-rnd",
        "326229876344": "mmi-sandbox-mmic",
        "125190407919": "mmi-sandbox-mmk8s-dev",
        "983058792752": "mmi-sandbox-mmk8s-performance",
        "495881025244": "mmi-sandbox-pd-dev",
        "862683271180": "mmi-sandbox-rnd",
        "257394454126": "mmpay-infra-deployment",
        "170478468157": "mmpay-production",
        "251624017305": "mmpay-prod-admin",
        "875197445074": "mmpay-prod-audit",
        "556664958801": "mmpay-staging",
        "175504091457": "mmpay-qa",
        "981921953115": "mmpay-sandbox-dev",
        "182072247589": "nexus-production-exscribe",
        "336696828319": "nexus-production-hydra",
        "021891587375": "nexus-production-management",
        "390778472690": "nexus-production-sammy",
        "340752796637": "nexus-production-xtract",
        "831580244187": "nexus-qa-hydra",
        "261841207250": "nexus-qa-sammy",
        "021891587884": "nexus-qa-xtract",
        "391043916181": "nexus-sandbox-exscribe",
        "554215901947": "nexus-sandbox-gi",
        "884038419676": "mminfra-prod-common",
        "785711437471": "mminfra-stg",
        "601326494725": "mminfra-sbx",
        "540728771764": "mmrcm-prod-common",
        "778011348283": "mmrcm-prod",
        "473398166784": "mmrcm-rc",
        "955409238874": "mmrcm-stg",
        "644993687176": "mmrcm-sbx",
        "586463628218": "vault-ggastro-s3-backup",
        "615299731386": "vault-klara",
        "102303256311": "vault-modmed-s3",
        "424876277441": "vault-modmed-db",
        "468629753286": "vault-xtract",
        "525375333093": "vault-fusion",
        "514160713140": "vendor-data-databricks",
        "839955467748": "mmorm-prod-common",
        "538494148365": "mmorm-prod",
        "259361437637": "mmorm-rc",
        "534321188268": "mmorm-stg",
        "253484721364": "mmorm-sbx",
        "954328706842": "mmauth-prod-common",
        "268836234485": "mmauth-prod",
        "860945038745": "mmauth-rc",
        "202508219200": "mmauth-stg",
        "035842753393": "mmauth-sbx",
        "348664921377": "mmsecurity-prod",
        "526680396749": "mmsecurity-sbx",
        "958533308928": "mmfhir-prod-common",
        "065789377350": "mmfhir-prod",
        "489491974256": "mmfhir-rc",
        "615763500983": "mmfhir-stg",
        "780573890979": "mmfhir-sbx",
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
