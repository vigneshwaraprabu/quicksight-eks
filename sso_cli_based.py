import os
import json
import subprocess
from pathlib import Path
from typing import Dict, Optional, List
from datetime import datetime
import shutil

# =========================
# Config: accounts
# =========================
ACCOUNTS: Dict[str, Dict[str, str]] = {
    "853973692277": {"role": "limited-admin", "name": "presidio-sandbox"},
}

# AWS SSO Configuration
SSO_START_URL = "https://pcsg.awsapps.com/start/#/"
SSO_REGION = "us-east-1"

CONFIG_PATH = Path.home() / ".aws" / "config"

# =========================
# AWS CLI SSO Helpers
# =========================
def backup_file(path: Path) -> None:
    """Create a backup of an existing file."""
    if path.exists():
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = path.with_suffix(f".backup_{timestamp}")
        backup_path.write_text(path.read_text())
        print(f"📋 Backed up existing file to {backup_path}")


def setup_aws_config():
    """Create AWS config file with SSO profiles for each account."""
    backup_file(CONFIG_PATH)
    
    existing_content = ""
    if CONFIG_PATH.exists():
        existing_content = CONFIG_PATH.read_text()
    
    config_lines = []
    for account_id, meta in ACCOUNTS.items():
        profile_name = account_id
        if f"[profile {profile_name}]" not in existing_content:
            config_lines.append(f"[profile {profile_name}]")
            config_lines.append(f"sso_start_url = {SSO_START_URL}")
            config_lines.append(f"sso_region = {SSO_REGION}")
            config_lines.append(f"sso_account_id = {account_id}")
            config_lines.append(f"sso_role_name = {meta['role']}")
            config_lines.append(f"region = us-east-1")
            config_lines.append("")
    
    if config_lines:
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with CONFIG_PATH.open("a") as f:
            f.write("\n" + "\n".join(config_lines))
        print(f"✅ Added SSO profiles to {CONFIG_PATH}")
    else:
        print(f"ℹ️  All profiles already exist in {CONFIG_PATH}")


def run_sso_login() -> bool:
    """Run AWS SSO login via CLI."""
    print("\n🔐 Starting AWS SSO login...")
    print("This will open your browser for authentication.")
    
    try:
        profile = list(ACCOUNTS.keys())[0]
        result = subprocess.run(
            ["aws", "sso", "login", "--profile", profile],
            capture_output=True,
            text=True,
            timeout=300
        )
        
        if result.returncode == 0:
            print("✅ SSO login successful!")
            return True
        else:
            print(f"❌ SSO login failed: {result.stderr}")
            return False
    except FileNotFoundError:
        print("❌ AWS CLI not found. Please install it first:")
        print("   pip install awscli")
        return False
    except subprocess.TimeoutExpired:
        print("❌ Login timed out")
        return False
    except Exception as e:
        print(f"❌ Error during SSO login: {e}")
        return False


def describe_ec2_instances(account_id: str) -> Optional[List[Dict]]:
    """Run EC2 describe-instances command for a specific account."""
    try:
        print(f"\n🔍 Fetching EC2 instances for account {account_id} ...")
        result = subprocess.run(
            ["aws", "ec2", "describe-instances", "--profile", account_id, "--output", "json"],
            capture_output=True,
            text=True,
            timeout=60
        )
        
        if result.returncode != 0:
            print(f"❌ Failed to describe instances: {result.stderr}")
            return None
        
        data = json.loads(result.stdout)
        return data.get("Reservations", [])
    except subprocess.TimeoutExpired:
        print("❌ Command timed out")
        return None
    except json.JSONDecodeError as e:
        print(f"❌ Failed to parse JSON response: {e}")
        return None
    except Exception as e:
        print(f"❌ Error describing instances: {e}")
        return None


def print_ec2_instances(account_name: str, reservations: List[Dict]) -> None:
    """Pretty print EC2 instances information."""
    if not reservations:
        print(f"\n📋 No EC2 instances found in {account_name}.")
        return
    
    instance_count = sum(len(r.get("Instances", [])) for r in reservations)
    print(f"\n📋 Found {instance_count} EC2 instance(s) in {account_name}:\n")
    print("=" * 100)
    
    for reservation in reservations:
        for instance in reservation.get("Instances", []):
            instance_id = instance.get("InstanceId", "N/A")
            instance_type = instance.get("InstanceType", "N/A")
            state = instance.get("State", {}).get("Name", "N/A")
            launch_time = instance.get("LaunchTime", "N/A")
            
            name = "N/A"
            for tag in instance.get("Tags", []):
                if tag.get("Key") == "Name":
                    name = tag.get("Value", "N/A")
                    break
            
            private_ip = instance.get("PrivateIpAddress", "N/A")
            public_ip = instance.get("PublicIpAddress", "N/A")
            vpc_id = instance.get("VpcId", "N/A")
            subnet_id = instance.get("SubnetId", "N/A")
            
            print(f"Instance ID:    {instance_id}")
            print(f"Name:           {name}")
            print(f"Type:           {instance_type}")
            print(f"State:          {state}")
            print(f"Private IP:     {private_ip}")
            print(f"Public IP:      {public_ip}")
            print(f"VPC ID:         {vpc_id}")
            print(f"Subnet ID:      {subnet_id}")
            print(f"Launch Time:    {launch_time}")
            print("-" * 100)


def cleanup_sso_cache() -> bool:
    """Remove AWS SSO cache directory."""
    sso_cache_dir = Path.home() / ".aws" / "sso" / "cache"
    
    if not sso_cache_dir.exists():
        print("ℹ️  No SSO cache found to clean up.")
        return True
    
    try:
        shutil.rmtree(sso_cache_dir)
        print(f"✅ Cleaned up SSO cache at {sso_cache_dir}")
        return True
    except Exception as e:
        print(f"⚠️  Failed to clean up SSO cache: {e}")
        return False


# =========================
# Main
# =========================
def main():
    try:
        print("=" * 100)
        print("AWS SSO EC2 Instance Lister")
        print("=" * 100)
        
        # Step 1: Setup AWS config
        print("\n[Step 1/3] Setting up AWS configuration...")
        setup_aws_config()
        
        # Step 2: Authenticate via SSO
        print("\n[Step 2/3] Authenticating via AWS SSO...")
        if not run_sso_login():
            print("\n❌ Failed to authenticate. Exiting.")
            return 1
        
        # Step 3: List EC2 instances for all accounts
        print("\n[Step 3/3] Listing EC2 instances for all accounts...")
        print("=" * 100)
        
        for account_id, meta in ACCOUNTS.items():
            account_name = f"{meta['name']} [{account_id}]"
            reservations = describe_ec2_instances(account_id)
            
            if reservations is not None:
                print_ec2_instances(account_name, reservations)
            else:
                print(f"\n⚠️  Could not fetch EC2 instances for {account_name}")
        
        print("\n" + "=" * 100)
        print("✅ Done! All accounts processed.")
        print("=" * 100)
        
        # Step 4: Cleanup SSO cache
        print("\n[Cleanup] Removing SSO authentication cache...")
        cleanup_sso_cache()
        
        return 0
        
    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user. Exiting.")
        # Cleanup on interrupt as well
        cleanup_sso_cache()
        return 130
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        return 1


if __name__ == "__main__":
    exit(main())
