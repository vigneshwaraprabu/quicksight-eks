import csv
import boto3
from botocore.exceptions import ClientError
from datetime import datetime, timezone
import kubernetes.client as k8s
import kubernetes.config
import subprocess
import tempfile
import os
import shutil
from pathlib import Path

# =========================
# AWS SSO Configuration
# =========================
SSO_START_URL = "https://pcsg.awsapps.com/start/#/"  # Update with your SSO start URL
SSO_REGION = "us-east-1"  # Update with your SSO region
CONFIG_PATH = Path.home() / ".aws" / "config"

# =========================
# SSO Helper Functions
# =========================
def backup_file(path: Path) -> None:
    """Create a backup of an existing file."""
    if path.exists():
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = path.with_suffix(f".backup_{timestamp}")
        backup_path.write_text(path.read_text())
        print(f"📋 Backed up existing file to {backup_path}")

def setup_aws_config_for_accounts(accounts_data):
    """Create AWS config file with SSO profiles for each account from CSV."""
    backup_file(CONFIG_PATH)
    
    existing_content = ""
    if CONFIG_PATH.exists():
        existing_content = CONFIG_PATH.read_text()
    
    config_lines = []
    for account_id, role_name in accounts_data.items():
        profile_name = account_id
        if f"[profile {profile_name}]" not in existing_content:
            config_lines.append(f"[profile {profile_name}]")
            config_lines.append(f"sso_start_url = {SSO_START_URL}")
            config_lines.append(f"sso_region = {SSO_REGION}")
            config_lines.append(f"sso_account_id = {account_id}")
            config_lines.append(f"sso_role_name = {role_name}")
            config_lines.append(f"region = us-east-1")
            config_lines.append("")
    
    if config_lines:
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with CONFIG_PATH.open("a") as f:
            f.write("\n" + "\n".join(config_lines))
        print(f"✅ Added SSO profiles to {CONFIG_PATH}")
    else:
        print(f"ℹ️  All profiles already exist in {CONFIG_PATH}")

