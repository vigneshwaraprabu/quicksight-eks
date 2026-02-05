import boto3
from datetime import datetime
from pathlib import Path
from botocore.exceptions import ClientError


class S3Handler:
    
    def __init__(self, session):
        self.session = session
        self.s3_client = session.client("s3")
    
    @staticmethod
    def generate_timestamped_filename(base_filename: str) -> str:
        timestamp = datetime.now().strftime("%d%b%Y_%I_%M%p")
        path = Path(base_filename)
        stem = path.stem
        suffix = path.suffix
        return f"{stem}_{timestamp}{suffix}"
    
    def upload_file(self, local_file: str, bucket: str, prefix: str = "") -> bool:
        try:
            timestamped_name = self.generate_timestamped_filename(Path(local_file).name)
            s3_key = f"{prefix}/{timestamped_name}" if prefix else timestamped_name
            s3_key = s3_key.lstrip("/")
            
            print(f"\nINFO: Uploading to S3")
            print(f"INFO: Bucket: {bucket}")
            print(f"INFO: Key: {s3_key}")
            
            self.s3_client.upload_file(
                Filename=local_file,
                Bucket=bucket,
                Key=s3_key
            )
            
            s3_url = f"s3://{bucket}/{s3_key}"
            print(f"INFO: Successfully uploaded to {s3_url}")
            return True
            
        except FileNotFoundError:
            print(f"ERROR: Local file '{local_file}' not found")
            return False
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', 'Unknown')
            if error_code == 'NoSuchBucket':
                print(f"ERROR: S3 bucket '{bucket}' does not exist")
            elif error_code == 'AccessDenied':
                print(f"ERROR: Access denied to bucket '{bucket}'. Check IAM permissions")
            else:
                print(f"ERROR: Failed to upload to S3: {e}")
            return False
        except Exception as e:
            print(f"ERROR: S3 upload failed: {e}")
            return False
