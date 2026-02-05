import os

# --- S3 & Input Configuration ---
S3_BUCKET = 'latest-eks-data'
S3_FOLDER = 'eks-inventory-audit'
INPUT_CSV_PATH = 'input.csv'
LOG_FILE = 'eks_audit.log'

# --- AWS SSM AMI Paths ---
# Standard paths to fetch latest recommended EKS AMI IDs
SSM_PATHS = [
    '/aws/service/eks/optimized-ami/{version}/amazon-linux-2/recommended/image_id',
    '/aws/service/eks/optimized-ami/{version}/amazon-linux-2023/x86_64/standard/recommended/image_id'
]

# --- Refinement Account Logic ---
# Filter specific accounts here; leave empty to process all in CSV
REFINED_ACCOUNTS = []