def run_sso_login(profile_name: str) -> bool:
    """Run AWS SSO login via CLI."""
    print("\n🔐 Starting AWS SSO login...")
    print("This will open your browser for authentication.")
    
    try:
        result = subprocess.run(
            ["aws", "sso", "login", "--profile", profile_name],
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
# EKS Analysis Functions
# =========================
def print_caller_identity(session, account_id, region):
    sts = session.client("sts", region_name=region)
    identity = sts.get_caller_identity()
    print(f"\n=== Account: {account_id} | Region: {region} | UserId: {identity['UserId']} | Arn: {identity['Arn']} ===")

def list_eks_clusters(session, region):
    try:
        eks = session.client("eks", region_name=region)
        paginator = eks.get_paginator("list_clusters")
        clusters = []
        for page in paginator.paginate():
            clusters.extend(page.get("clusters", []))
        return clusters
    except ClientError as e:
        print(f"❌ Failed to list EKS clusters in {region}: {e}")
        return []

def get_latest_eks_amis(session, region, version):
    os_paths = [
        "amazon-linux-2/x86_64/standard",
        "amazon-linux-2023/x86_64/standard",
        "bottlerocket/x86_64/standard",
        "ubuntu/x86_64/standard",
    ]
    os_amis = {}
    try:
        ssm = session.client("ssm", region_name=region)
        for os_path in os_paths:
            param_name = f"/aws/service/eks/optimized-ami/{version}/{os_path}/recommended/image_id"
            try:
                response = ssm.get_parameter(Name=param_name)
                os_amis[os_path] = response["Parameter"]["Value"]
            except ClientError:
                continue
        return os_amis, ""
    except ClientError as e:
        return {}, str(e)

def parse_ami_info(ami_info):
    creation_date_str = ami_info.get("CreationDate", 0)
    ami_age = 0
    if creation_date_str and creation_date_str != 0:
        try:
            creation_date = datetime.fromisoformat(creation_date_str.replace('Z', '+00:00'))
            now = datetime.now(timezone.utc)
            delta = now - creation_date
            ami_age = f"{delta.days} days"
        except Exception:
            ami_age = 0
    desc = str(ami_info.get("Description", "")).lower()
    if "amazon linux 2023" in desc:
        os_version = "Amazon Linux 2023"
    elif "amazon linux 2" in desc:
        os_version = "Amazon Linux 2"
    elif "bottlerocket" in desc:
        os_version = "Bottlerocket"
    elif "ubuntu" in desc:
        os_version = "Ubuntu"
    else:
        os_version = 0
    return ami_age, os_version

def get_node_readiness(instance_ids, cluster_name, region, session):
    kubeconfig_path = None
    
    # Save and restore credentials in a context manager style
    original_aws_env = {
        'AWS_ACCESS_KEY_ID': os.environ.get('AWS_ACCESS_KEY_ID'),
        'AWS_SECRET_ACCESS_KEY': os.environ.get('AWS_SECRET_ACCESS_KEY'),
        'AWS_SESSION_TOKEN': os.environ.get('AWS_SESSION_TOKEN'),
        'AWS_DEFAULT_REGION': os.environ.get('AWS_DEFAULT_REGION')
    }
    
    try:
        creds = session.get_credentials().get_frozen_credentials()
        
        # Debug
        sts = session.client("sts", region_name=region)
        identity = sts.get_caller_identity()
        print(f"🔍 Accessing EKS cluster '{cluster_name}' with identity: {identity['Arn']}")

        # Temporarily set environment for this operation only
        os.environ['AWS_ACCESS_KEY_ID'] = creds.access_key
        os.environ['AWS_SECRET_ACCESS_KEY'] = creds.secret_key
        os.environ['AWS_SESSION_TOKEN'] = creds.token
        os.environ['AWS_DEFAULT_REGION'] = region

        with tempfile.NamedTemporaryFile(delete=False, mode='w') as tmp:
            kubeconfig_path = tmp.name

        # Generate kubeconfig
        result = subprocess.run(
            ["aws", "eks", "update-kubeconfig", "--name", cluster_name, "--region", region, "--kubeconfig", kubeconfig_path],
            capture_output=True,
            text=True
        )
        
        if result.returncode != 0:
            print(f"❌ Failed to generate kubeconfig: {result.stderr}")
            return {iid: "Unknown" for iid in instance_ids}

        # Load and use kubeconfig
        kubernetes.config.load_kube_config(config_file=kubeconfig_path)
        v1 = k8s.CoreV1Api()
        k8s_nodes = v1.list_node()

        readiness_map = {}
        for node in k8s_nodes.items:
            provider_id = node.spec.provider_id
            if provider_id and provider_id.startswith("aws:///"):
                instance_id = provider_id.split("/")[-1]
                if instance_id in instance_ids:
                    conditions = node.status.conditions or []
                    ready = any(c.type == "Ready" and c.status == "True" for c in conditions)
                    readiness_map[instance_id] = "Ready" if ready else "NotReady"

        for iid in instance_ids:
            readiness_map.setdefault(iid, "Unknown")

        return readiness_map

    except k8s.ApiException as e:
        # Handle Kubernetes API exceptions without printing full traceback
        if e.status == 401:
            print(f"❌ Unauthorized access to cluster '{cluster_name}'. The IAM role may lack EKS access entries.")
        elif e.status == 403:
            print(f"❌ Forbidden access to cluster '{cluster_name}'. Check IAM permissions.")
        else:
            print(f"❌ Kubernetes API error for cluster '{cluster_name}': {e.reason}")
        return {iid: "Unknown" for iid in instance_ids}
    except Exception as e:
        print(f"❌ Failed to fetch node readiness for cluster '{cluster_name}': {str(e)}")
        return {iid: "Unknown" for iid in instance_ids}

    finally:
        # Always restore original environment
        for key, value in original_aws_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        
        if kubeconfig_path and os.path.exists(kubeconfig_path):
            try:
                os.remove(kubeconfig_path)
            except Exception:
                pass


def get_node_details(session, cluster_name, region):
    try:
        ec2 = session.client("ec2", region_name=region)
        filters = [
            {"Name": "instance-state-name", "Values": ["running"]},
            {"Name": f"tag:kubernetes.io/cluster/{cluster_name}", "Values": ["owned", "shared"]}
        ]
        paginator = ec2.get_paginator("describe_instances")
        nodes, ami_ids, instance_ids = [], set(), []
        for page in paginator.paginate(Filters=filters):
            for res in page.get("Reservations", []):
                for inst in res.get("Instances", []):
                    ami_id = inst.get("ImageId")
                    if ami_id:
                        ami_ids.add(ami_id)
                    instance_ids.append(inst["InstanceId"])
                    launch_time = inst.get("LaunchTime")
                    uptime = 0
                    if launch_time:
                        now = datetime.now(timezone.utc)
                        delta = now - launch_time.replace(tzinfo=timezone.utc)
                        days = delta.days
                        hours, _ = divmod(delta.seconds, 3600)
                        uptime = f"{days} days {hours} hours"
                    nodes.append({
                        "InstanceID": inst["InstanceId"],
                        "AMI_ID": ami_id if ami_id else 0,
                        "InstanceType": inst.get("InstanceType", 0),
                        "NodeState": inst.get("State", {}).get("Name", 0),
                        "NodeUptime": uptime
                    })
        ami_data = {}
        if ami_ids:
            ami_response = ec2.describe_images(ImageIds=list(ami_ids))
            for img in ami_response.get("Images", []):
                ami_data[img["ImageId"]] = {"CreationDate": img.get("CreationDate", 0), "Description": img.get("Description", "")}
        for node in nodes:
            ami_info = ami_data.get(node["AMI_ID"], {"CreationDate": 0, "Description": ""})
            node["AMI_Age"], node["OS_Version"] = parse_ami_info(ami_info)
        # readiness_map = get_node_readiness(instance_ids)
        readiness_map = get_node_readiness(instance_ids, cluster_name, region, session)

        for node in nodes:
            node["NodeReadinessStatus"] = readiness_map.get(node["InstanceID"], 0)
        return nodes
    except ClientError:
        return []

def get_cluster_version(session, cluster_name, region):
    try:
        eks = session.client("eks", region_name=region)
        return eks.describe_cluster(name=cluster_name)["cluster"]["version"]
    except ClientError:
        return "N/A"

def get_current_identity(region=None):
    return boto3.client("sts", region_name=region).get_caller_identity()

def get_patch_status(ami_age_str):
    if ami_age_str and "days" in str(ami_age_str):
        try:
            days = int(str(ami_age_str).split()[0])
            return "False" if days < 30 else "True"
        except Exception:
            return "False"
    return "False"

def write_node_row(writer, account_id, region, cluster, cluster_version, node, latest_ami, patch_status, node_readiness):
    # patch_status is already "True" or "False" from get_patch_status
    # Print actual readiness status if available, else 0
    readiness_val = node_readiness if node_readiness in ("Ready", "NotReady") else 0
    writer.writerow([
        account_id,
        region,
        cluster,
        cluster_version,
        node.get("InstanceID", 0) or 0,
        node.get("AMI_ID", 0) or 0,
        node.get("AMI_Age", 0) or 0,
        node.get("OS_Version", 0) or 0,
        node.get("InstanceType", 0) or 0,
        node.get("NodeState", 0) or 0,
        node.get("NodeUptime", 0) or 0,
        str(latest_ami) if latest_ami is not None else "0",
        patch_status,
        readiness_val
    ])

def process_clusters(session, writer, account_id, region):
    clusters = list_eks_clusters(session, region)
    print("EKS Clusters:")
    for c in clusters:
        cluster_version = get_cluster_version(session, c, region)
        latest_amis, error = get_latest_eks_amis(session, region, cluster_version)
        if error:
            print(f"Error fetching latest EKS AMIs for {region} cluster {c} (version {cluster_version}): {error}")
        elif not latest_amis:
            print(f"No latest EKS AMIs found for {region} cluster {c} (version {cluster_version})")
        else:
            for os_type, ami_id in latest_amis.items():
                print(f"Latest EKS AMI for {region} cluster {c} (version {cluster_version}, {os_type}): {ami_id}")
        nodes = get_node_details(session, c, region)
        if nodes:
            for node in nodes:
                os_version = str(node.get("OS_Version", "")).lower()
                os_key = {
                    "amazon linux 2": "amazon-linux-2/x86_64/standard",
                    "amazon linux 2023": "amazon-linux-2023/x86_64/standard",
                    "bottlerocket": "bottlerocket/x86_64/standard",
                    "ubuntu": "ubuntu/x86_64/standard"
                }.get(os_version, None)
                latest_ami = latest_amis.get(os_key, 0) if latest_amis and os_key else 0
                patch_status = get_patch_status(node.get("AMI_Age", 0))
                node_readiness = node.get("NodeReadinessStatus", 0)
                print(f" - {c}: Instance {node['InstanceID']} (AMI: {node['AMI_ID']}, Type: {node['InstanceType']})")
                write_node_row(writer, account_id, region, c, cluster_version, node, latest_ami, patch_status, node_readiness)
        else:
            print(f" - {c}: (no running nodes)")
            write_node_row(writer, account_id, region, c, cluster_version, {}, 0, 0, 0)
    if not clusters:
        print(" - (none found)")

def main():
    csv_file = "accounts_sso.csv"  # Expected columns: account_id, role_name, region
    output_file = "output_sso.csv"
    
    print("=" * 100)
    print("AWS SSO EKS Cluster Analysis")
    print("=" * 100)
    
    # Step 1: Read accounts from CSV
    print("\n[Step 1/4] Reading account information from CSV...")
    accounts_data = {}  # {account_id: role_name}
    account_regions = {}  # {account_id: [regions]}
    
    try:
        with open(csv_file, newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                account_id = row["account_id"].strip()
                role_name = row.get("role_name", "limited-admin").strip()  # Default role if not specified
                region_field = row["region"].strip()
                regions = [r.strip() for r in region_field.split(",") if r.strip()]
                
                accounts_data[account_id] = role_name
                account_regions[account_id] = regions
        
        print(f"✅ Found {len(accounts_data)} account(s) to process")
    except FileNotFoundError:
        print(f"❌ CSV file '{csv_file}' not found!")
        print(f"Expected format: account_id,role_name,region")
        return 1
    except Exception as e:
        print(f"❌ Error reading CSV file: {e}")
        return 1
    
    # Step 2: Setup AWS config with SSO profiles
    print("\n[Step 2/4] Setting up AWS SSO configuration...")
    setup_aws_config_for_accounts(accounts_data)
    
    # Step 3: Authenticate via SSO
    print("\n[Step 3/4] Authenticating via AWS SSO...")
    first_account = list(accounts_data.keys())[0]
    if not run_sso_login(first_account):
        print("\n❌ Failed to authenticate. Exiting.")
        return 1
    
    # Step 4: Process all accounts and regions
    print("\n[Step 4/4] Processing EKS clusters for all accounts...")
    print("=" * 100)
    
    with open(output_file, "w", newline="") as out_f:
        writer = csv.writer(out_f)
        writer.writerow([
            "AccountID", "Region", "ClusterName", "ClusterVersion",
            "InstanceID", "AMI_ID", "AMI_Age", "OS_Version", "InstanceType", "NodeState", "NodeUptime",
            "Latest_EKS_AMI", "PatchPendingStatus", "NodeReadinessStatus"
        ])
        
        for account_id, regions in account_regions.items():
            for region in regions:
                print(f"\n🔄 Processing account {account_id} ({region}) ...")
                try:
                    # Create session using SSO profile
                    session = boto3.Session(profile_name=account_id, region_name=region)
                    print_caller_identity(session, account_id, region)
                    process_clusters(session, writer, account_id, region)
                    print("✅ Success")
                except Exception as ex:
                    print(f"❌ Error processing account {account_id} in {region}: {ex}")
                print(f"REGION_SUMMARY: account={account_id} region={region}")
    
    print("\n" + "=" * 100)
    print(f"✅ Done! Results written to {output_file}")
    print("=" * 100)
    
    # Cleanup
    print("\n[Cleanup] Removing SSO authentication cache...")
    cleanup_sso_cache()
    
    return 0

if __name__ == "__main__":
    try:
        exit(main())
    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user. Exiting.")
        cleanup_sso_cache()
        exit(130)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        exit(1)