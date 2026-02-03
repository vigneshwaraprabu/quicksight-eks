import csv
import boto3
from botocore.exceptions import ClientError
from datetime import datetime, timezone
import kubernetes.client as k8s
import kubernetes.config

def assume_role(account_id, role_name, region):
    sts = boto3.client("sts", region_name=region)
    response = sts.assume_role(
        RoleArn=f"arn:aws:iam::{account_id}:role/{role_name}",
        RoleSessionName=f"AssumeRoleTest-{account_id}"
    )
    creds = response["Credentials"]
    return boto3.Session(
        aws_access_key_id=creds["AccessKeyId"],
        aws_secret_access_key=creds["SecretAccessKey"],
        aws_session_token=creds["SessionToken"],
        region_name=region
    )

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


def get_node_readiness(instance_ids):
    try:
        kubernetes.config.load_kube_config()
        v1 = k8s.CoreV1Api()
        k8s_nodes = v1.list_node()
        readiness_map = {}
        for k_node in k8s_nodes.items:
            provider_id = k_node.spec.provider_id
            if provider_id and provider_id.startswith('aws:///'):
                instance_id = provider_id.split('/')[-1]
                if instance_id in instance_ids:
                    conditions = k_node.status.conditions or []
                    ready = any(c.type == 'Ready' and c.status == 'True' for c in conditions)
                    readiness_map[instance_id] = "Ready" if ready else "NotReady"
        for iid in instance_ids:
            if iid not in readiness_map:
                readiness_map[iid] = "Unknown"
        return readiness_map
    except Exception as e:
        print(f"Failed to fetch node readiness from Kubernetes API: {e}")
        return {iid: "Unknown" for iid in instance_ids}


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
        readiness_map = get_node_readiness(instance_ids)
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
            return 1 if days < 30 else 0
        except Exception:
            return 0
    return 0

def write_node_row(writer, account_id, region, cluster, cluster_version, node, latest_ami, patch_status, node_readiness):
    patch_status = 1 if patch_status == 1 else 0
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
    csv_file = "accounts.csv"
    output_file = "output.csv"
    try:
        current_identity = get_current_identity()
        current_account = current_identity["Account"]
        current_arn = current_identity["Arn"]
    except Exception:
        current_account = None
        current_arn = ""
    with open(output_file, "w", newline="") as out_f:
        writer = csv.writer(out_f)
        writer.writerow([
            "AccountID", "Region", "ClusterName", "ClusterVersion",
            "InstanceID", "AMI_ID", "AMI_Age", "OS_Version", "InstanceType", "NodeState", "NodeUptime",
            "Latest_EKS_AMI", "PatchStatus", "NodeReadinessStatus"
        ])
        with open(csv_file, newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                account_id = row["account_id"].strip()
                role_name = row["role_name"].strip()
                region_field = row["region"].strip()
                regions = [r.strip() for r in region_field.split(",") if r.strip()]
                for region in regions:
                    print(f"\n🔄 Assuming role in account {account_id} ({region}) ...")
                    already_same_role = (
                        account_id == current_account and
                        (f"assumed-role/{role_name}" in current_arn or f":role/{role_name}" in current_arn)
                    )
                    try:
                        session = boto3.Session(region_name=region) if already_same_role else assume_role(account_id, role_name, region)
                        print_caller_identity(session, account_id, region)
                        process_clusters(session, writer, account_id, region)
                        print("✅ Success")
                    except Exception as ex:
                        print(f"❌ Error processing account {account_id} in {region}: {ex}")
                    print(f"REGION_SUMMARY: account={account_id} region={region}")
    try:
        boto3.client("s3").upload_file(output_file, "vignesh-s3-debezium-test", "reports/output.csv")
        print("✅ Uploaded output.csv to s3://vignesh-s3-debezium-test/reports/output.csv")
    except Exception as e:
        print(f"❌ Failed to upload output.csv to S3: {e}")

if __name__ == "__main__":
    main()