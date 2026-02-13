import os
import shutil
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Dict
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
    def authenticate(profile_name: str) -> bool:
        Logger.blank()
        Logger.info(f"Starting AWS SSO login for profile '{profile_name}'")
        Logger.info("Browser will open for authentication", indent=1)
        
        try:
            result = subprocess.run(
                ["aws", "sso", "login", "--profile", profile_name],
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
                    Logger.error(f"Profile '{profile_name}' not found in AWS config")
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
