import boto3
from typing import Optional
from botocore.exceptions import ClientError
from .logger import Logger


class RoleAssumption:
    """
    Handles AWS role assumption for GitHub Actions workflow.
    
    Flow:
    1. GitHub Actions assumes base role (via OIDC)
    2. This class assumes target account roles from the base role
    3. Separate method for assuming S3 upload role
    """
    
    # Hardcoded S3 upload account and role
    S3_UPLOAD_ACCOUNT = "853973692277"
    S3_UPLOAD_ROLE = "PatchingAccess"
    
    def __init__(self):
        """Initialize with base session (GitHub Actions assumed role)"""
        self.base_session = boto3.Session()
        self.sts_client = self.base_session.client('sts')
        Logger.debug("Initialized RoleAssumption with base session")
    
    def assume_role(self, account_id: str, role_name: str, region: str, 
                    session_name: Optional[str] = None) -> Optional[boto3.Session]:
        """
        Assume a role in a target account from the base GitHub Actions role.
        
        Args:
            account_id: AWS account ID to assume role in
            role_name: IAM role name to assume
            region: AWS region for the session
            session_name: Optional custom session name
        
        Returns:
            boto3.Session with assumed role credentials, or None if failed
        """
        role_arn = f"arn:aws:iam::{account_id}:role/{role_name}"
        
        if session_name is None:
            session_name = f"EKSAnalyzer-{account_id}"
        
        try:
            Logger.info(f"Assuming role: {role_arn}", indent=1)
            
            response = self.sts_client.assume_role(
                RoleArn=role_arn,
                RoleSessionName=session_name,
                DurationSeconds=3600  # 1 hour
            )
            
            credentials = response['Credentials']
            
            # Create a new session with assumed role credentials
            assumed_session = boto3.Session(
                aws_access_key_id=credentials['AccessKeyId'],
                aws_secret_access_key=credentials['SecretAccessKey'],
                aws_session_token=credentials['SessionToken'],
                region_name=region
            )
            
            Logger.success(f"Successfully assumed role in account {account_id}", indent=1)
            return assumed_session
            
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', 'Unknown')
            error_message = e.response.get('Error', {}).get('Message', str(e))
            
            if error_code == 'AccessDenied':
                Logger.error(f"Access denied assuming role {role_arn}", indent=1)
                Logger.error("Check that:", indent=2)
                Logger.error(f"1. Role {role_name} exists in account {account_id}", indent=3)
                Logger.error("2. Trust policy allows base role to assume it", indent=3)
                Logger.error("3. Base role has sts:AssumeRole permission", indent=3)
            elif error_code == 'InvalidClientTokenId':
                Logger.error("Invalid AWS credentials", indent=1)
                Logger.error("Check GitHub Actions OIDC configuration", indent=2)
            elif error_code == 'ExpiredToken':
                Logger.error("AWS credentials expired", indent=1)
                Logger.error("Check GitHub Actions token refresh", indent=2)
            else:
                Logger.error(f"Failed to assume role {role_arn}: {error_message}", indent=1)
            
            return None
            
        except Exception as e:
            Logger.error(f"Unexpected error assuming role {role_arn}: {e}", indent=1)
            return None
    
    def assume_s3_upload_role(self, region: str = "us-east-1") -> Optional[boto3.Session]:
        """
        Assume the hardcoded S3 upload role.
        
        Args:
            region: AWS region for the session (default: us-east-1)
        
        Returns:
            boto3.Session with assumed role credentials, or None if failed
        """
        Logger.info(f"Assuming S3 upload role in account {self.S3_UPLOAD_ACCOUNT}")
        return self.assume_role(
            account_id=self.S3_UPLOAD_ACCOUNT,
            role_name=self.S3_UPLOAD_ROLE,
            region=region,
            session_name="EKSAnalyzer-S3Upload"
        )
    
    def get_base_caller_identity(self) -> dict:
        """
        Get the caller identity of the base session (GitHub Actions role).
        
        Returns:
            Dictionary with Account, UserId, and Arn, or empty dict on error
        """
        try:
            response = self.sts_client.get_caller_identity()
            return response
        except Exception as e:
            Logger.error(f"Failed to get base caller identity: {e}")
            return {}
