import argparse
import csv
import logging
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime
from queue import Queue
from typing import Dict, List, Tuple

import boto3
from botocore.exceptions import BotoCoreError, ClientError

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Queue for CSV writing
csv_queue: Queue = Queue()


def load_accounts_from_csv(csv_file: str) -> Dict[str, List[str]]:
    account_regions = {}
    with open(csv_file, newline="") as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            account_id = row["account_id"].strip()
            regions_str = row["regions"]
            account_regions[account_id] = [
                r.strip() for r in regions_str.split(",") if r.strip()
            ]
    return account_regions


def assume_role(
    role_arn: str, session_name: str = "ResourceTagSession"
) -> Tuple[str, str, str]:
    sts_client = boto3.client("sts")
    try:
        response = sts_client.assume_role(
            RoleArn=role_arn, RoleSessionName=session_name, DurationSeconds=3600
        )
        credentials = response["Credentials"]
        return (
            credentials["AccessKeyId"],
            credentials["SecretAccessKey"],
            credentials["SessionToken"],
        )
    except (BotoCoreError, ClientError) as e:
        logger.error(f"Failed to assume role {role_arn}: {e}")
        raise


def get_client(
    service, region, aws_access_key_id, aws_secret_access_key, aws_session_token
):
    session = boto3.Session(
        aws_access_key_id=aws_access_key_id,
        aws_secret_access_key=aws_secret_access_key,
        aws_session_token=aws_session_token,
    )
    return session.client(service, region_name=region)


def extract_resources(account_id, region, creds):
    access_key, secret_key, session_token = creds
    try:
        client = get_client(
            "resourcegroupstaggingapi", region, access_key, secret_key, session_token
        )
        paginator = client.get_paginator("get_resources")

        for page in paginator.paginate(PaginationConfig={"PageSize": 50}):
            for resource in page.get("ResourceTagMappingList", []):
                resource_arn = resource.get("ResourceARN", "")
                tags = {tag["Key"]: tag["Value"] for tag in resource.get("Tags", [])}
                service_type = resource_arn.split(":")[2] if ":" in resource_arn else ""
                resource_name = (
                    resource_arn.split("/")[-1] if "/" in resource_arn else ""
                )
                creation_date = ""  # Not available via this API
                dateofextraction = date.today()

                csv_queue.put(
                    [
                        account_id,
                        creation_date,
                        resource_arn,
                        resource_name,
                        dateofextraction,
                        service_type,
                        region,
                        tags.get("mmsystem", ""),
                        tags.get("standard", ""),
                        tags.get("product", ""),
                    ]
                )
        print(f"{account_id} in {region} ✅ completed")
    except Exception as e:
        print(f"❌ Failed for {account_id} in {region}: {e}")


def csv_writer(filename):
    with open(filename, "w", newline="") as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(
            [
                "AccountID",
                "ResourceCreationDate",
                "ResourceARN",
                "ResourceName",
                "DateOfExtraction",
                "Type",
                "Region",
                "mmsystem",
                "standard",
                "product",
            ]
        )
        while True:
            row = csv_queue.get()
            if row == "DONE":
                break
            writer.writerow(row)
            csv_queue.task_done()


def upload_to_s3(filename: str, bucket: str, prefix: str = ""):
    s3_client = boto3.client("s3")
    key = f"{prefix.rstrip('/')}/{filename}" if prefix else filename

    try:
        s3_client.upload_file(filename, bucket, key)
        print(f"✅ File uploaded to S3: s3://{bucket}/{key}")
    except Exception as e:
        print(f"❌ Failed to upload to S3: {e}")


def main(csv_path, s3_bucket=None, s3_prefix=""):
    account_regions = load_accounts_from_csv(csv_path)

    # Output file
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"AllAccounts_TF_Modules_Adoption_Report_{timestamp}.csv"

    # Start CSV writer thread
    writer_thread = threading.Thread(target=csv_writer, args=(filename,))
    writer_thread.start()

    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = []
        for account_id, regions in account_regions.items():
            role_arn = f"arn:aws:iam::{account_id}:role/tag-check-assume-role"
            try:
                creds = assume_role(
                    role_arn, session_name=f"GitHubTagCheck-{account_id}"
                )
                for region in regions:
                    futures.append(
                        executor.submit(extract_resources, account_id, region, creds)
                    )
            except Exception as e:
                logger.error(
                    f"Skipping account {account_id}: failed to assume role: {e}"
                )

        for future in as_completed(futures):
            _ = future.result()

    # Finalize CSV writing
    csv_queue.put("DONE")
    writer_thread.join()

    print(f"\n✅ Output written to local file: {filename}\n")

    if s3_bucket:
        upload_to_s3(filename, s3_bucket, s3_prefix)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="AWS Resource Tag Extractor (Multi-Account)"
    )
    parser.add_argument(
        "--accounts_csv",
        required=True,
        help="Path to CSV file with account_id and regions",
    )
    parser.add_argument(
        "--s3-bucket", help="Optional: Upload final CSV to this S3 bucket"
    )
    parser.add_argument(
        "--s3-prefix",
        default="",
        help="Optional: Prefix (folder path) in the S3 bucket",
    )
    args = parser.parse_args()

    main(args.accounts_csv, args.s3_bucket, args.s3_prefix)
