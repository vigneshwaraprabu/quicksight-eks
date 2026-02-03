import boto3
import csv
import threading
from datetime import datetime, timezone
from queue import Queue
from concurrent.futures import ThreadPoolExecutor

from kubernetes import client as k8s_client
from kubernetes.config import load_kube_config

csv_queue = Queue()

COMPLIANCE_DAYS = 30

def assume_role(role_arn, session_name):
    sts = boto3.client("sts")
    creds = sts.assume_role(
        RoleArn=role_arn,
        RoleSessionName=session_name
    )["Credentials"]

    return boto3.Session(
        aws_access_key_id=creds["AccessKeyId"],
        aws_secret_access_key=creds["SecretAccessKey"],
        aws_session_token=creds["SessionToken"]
    )

def get_eks_clusters(session, region):
    eks = session.client("eks", region_name=region)
    return eks.list_clusters()["clusters"]

def get_cluster_nodes(session, region, cluster_name):
    ec2 = session.client("ec2", region_name=region)

    filters = [
        {"Name": "tag:eks:cluster-name", "Values": [cluster_name]},
        {"Name": "instance-state-name", "Values": ["running", "stopped"]}
    ]

    reservations = ec2.describe_instances(Filters=filters)["Reservations"]
    return [i for r in reservations for i in r["Instances"]]

def get_ami_details(session, region, ami_id):
    ec2 = session.client("ec2", region_name=region)
    image = ec2.describe_images(ImageIds=[ami_id])["Images"][0]
    creation = datetime.fromisoformat(image["CreationDate"].replace("Z", "+00:00"))
    age_days = (datetime.now(timezone.utc) - creation).days
    return creation.date(), age_days

def get_running_pods_per_node():
    v1 = k8s_client.CoreV1Api()
    pods = v1.list_pod_for_all_namespaces().items
    pod_count = {}
    for pod in pods:
        if pod.spec.node_name:
            pod_count[pod.spec.node_name] = pod_count.get(pod.spec.node_name, 0) + 1
    return pod_count

def extract_cluster_data(account_id, region, cluster_name, session):
    nodes = get_cluster_nodes(session, region, cluster_name)

    pod_map = get_running_pods_per_node()

    for node in nodes:
        instance_id = node["InstanceId"]
        ami_id = node["ImageId"]
        launch_time = node["LaunchTime"]
        uptime_days = (datetime.now(timezone.utc) - launch_time).days

        ami_creation, ami_age = get_ami_details(session, region, ami_id)

        compliance = "COMPLIANT" if ami_age < COMPLIANCE_DAYS else "NON_COMPLIANT"

        csv_queue.put([
            account_id,
            region,
            cluster_name,
            node.get("PrivateDnsName", ""),
            instance_id,
            node["InstanceType"],
            ami_id,
            ami_creation,
            ami_age,
            launch_time.date(),
            uptime_days,
            node["State"]["Name"],
            pod_map.get(node.get("PrivateDnsName", ""), 0),
            compliance
        ])

def csv_writer(filename):
    with open(filename, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "AccountID","Region","ClusterName","NodeName","InstanceId",
            "InstanceType","AMI_ID","AMI_CreationDate","AMI_Age_Days",
            "NodeLaunchTime","NodeUptimeDays","NodeStatus","RunningPods","Compliance"
        ])
        while True:
            row = csv_queue.get()
            if row == "DONE":
                break
            writer.writerow(row)

def main():
    account_id = "853973692277"
    region = "us-east-1"
    role_arn = f"arn:aws:iam::{account_id}:role/EC2RoleforMSK"

    session = assume_role(role_arn, "EKSNodeCompliance")

    filename = f"EKS_Node_Compliance_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    threading.Thread(target=csv_writer, args=(filename,), daemon=True).start()

    clusters = get_eks_clusters(session, region)

    with ThreadPoolExecutor(max_workers=5) as executor:
        for cluster in clusters:
            executor.submit(extract_cluster_data, account_id, region, cluster, session)

    csv_queue.put("DONE")
    print(f"✅ Report generated: {filename}")

if __name__ == "__main__":
    main()