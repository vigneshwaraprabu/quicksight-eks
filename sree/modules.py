import boto3
import pandas as pd
import io
import logging
import base64
from datetime import datetime, timezone
from kubernetes import client as k8s_client
import constants

class EKSAuditor:
    def __init__(self):
        self.s3_client = boto3.client('s3')
        self._setup_logging()

    def _setup_logging(self):
        """Initializes logging to a local file only."""
        self.logger = logging.getLogger("EKSAudit")
        self.logger.setLevel(logging.DEBUG)
        
        file_handler = logging.FileHandler(constants.LOG_FILE, mode='a')
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        file_handler.setFormatter(formatter)
        
        if not self.logger.handlers:
            self.logger.addHandler(file_handler)

    def get_base_role_arn(self, sts_client):
        """
        Dynamically extracts the Base IAM Role ARN from the current session identity.
        This ensures compatibility with EKS Access Entries.
        """
        identity = sts_client.get_caller_identity()
        arn = identity['Arn']
        
        # If the script is running as an assumed role (common in SSO or cross-account)
        if ":assumed-role/" in arn:
            # Reconstruct the Role ARN: Remove the session name and switch sts to iam
            # From: arn:aws:sts::123:assumed-role/MyCustomRole/session-name
            # To:   arn:aws:iam::123:role/MyCustomRole
            role_parts = arn.replace("sts", "iam").replace("assumed-role", "role").split("/")
            return "/".join(role_parts[:-1])
        return arn

    def get_k8s_api_client(self, cluster_info, region):
        """Generates a signed EKS token for the current custom role."""
        cluster_name = cluster_info['name']
        endpoint = cluster_info['endpoint']
        
        # Initialize STS specifically for the region of the target cluster
        sts = boto3.client('sts', region_name=region)
        
        # This replicates the 'aws eks get-token' logic
        signed_url = sts.generate_presigned_url(
            'get_caller_identity',
            Params={'Header': {'x-k8s-aws-id': cluster_name}},
            ExpiresIn=60,
            HttpMethod='GET'
        )
        
        # Construct the Bearer Token
        token = 'k8s-aws-v1.' + base64.urlsafe_b64encode(signed_url.encode('utf-8')).decode('utf-8').rstrip('=')

        configuration = k8s_client.Configuration()
        configuration.host = endpoint
        configuration.verify_ssl = True
        
        # Handle CA Certificate
        ca_path = "/tmp/ca.crt"
        with open(ca_path, "wb") as f:
            f.write(base64.b64decode(cluster_info['certificateAuthority']['data']))
        configuration.ssl_ca_cert = ca_path
        
        configuration.api_key['authorization'] = f"Bearer {token}"
        configuration.api_key_prefix['authorization'] = 'Bearer'
        
        return k8s_client.CoreV1Api(k8s_client.ApiClient(configuration))

    def get_account_name(self, iam_client, account_id):
        """Attempts to fetch the Account Alias for better dashboard readability."""
        try:
            aliases = iam_client.list_account_aliases()['AccountAliases']
            return aliases[0] if aliases else str(account_id)
        except Exception:
            return str(account_id)

    def get_latest_ami(self, ssm, k8s_version):
        """Fetches the latest approved EKS AMI from SSM."""
        for path_template in constants.SSM_PATHS:
            try:
                path = path_template.format(version=k8s_version)
                response = ssm.get_parameter(Name=path)
                return (
                    response['Parameter']['Value'], 
                    response['Parameter']['LastModifiedDate'].strftime('%Y-%m-%d')
                )
            except Exception:
                continue
        return "NA", "NA"

    def perform_audit(self, region, account_no):
        """Main audit logic called per row in the input CSV."""
        self.logger.info(f"--- Starting Audit: {account_no} | {region} ---")
        
        sts_client = boto3.client('sts', region_name=region)
        self.logger.info(f"Identity Role: {self.get_base_role_arn(sts_client)}")

        eks = boto3.client('eks', region_name=region)
        ec2 = boto3.client('ec2', region_name=region)
        ssm = boto3.client('ssm', region_name=region)
        iam = boto3.client('iam', region_name=region)

        account_name = self.get_account_name(iam, account_no)
        inventory = []
        
        try:
            clusters = eks.list_clusters().get('clusters', [])
        except Exception as e:
            self.logger.error(f"Failed to list clusters: {str(e)}")
            return []

        for name in clusters:
            try:
                desc = eks.describe_cluster(name=name)['cluster']
                late_ami, late_date = self.get_latest_ami(ssm, desc['version'])

                # 1. Fetch Node Readiness from K8s API
                readiness_map = {}
                try:
                    v1 = self.get_k8s_api_client(desc, region)
                    for node in v1.list_node().items:
                        ready_cond = next((c for c in node.status.conditions if c.type == 'Ready'), None)
                        if ready_cond:
                            readiness_map[node.metadata.name] = "Ready" if ready_cond.status == "True" else "NotReady"
                except Exception as e:
                    self.logger.error(f"K8s API failed for cluster {name}: {str(e)}")

                # 2. Match with EC2 data (includes Managed and Spot.io)
                # 
                nodes = ec2.describe_instances(
                    Filters=[{'Name': f'tag:kubernetes.io/cluster/{name}', 'Values': ['owned', 'shared']}]
                )
                
                for res in nodes['Reservations']:
                    for inst in res['Instances']:
                        dns_name = inst.get('PrivateDnsName')
                        # If K8s API call failed, falls back to EC2 status (e.g., 'running')
                        readiness = readiness_map.get(dns_name, inst['State']['Name'])
                        
                        uptime = round((datetime.now(timezone.utc) - inst['LaunchTime']).total_seconds() / 3600, 2)
                        
                        inventory.append({
                            "account_id": str(account_no),
                            "account_name": account_name,
                            "clustername": name,
                            "instanceid": inst['InstanceId'],
                            "nodeuptime": uptime,
                            "readiness": readiness,
                            "currentami": inst['ImageId'],
                            "latestapprovedami": late_ami,
                            "patchpendingstatus": bool(late_ami != "NA" and inst['ImageId'] != late_ami),
                            "audittimestamp": datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
                        })
            except Exception as cluster_err:
                self.logger.error(f"Error processing cluster {name}: {str(cluster_err)}")

        return inventory

    def upload_to_s3(self, results):
        """Converts results to CSV and uploads to S3."""
        if not results:
            self.logger.warning("No data found for audit.")
            return

        df = pd.DataFrame(results)
        csv_buffer = io.StringIO()
        df.to_csv(csv_buffer, index=False)
        
        filename = f"{constants.S3_FOLDER}/eks_inventory_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        
        try:
            self.s3_client.put_object(Bucket=constants.S3_BUCKET, Key=filename, Body=csv_buffer.getvalue())
            self.logger.info(f"Report uploaded successfully: {filename}")
        except Exception as e:
            self.logger.critical(f"S3 Upload Failed: {str(e)}")