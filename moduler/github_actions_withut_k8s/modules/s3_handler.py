import boto3
from datetime import datetime
from pathlib import Path
from botocore.exceptions import ClientError
from .logger import Logger


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
    
    def upload_file(self, local_file: str, bucket: str, prefix: str = "", preserve_filename: bool = False) -> bool:
        try:
            if preserve_filename:
                filename = Path(local_file).name
            else:
                filename = self.generate_timestamped_filename(Path(local_file).name)
            
            s3_key = f"{prefix}/{filename}" if prefix else filename
            s3_key = s3_key.lstrip("/")
            
            Logger.blank()
            Logger.info(f"Uploading to S3")
            Logger.info(f"Bucket: {bucket}", indent=1)
            Logger.info(f"Key: {s3_key}", indent=1)
            
            self.s3_client.upload_file(
                Filename=local_file,
                Bucket=bucket,
                Key=s3_key
            )
            
            s3_url = f"s3://{bucket}/{s3_key}"
            Logger.success(f"Successfully uploaded to {s3_url}")
            return True
            
        except FileNotFoundError:
            Logger.error(f"Local file '{local_file}' not found")
            return False
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', 'Unknown')
            if error_code == 'NoSuchBucket':
                Logger.error(f"S3 bucket '{bucket}' does not exist")
            elif error_code == 'AccessDenied':
                Logger.error(f"Access denied to bucket '{bucket}'. Check IAM permissions")
            else:
                Logger.error(f"Failed to upload to S3: {e}")
            return False
        except Exception as e:
            Logger.error(f"S3 upload failed: {e}")
            return False
