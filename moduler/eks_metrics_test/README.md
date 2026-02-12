# EKS Cluster Analyzer

## Overview

Analyzes AWS EKS clusters across multiple regions using your current AWS credentials. Collects detailed information about clusters, nodes, AMI versions, and compliance status.

## Features

- **Uses Current AWS Credentials**: No SSO setup required - uses your active AWS session
- **Multi-Region Support**: Analyze clusters across multiple AWS regions
- **Comprehensive Analysis**:
  - Cluster version and compliance status
  - Node instance types and states
  - AMI versions and patch status
  - Kubernetes node readiness
  - OS version detection (Amazon Linux 2, AL2023, Bottlerocket, Ubuntu)
  - Node uptime and AMI age

## Prerequisites

### Required Software

```bash
# Python 3.7+
python3 --version

# AWS CLI
aws --version

# kubectl (for node readiness checks)
kubectl version --client
```

### Python Dependencies

```bash
pip3 install boto3 kubernetes
```

### AWS Credentials

Ensure you have valid AWS credentials configured. The script will use your current session:

```bash
# Verify credentials
aws sts get-caller-identity

# Example output:
# {
#   "UserId": "AIDAXXXXXXXXXXXXXXXXX",
#   "Account": "123456789012",
#   "Arn": "arn:aws:iam::123456789012:user/your-user"
# }
```

## Required IAM Permissions

Your AWS credentials must have the following permissions:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "eks:ListClusters",
        "eks:DescribeCluster"
      ],
      "Resource": "*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "ec2:DescribeInstances",
        "ec2:DescribeImages"
      ],
      "Resource": "*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "ssm:GetParameter"
      ],
      "Resource": "arn:aws:ssm:*:*:parameter/aws/service/eks/optimized-ami/*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "iam:ListAccountAliases"
      ],
      "Resource": "*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "sts:GetCallerIdentity"
      ],
      "Resource": "*"
    }
  ]
}
```

### Optional (for Kubernetes readiness checks)

For node readiness status, you also need EKS cluster access:

```json
{
  "Effect": "Allow",
  "Action": [
    "eks:DescribeCluster"
  ],
  "Resource": "*"
}
```

And appropriate Kubernetes RBAC permissions in the cluster.

## Usage

### Option 1: Use Regions File (Recommended)

Create or edit `regions.txt`:

```txt
# List regions to analyze, one per line
us-east-1
us-east-2
us-west-2
ap-south-1
```

Run the analyzer:

```bash
cd /path/to/eks_metrics
python3 eks_analyzer.py
```

### Option 2: Specify Regions via Command Line

```bash
python3 eks_analyzer.py --regions us-east-1,us-west-2,eu-central-1
```

### Option 3: Custom Regions File

```bash
python3 eks_analyzer.py --regions-file my_regions.txt
```

## Command Line Options

```
usage: eks_analyzer.py [-h] [--regions REGIONS] [--regions-file REGIONS_FILE]

EKS Cluster Analyzer - Uses current AWS credentials

optional arguments:
  -h, --help            show this help message and exit
  --regions REGIONS     Comma-separated list of AWS regions (e.g., us-east-1,us-west-2)
  --regions-file REGIONS_FILE
                        File containing regions, one per line (default: regions.txt)
```

## Output

### Output File

- **File Name**: `eks_analysis_output.csv`
- **Location**: Current directory

### Output Columns

| Column | Description |
|--------|-------------|
| `AccountID` | AWS Account ID |
| `AccountName` | AWS Account alias or name |
| `Region` | AWS Region |
| `ClusterName` | EKS cluster name |
| `ClusterVersion` | Kubernetes version |
| `InstanceID` | EC2 instance ID |
| `Current_AMI_ID` | Currently running AMI |
| `Current_AMI_Publication_Date` | AMI creation date |
| `AMI_Age` | Days since AMI creation |
| `OS_Version` | Operating system type |
| `InstanceType` | EC2 instance type |
| `NodeState` | EC2 instance state |
| `NodeUptime` | Time since instance launch |
| `Latest_AMI_ID` | Latest available AMI for cluster version |
| `New_AMI_Publication_Date` | Latest AMI creation date |
| `PatchPendingStatus` | True if AMI is >30 days old |
| `NodeReadinessStatus` | Kubernetes node ready status |
| `Cluster_Compliance` | 1 if within 2 versions of latest, else 0 |

### Sample Output

```csv
AccountID,AccountName,Region,ClusterName,ClusterVersion,InstanceID,Current_AMI_ID,Current_AMI_Publication_Date,AMI_Age,OS_Version,InstanceType,NodeState,NodeUptime,Latest_AMI_ID,New_AMI_Publication_Date,PatchPendingStatus,NodeReadinessStatus,Cluster_Compliance
123456789012,prod-account,us-east-1,prod-cluster,1.29,i-0abc123def456,ami-0abc123,2024-01-15,45 days,Amazon Linux 2023,t3.large,running,45 days 12 hours,ami-0xyz789,2024-02-20,True,Ready,1
```

## Example Workflow

```bash
# 1. Verify AWS credentials
aws sts get-caller-identity

# 2. Create regions file
cat > regions.txt << EOF
us-east-1
us-west-2
EOF

# 3. Run the analyzer
python3 eks_analyzer.py

# 4. View output
cat eks_analysis_output.csv
```

## Troubleshooting

### "No credential providers found"

```bash
# Configure AWS credentials
aws configure

# Or use environment variables
export AWS_ACCESS_KEY_ID=your_key
export AWS_SECRET_ACCESS_KEY=your_secret
export AWS_SESSION_TOKEN=your_token  # if using temporary credentials
```

### "Access Denied" errors

Verify your IAM permissions match the requirements above:

```bash
# Test EKS access
aws eks list-clusters --region us-east-1

# Test EC2 access
aws ec2 describe-instances --region us-east-1 --max-results 1

# Test SSM access
aws ssm get-parameter --name /aws/service/eks/optimized-ami/1.29/amazon-linux-2023/x86_64/standard/recommended/image_id --region us-east-1
```

### "Unknown" Node Readiness Status

This usually indicates:
- Kubectl is not installed
- Insufficient Kubernetes RBAC permissions
- Unable to generate kubeconfig for the cluster

You can still get all other metrics; only the `NodeReadinessStatus` will show "Unknown".

## Performance Considerations

- Processing time depends on the number of regions and clusters
- Each cluster requires multiple API calls (EKS, EC2, SSM, K8s)
- Typical performance: 2-5 seconds per cluster

## Project Structure

```
eks_metrics/
├── eks_analyzer.py          # Main script
├── regions.txt              # Region configuration
├── eks_analysis_output.csv  # Output file (generated)
└── modules/
    ├── __init__.py
    ├── aws_session.py       # AWS session management
    ├── cluster_analyzer.py  # Cluster analysis logic
    ├── csv_handler.py       # CSV output handling
    ├── eks_operations.py    # EKS API operations
    ├── kubernetes_operations.py  # K8s API operations
    ├── logger.py            # Colored logging
    └── node_operations.py   # EC2 node operations
```

## Version History

- **v2.0**: Simplified to use current AWS credentials (removed SSO and S3)
- **v1.0**: Original version with SSO authentication and S3 upload

## Support

For issues:
1. Verify AWS credentials: `aws sts get-caller-identity`
2. Check IAM permissions
3. Review error messages in console output
4. Ensure kubectl is installed for node readiness checks
