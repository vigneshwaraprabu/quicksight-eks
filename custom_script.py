import csv, boto3, argparse
from botocore.exceptions import ClientError
from datetime import datetime, timezone
import kubernetes.client as k8s, kubernetes.config

def assume_role(account_id, role_name, region):
    sts = boto3.client("sts", region_name=region)
    creds = sts.assume_role(
        RoleArn=f"arn:aws:iam::{account_id}:role/{role_name}",
        RoleSessionName=f"AssumeRoleTest-{account_id}"
    )["Credentials"]
    return boto3.Session(
        aws_access_key_id=creds["AccessKeyId"],
        aws_secret_access_key=creds["SecretAccessKey"],
        aws_session_token=creds["SessionToken"],
        region_name=region)

def print_caller_identity(session, account_id, region):
    i = session.client("sts", region_name=region).get_caller_identity()
    print(f"\n=== Account: {account_id} | Region: {region} | UserId: {i['UserId']} | Arn: {i['Arn']} ===")

def list_eks_clusters(session, region):
    try:
        eks = session.client("eks", region_name=region)
        return sum([p.get("clusters", []) for p in eks.get_paginator("list_clusters").paginate()], [])
    except ClientError as e:
        print(f"❌ Failed to list EKS clusters in {region}: {e}")
        return []

def get_ami_ids(session, cluster_name, region):
    try:
        ec2 = session.client("ec2", region_name=region)
        filters = [
            {"Name": "instance-state-name", "Values": ["running"]},
            {"Name": f"tag:kubernetes.io/cluster/{cluster_name}", "Values": ["owned", "shared"]}
        ]
        paginator = ec2.get_paginator("describe_instances")
        ami_ids = []
        for page in paginator.paginate(Filters=filters):
            for res in page.get("Reservations", []):
                for inst in res.get("Instances", []):
                    ami_id = inst.get("ImageId")
                    if ami_id:
                        ami_ids.append(ami_id)
        return ami_ids
    except ClientError:
        return []

def get_latest_eks_amis(session, region, version):
    os_paths = [
        "amazon-linux-2/x86_64/standard",
        "amazon-linux-2023/x86_64/standard",
        "bottlerocket/x86_64/standard",
        "ubuntu/x86_64/standard",
    ]
    try:
        ssm = session.client("ssm", region_name=region)
        return {os: ssm.get_parameter(Name=f"/aws/service/eks/optimized-ami/{version}/{os}/recommended/image_id")["Parameter"]["Value"]
                for os in os_paths if not ClientError}, ""
    except ClientError as e:
        return {}, str(e)

def parse_ami_info(ami_info):
    d = ami_info.get("CreationDate", 0)
    ami_age = 0
    if d and d != 0:
        try:
            delta = datetime.now(timezone.utc) - datetime.fromisoformat(d.replace('Z', '+00:00'))
            ami_age = f"{delta.days} days"
        except Exception:
            ami_age = 0
    desc = str(ami_info.get("Description", "")).lower()
    for k, v in {"amazon linux 2023": "Amazon Linux 2023", "amazon linux 2": "Amazon Linux 2", "bottlerocket": "Bottlerocket", "ubuntu": "Ubuntu"}.items():
        if k in desc: return ami_age, v
    return ami_age, 0



def get_node_readiness(instance_ids):
    try:
        kubernetes.config.load_kube_config()
        v1 = k8s.CoreV1Api()
        k8s_nodes = v1.list_node()
        m = {}
        for n in k8s_nodes.items:
            pid = n.spec.provider_id
            if pid and pid.startswith('aws:///'):
                iid = pid.split('/')[-1]
                if iid in instance_ids:
                    ready = any(c.type == 'Ready' and c.status == 'True' for c in (n.status.conditions or []))
                    m[iid] = "Ready" if ready else "NotReady"
        for iid in instance_ids:
            if iid not in m:
                m[iid] = "Unknown"
        return m
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
                        delta = datetime.now(timezone.utc) - launch_time.replace(tzinfo=timezone.utc)
                        days, hours = delta.days, delta.seconds // 3600
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
            for img in ec2.describe_images(ImageIds=list(ami_ids)).get("Images", []):
                ami_data[img["ImageId"]] = {"CreationDate": img.get("CreationDate", 0), "Description": img.get("Description", "")}
        for node in nodes:
            node["AMI_Age"], node["OS_Version"] = parse_ami_info(ami_data.get(node["AMI_ID"], {"CreationDate": 0, "Description": ""}))
        rmap = get_node_readiness(instance_ids)
        for node in nodes:
            node["NodeReadinessStatus"] = rmap.get(node["InstanceID"], 0)
        return nodes
    except ClientError:
        return []

# Add: helper to get EKS cluster version


def get_cluster_version(session, cluster_name, region):
    try:
        return session.client("eks", region_name=region).describe_cluster(name=cluster_name)["cluster"]["version"]
    except ClientError:
        return "N/A"



def get_current_identity(region=None):
    return boto3.client("sts", region_name=region).get_caller_identity()




def get_patch_status(ami_age_str):
    try:
        if ami_age_str and "days" in str(ami_age_str):
            return str(int(str(ami_age_str).split()[0]) < 30)
    except Exception:
        pass
    return 0



