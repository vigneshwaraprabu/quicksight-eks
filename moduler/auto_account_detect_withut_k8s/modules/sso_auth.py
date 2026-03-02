import os
import shutil
import subprocess
import boto3
from pathlib import Path
from datetime import datetime
from typing import Dict, List
from botocore.exceptions import ClientError
from .logger import Logger


class SSOAuthenticator:
    
    SSO_START_URL = "https://d-9067ab41c2.awsapps.com/start/#/"
    SSO_REGION = "us-east-1"
    CONFIG_PATH = Path.home() / ".aws" / "config"
    CACHE_PATH = Path.home() / ".aws" / "sso" / "cache"
    LOGIN_TIMEOUT = 300
    
    @staticmethod
    def backup_config():
        if SSOAuthenticator.CONFIG_PATH.exists():
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = SSOAuthenticator.CONFIG_PATH.with_suffix(f".backup_{timestamp}")
            backup_path.write_text(SSOAuthenticator.CONFIG_PATH.read_text())
            Logger.info(f"Backed up AWS config to {backup_path}")
    
    @staticmethod
    def setup_profiles(accounts_data: Dict[str, str]):
        SSOAuthenticator.backup_config()
        
        existing_content = SSOAuthenticator.CONFIG_PATH.read_text() if SSOAuthenticator.CONFIG_PATH.exists() else ""
        
        config_lines = []
        profiles_to_add = 0
        for account_id, role_name in accounts_data.items():
            if f"[profile {account_id}]" not in existing_content:
                profiles_to_add += 1
                config_lines.extend([
                    f"[profile {account_id}]",
                    f"sso_start_url = {SSOAuthenticator.SSO_START_URL}",
                    f"sso_region = {SSOAuthenticator.SSO_REGION}",
                    f"sso_account_id = {account_id}",
                    f"sso_role_name = {role_name}",
                    f"region = us-east-1",
                    ""
                ])
        
        if config_lines:
            SSOAuthenticator.CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
            with SSOAuthenticator.CONFIG_PATH.open("a") as f:
                f.write("\n" + "\n".join(config_lines))
            Logger.success(f"Added {profiles_to_add} SSO profile(s) to AWS config")
        else:
            Logger.info("All SSO profiles already exist in AWS config")
    
    @staticmethod
    def authenticate(profile_name: str = None) -> bool:
        Logger.blank()
        
        if profile_name:
            Logger.info(f"Starting AWS SSO login for profile '{profile_name}'")
        else:
            Logger.info("Starting AWS SSO login")
        
        Logger.info("Browser will open for authentication", indent=1)
        
        try:
            cmd = ["aws", "sso", "login"]
            if profile_name:
                cmd.extend(["--profile", profile_name])
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=SSOAuthenticator.LOGIN_TIMEOUT
            )
            
            if result.returncode == 0:
                Logger.success("SSO login successful")
                return True
            else:
                error_msg = result.stderr.strip()
                if "Could not find profile" in error_msg:
                    if profile_name:
                        Logger.error(f"Profile '{profile_name}' not found in AWS config")
                    else:
                        Logger.error("No default profile found in AWS config")
                    Logger.error("Run: aws configure sso", indent=1)
                elif "sso_start_url" in error_msg:
                    Logger.error("Invalid SSO configuration. Check sso_start_url and sso_region")
                elif "access token" in error_msg.lower():
                    Logger.error("SSO session expired. Please authenticate again")
                else:
                    Logger.error(f"SSO login failed: {error_msg}")
                Logger.error("Try running: aws sso login manually to diagnose", indent=1)
                return False
                
        except FileNotFoundError:
            Logger.error("AWS CLI not found. Install with: pip install awscli or brew install awscli")
            return False
        except subprocess.TimeoutExpired:
            Logger.error(f"Login timed out after {SSOAuthenticator.LOGIN_TIMEOUT}s")
            Logger.error("User may not have completed browser authentication", indent=1)
            return False
        except PermissionError:
            Logger.error("Permission denied executing AWS CLI")
            return False
        except Exception as e:
            Logger.error(f"SSO login error: {e}")
            return False
    
    @staticmethod
    def cleanup_cache():
        if not SSOAuthenticator.CACHE_PATH.exists():
            Logger.info("No SSO cache to clean up")
            return True
        
        try:
            shutil.rmtree(SSOAuthenticator.CACHE_PATH)
            Logger.success(f"Cleaned up SSO cache at {SSOAuthenticator.CACHE_PATH}")
            return True
        except Exception as e:
            Logger.warning(f"Failed to clean up SSO cache: {e}")
            return False
    
    @staticmethod
    def discover_accounts() -> List[str]:
        """
        Discover all AWS accounts accessible via the current SSO session.
        Uses AWS CLI to list accounts from SSO (no Organizations API needed).
        Returns a list of account IDs.
        """
        try:
            Logger.info("Discovering accessible AWS accounts from SSO...")
            
            # Use AWS CLI to list accounts accessible via SSO
            result = subprocess.run(
                ["aws", "sso", "list-accounts"],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode != 0:
                Logger.error("Failed to list SSO accounts")
                Logger.error(f"Error: {result.stderr.strip()}", indent=1)
                Logger.blank()
                Logger.info("Falling back to parsing AWS config profiles...", indent=1)
                return SSOAuthenticator._discover_from_config()
            
            # Parse JSON output
            import json
            accounts_data = json.loads(result.stdout)
            
            account_ids = []
            for account in accounts_data:
                account_id = account.get('accountId')
                account_name = account.get('accountName', 'N/A')
                if account_id:
                    account_ids.append(account_id)
                    Logger.info(f"  • {account_id} ({account_name})", indent=1)
            
            if account_ids:
                Logger.success(f"Discovered {len(account_ids)} account(s) from SSO")
                return account_ids
            else:
                Logger.warning("No accounts found via SSO")
                return []
                
        except FileNotFoundError:
            Logger.error("AWS CLI not found")
            return []
        except json.JSONDecodeError:
            Logger.warning("Failed to parse SSO accounts, trying config fallback...")
            return SSOAuthenticator._discover_from_config()
        except Exception as e:
            Logger.error(f"Unexpected error discovering accounts: {e}")
            Logger.info("Trying config fallback...", indent=1)
            return SSOAuthenticator._discover_from_config()
    
    @staticmethod
    def _discover_from_config() -> List[str]:
        """
        Fallback: Parse account IDs from existing AWS config profiles.
        """
        account_ids = []
        try:
            if SSOAuthenticator.CONFIG_PATH.exists():
                config_content = SSOAuthenticator.CONFIG_PATH.read_text()
                lines = config_content.split('\n')
                
                for line in lines:
                    line = line.strip()
                    if line.startswith('sso_account_id'):
                        account_id = line.split('=')[1].strip()
                        if account_id and account_id not in account_ids:
                            account_ids.append(account_id)
                            Logger.info(f"  • {account_id} (from config)", indent=1)
                
                if account_ids:
                    Logger.success(f"Found {len(account_ids)} account(s) from AWS config")
                    return account_ids
                else:
                    Logger.error("No SSO accounts found in AWS config")
            else:
                Logger.error("AWS config file not found")
        except Exception as e:
            Logger.error(f"Failed to parse config: {e}")
        
        return []
