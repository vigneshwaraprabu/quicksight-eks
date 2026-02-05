import os
import shutil
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Dict


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
            print(f"INFO: Backed up AWS config to {backup_path}")
    
    @staticmethod
    def setup_profiles(accounts_data: Dict[str, str]):
        SSOAuthenticator.backup_config()
        
        existing_content = ""
        if SSOAuthenticator.CONFIG_PATH.exists():
            existing_content = SSOAuthenticator.CONFIG_PATH.read_text()
        
        config_lines = []
        for account_id, role_name in accounts_data.items():
            profile_name = account_id
            if f"[profile {profile_name}]" not in existing_content:
                config_lines.extend([
                    f"[profile {profile_name}]",
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
            print(f"INFO: Added {len(accounts_data)} SSO profile(s) to AWS config")
        else:
            print("INFO: All SSO profiles already exist in AWS config")
    
    @staticmethod
    def authenticate(profile_name: str) -> bool:
        print(f"\nINFO: Starting AWS SSO login for profile '{profile_name}'")
        print("INFO: Browser will open for authentication")
        
        try:
            result = subprocess.run(
                ["aws", "sso", "login", "--profile", profile_name],
                capture_output=True,
                text=True,
                timeout=SSOAuthenticator.LOGIN_TIMEOUT
            )
            
            if result.returncode == 0:
                print("INFO: SSO login successful")
                return True
            else:
                print(f"ERROR: SSO login failed: {result.stderr}")
                return False
                
        except FileNotFoundError:
            print("ERROR: AWS CLI not found. Install with: pip install awscli")
            return False
        except subprocess.TimeoutExpired:
            print(f"ERROR: Login timed out after {SSOAuthenticator.LOGIN_TIMEOUT}s")
            return False
        except Exception as e:
            print(f"ERROR: SSO login error: {e}")
            return False
    
    @staticmethod
    def cleanup_cache():
        if not SSOAuthenticator.CACHE_PATH.exists():
            print("INFO: No SSO cache to clean up")
            return True
        
        try:
            shutil.rmtree(SSOAuthenticator.CACHE_PATH)
            print(f"INFO: Cleaned up SSO cache at {SSOAuthenticator.CACHE_PATH}")
            return True
        except Exception as e:
            print(f"WARNING: Failed to clean up SSO cache: {e}")
            return False