def write_node_row(w, aid, reg, cl, ver, n, lami, pstat, nready):
    w.writerow([
        aid, reg, cl, ver,
        n.get("InstanceID", 0) or 0,
        n.get("AMI_ID", 0) or 0,
        n.get("AMI_Age", 0) or 0,
        n.get("OS_Version", 0) or 0,
        n.get("InstanceType", 0) or 0,
        n.get("NodeState", 0) or 0,
        n.get("NodeUptime", 0) or 0,
        lami or 0,
        pstat or 0,
        nready or 0
    ])



def process_clusters(session, w, aid, reg):
    clusters = list_eks_clusters(session, reg)
    print("EKS Clusters:")
    for c in clusters:
        ver = get_cluster_version(session, c, reg)
        latest_amis, err = get_latest_eks_amis(session, reg, ver)
        if err:
            print(f"Error fetching latest EKS AMIs for {reg} cluster {c} (version {ver}): {err}")
        elif not latest_amis:
            print(f"No latest EKS AMIs found for {reg} cluster {c} (version {ver})")
        else:
            for os_type, ami_id in latest_amis.items():
                print(f"Latest EKS AMI for {reg} cluster {c} (version {ver}, {os_type}): {ami_id}")
        nodes = get_node_details(session, c, reg)
        for n in nodes:
            os_version = str(n.get("OS_Version", "")).lower()
            os_key = {
                "amazon linux 2": "amazon-linux-2/x86_64/standard",
                "amazon linux 2023": "amazon-linux-2023/x86_64/standard",
                "bottlerocket": "bottlerocket/x86_64/standard",
                "ubuntu": "ubuntu/x86_64/standard"
            }.get(os_version, None)
            lami = latest_amis.get(os_key, 0) if latest_amis and os_key else 0
            pstat = get_patch_status(n.get("AMI_Age", 0))
            nready = n.get("NodeReadinessStatus", 0)
            print(f" - {c}: Instance {n['InstanceID']} (AMI: {n['AMI_ID']}, Type: {n['InstanceType']})")
            write_node_row(w, aid, reg, c, ver, n, lami, pstat, nready)
        if not nodes:
            print(f" - {c}: (no running nodes)")
            write_node_row(w, aid, reg, c, ver, {}, 0, 0, 0)
    if not clusters:
        print(" - (none found)")




OUTPUT_FILE = "output.csv"

def main():
    parser = argparse.ArgumentParser(description="EKS/EC2/K8s inventory script")
    parser.add_argument('--bucket', required=True, help='S3 bucket name to upload output file')
    parser.add_argument('--account-list', required=True, help='CSV file with account list')
    parser.add_argument('--prefix', default="reports", help='S3 prefix/folder for output file (default: reports)')
    args = parser.parse_args()

    try:
        ident = get_current_identity()
        curr_acct, curr_arn = ident["Account"], ident["Arn"]
    except Exception:
        curr_acct, curr_arn = None, ""
    with open(OUTPUT_FILE, "w", newline="") as out_f:
        w = csv.writer(out_f)
        w.writerow(["AccountID", "Region", "ClusterName", "ClusterVersion", "InstanceID", "AMI_ID", "AMI_Age", "OS_Version", "InstanceType", "NodeState", "NodeUptime", "Latest_EKS_AMI", "PatchStatus", "NodeReadinessStatus"])
        with open(args.account_list, newline="") as f:
            for row in csv.DictReader(f):
                aid, rname, region_field = row["account_id"].strip(), row["role_name"].strip(), row["region"].strip()
                for reg in [r.strip() for r in region_field.split(",") if r.strip()]:
                    print(f"\n🔄 Assuming role in account {aid} ({reg}) ...")
                    same = (aid == curr_acct and (f"assumed-role/{rname}" in curr_arn or f":role/{rname}" in curr_arn))
                    try:
                        session = boto3.Session(region_name=reg) if same else assume_role(aid, rname, reg)
                        print_caller_identity(session, aid, reg)
                        process_clusters(session, w, aid, reg)
                        print("✅ Success")
                        status, status_msg = "SUCCESS", "Clusters fetched"
                    except ClientError as e:
                        code, msg = e.response.get("Error", {}).get("Code", ""), str(e)
                        print(f"❌ Failed for account {aid} in {reg}: {code} - {msg}")
                        status, status_msg = "FAILED", f"{code} - {msg}"
                        if aid == curr_acct:
                            try:
                                session = boto3.Session(region_name=reg)
                                print("ℹ️  Falling back to current credentials for same account.")
                                print_caller_identity(session, aid, reg)
                                process_clusters(session, w, aid, reg)
                                status, status_msg = "SUCCESS (fallback)", "Clusters fetched with fallback"
                            except Exception as ex:
                                print(f"❌ Fallback also failed: {ex}")
                                status, status_msg = "FAILED", f"fallback failed: {ex}"
                    except Exception as ex:
                        print(f"❌ Error processing account {aid} in {reg}: {ex}")
                        status, status_msg = "FAILED", str(ex)
                    print(f"RESULT: {'✅' if status.startswith('SUCCESS') else '❌'} account={aid} region={reg} status={status} message={status_msg}")
                    print(f"REGION_SUMMARY: account={aid} region={reg} status={status} message={status_msg}")
    s3_key = f"{args.prefix.rstrip('/')}/{OUTPUT_FILE}"
    try:
        boto3.client("s3").upload_file(OUTPUT_FILE, args.bucket, s3_key)
        print(f"✅ Uploaded {OUTPUT_FILE} to s3://{args.bucket}/{s3_key}")
    except Exception as e:
        print(f"❌ Failed to upload {OUTPUT_FILE} to S3: {e}")

if __name__ == "__main__":
    main()