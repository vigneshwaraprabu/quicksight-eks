# QuickSight Setup Guide

## Table of Contents
- [Introduction](#introduction)
- [Prerequisites](#prerequisites)
- [AWS OIDC Authentication Setup](#aws-oidc-authentication-setup)
- [EKS Access Configuration](#eks-access-configuration)
- [AWS Glue Crawler Setup](#aws-glue-crawler-setup)
- [QuickSight Visualization](#quicksight-visualization)
- [Troubleshooting](#troubleshooting)
- [References](#references)

## Introduction
This guide provides comprehensive steps to set up AWS QuickSight with EKS clusters, AWS Glue, and GitHub Actions using OIDC authentication.

## Prerequisites
- AWS account with appropriate permissions
- AWS CLI installed and configured
- Python 3.11 or higher installed
- Required Python libraries:
  ```bash
  pip install boto3 kubernetes
  ```
- GitHub repository with Actions enabled
- Basic understanding of AWS IAM, EKS, and S3

## AWS OIDC Authentication Setup

### 1. Create OIDC Identity Provider in AWS IAM

1. Navigate to **AWS IAM Console** → **Identity Providers** → **Add Provider**
2. Select **OpenID Connect**
3. Configure the provider:
   - **Provider URL**: `https://token.actions.githubusercontent.com`
   - **Audience**: `sts.amazonaws.com`
4. Click **Add Provider**

### 2. Create IAM Role for OIDC

1. Go to **IAM** → **Roles** → **Create Role**
2. Select **Web Identity** as trusted entity type
3. Choose the OIDC provider created above
4. Attach necessary permissions policies (e.g., EKS read, EC2 describe, STS assume role)
5. Configure the trust policy:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Federated": "arn:aws:iam::853973692277:oidc-provider/token.actions.githubusercontent.com"
      },
      "Action": "sts:AssumeRoleWithWebIdentity",
      "Condition": {
        "StringEquals": {
          "token.actions.githubusercontent.com:aud": "sts.amazonaws.com"
        },
        "StringLike": {
          "token.actions.githubusercontent.com:sub": "repo:YOUR_ORG/YOUR_REPO:*"
        }
      }
    }
  ]
}
```

### 3. Update GitHub Actions Workflow

Create or update `.github/workflows/eks-inventory.yml`:

```yaml
name: EKS Inventory with OIDC

on:
  workflow_dispatch:
  push:
    branches: [main]

permissions:
  id-token: write   # Required for OIDC JWT
  contents: read    # Required for checkout

jobs:
  run-inventory:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Configure AWS credentials using OIDC
        uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: arn:aws:iam::853973692277:role/GithubActionsRole
          aws-region: us-east-1

      - name: Run inventory script
        run: |
          python3 custom_script.py --bucket your-bucket --account-list accounts.csv
```

### 4. Benefits of OIDC

- ✅ No long-lived credentials stored in GitHub Secrets
- ✅ Automatic credential rotation
- ✅ Enhanced security posture
- ✅ Reduced risk of credential leakage
- ✅ Fine-grained access control with conditions

## EKS Access Configuration

### Understanding Role Hierarchy

**Important**: The OIDC role (e.g., `GithubActionsRole`) is only used for initial authentication. The script then assumes roles specified in `accounts.csv` (e.g., `EC2RoleforMSK`) to access EKS clusters. **The role in accounts.csv must have EKS access entries.**

### 1. Required IAM Permissions

The role in `accounts.csv` needs the following permissions:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "EKSReadAccess",
      "Effect": "Allow",
      "Action": [
        "eks:ListClusters",
        "eks:DescribeCluster",
        "eks:ListAccessEntries",
        "eks:DescribeAccessEntry"
      ],
      "Resource": "*"
    },
    {
      "Sid": "EC2NodeInspection",
      "Effect": "Allow",
      "Action": [
        "ec2:DescribeInstances",
        "ec2:DescribeImages",
        "ec2:DescribeTags"
      ],
      "Resource": "*"
    },
    {
      "Sid": "STSCallerIdentity",
      "Effect": "Allow",
      "Action": "sts:GetCallerIdentity",
      "Resource": "*"
    },
    {
      "Sid": "S3Access",
      "Effect": "Allow",
      "Action": [
        "s3:PutObject",
        "s3:GetObject",
        "s3:ListBucket"
      ],
      "Resource": [
        "arn:aws:s3:::your-bucket-name",
        "arn:aws:s3:::your-bucket-name/*"
      ]
    }
  ]
}
```

### 2. Create EKS Access Entry

For each EKS cluster, add the role from `accounts.csv`:

```bash
# Create access entry
aws eks create-access-entry \
  --cluster-name poc-cluster1 \
  --principal-arn arn:aws:iam::853973692277:role/EC2RoleforMSK \
  --type STANDARD \
  --region us-east-1

# Associate admin policy
aws eks associate-access-policy \
  --cluster-name poc-cluster1 \
  --principal-arn arn:aws:iam::853973692277:role/EC2RoleforMSK \
  --policy-arn arn:aws:eks::aws:cluster-access-policy/AmazonEKSClusterAdminPolicy \
  --access-scope type=cluster \
  --region us-east-1

# Verify access entries
aws eks list-access-entries \
  --cluster-name poc-cluster1 \
  --region us-east-1
```

### 3. Verify Configuration

```bash
# Test role assumption
aws sts assume-role \
  --role-arn arn:aws:iam::853973692277:role/EC2RoleforMSK \
  --role-session-name test-session

# Verify identity
aws sts get-caller-identity

# Test EKS access
aws eks describe-cluster \
  --name poc-cluster1 \
  --region us-east-1
```

## AWS Glue Crawler Setup

### 1. Create Glue Crawler

1. Open **AWS Glue Console**
2. Navigate to **Crawlers** → **Create crawler**
3. Configure crawler:
   - **Name**: `output-csv-crawler`
   - **Data source**: S3
   - **Path**: `s3://vignesh-s3-debezium-test/reports/`
   - **Crawl all sub-folders**: Yes (if needed)

### 2. Configure IAM Role

Create or select an IAM role with:
- S3 read permissions for the data bucket
- Glue service permissions
- Write access to Glue Data Catalog

### 3. Set Output Configuration

- **Database**: Create or select existing database
- **Table prefix**: Optional prefix for created tables
- **Update behavior**: Choose appropriate update mode

### 4. Run Crawler

1. Run the crawler manually or on a schedule
2. Verify table creation in **Glue Console** → **Databases** → **Tables**
3. Check schema matches CSV structure

## QuickSight Visualization

### 1. Setup QuickSight Dataset

1. Open **Amazon QuickSight Console**
2. Navigate to **Datasets** → **New dataset**
3. Select **AWS Glue** as data source
4. Choose the Glue database and table created by crawler
5. Configure data preview and import settings

### 2. Configure QuickSight IAM Role

Ensure the QuickSight service role has the following permissions:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "s3:GetObject",
        "s3:ListBucket"
      ],
      "Resource": [
        "arn:aws:s3:::vignesh-s3-debezium-test",
        "arn:aws:s3:::vignesh-s3-debezium-test/*"
      ]
    },
    {
      "Effect": "Allow",
      "Action": [
        "glue:GetDatabase",
        "glue:GetTable",
        "glue:GetPartitions"
      ],
      "Resource": "*"
    }
  ]
}
```

### 3. Create Visualizations

1. Create a new **Analysis** from the dataset
2. Build visualizations using drag-and-drop interface
3. Add filters, calculated fields, and parameters as needed
4. Publish the analysis as a **Dashboard** for sharing

## Troubleshooting

### Error: 401 Unauthorized with OIDC

**Symptoms:**
```
❌ Failed to fetch node readiness for cluster: (401)
Reason: Unauthorized
message":"Unauthorized","reason":"Unauthorized","code":401}
```

**Root Cause:** The role specified in `accounts.csv` (not the OIDC role) lacks EKS access entries.

**Solution:**
```bash
# Add the role from accounts.csv to EKS access entries
aws eks create-access-entry \
  --cluster-name YOUR_CLUSTER_NAME \
  --principal-arn arn:aws:iam::853973692277:role/EC2RoleforMSK \
  --type STANDARD

aws eks associate-access-policy \
  --cluster-name YOUR_CLUSTER_NAME \
  --principal-arn arn:aws:iam::853973692277:role/EC2RoleforMSK \
  --policy-arn arn:aws:eks::aws:cluster-access-policy/AmazonEKSClusterAdminPolicy \
  --access-scope type=cluster
```

### Error: Unhandled Kubernetes API Error

**Symptoms:**
```
E0202 16:14:14.839654   13459 memcache.go:265] "Unhandled Error" 
err="couldn't get current server API group list: the server has asked for the client to provide credentials"
```

**Solution:** Ensure the IAM role has proper EKS access entries and the AWS credentials are correctly configured.

### Error: Forbidden - Cannot List Nodes

**Symptoms:**
```
Error from server (Forbidden): nodes is forbidden: 
User "system:node:ip-10-0-12-76.ec2.internal" cannot list resource "nodes" 
in API group "" at the cluster scope.
```

**Solution:** Create ClusterRole and ClusterRoleBinding for the role:

```bash
kubectl apply -f - <<EOF
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: eks-admin-binding
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: cluster-admin
subjects:
- kind: User
  name: system:node:ip-10-0-12-76.ec2.internal
EOF
```

### Error: QuickSight S3 Permission Denied

**Symptoms:**
```
PERMISSION_DENIED: User: arn:aws:sts::853973692277:assumed-role/aws-quicksight-service-role-v0/...
is not authorized to perform: s3:ListBucket on resource: "arn:aws:s3:::vignesh-s3-debezium-test"
```

**Solution:** Attach S3 permissions to the QuickSight service role:

1. Navigate to **IAM** → **Roles** → `aws-quicksight-service-role-v0`
2. Add inline policy with S3 ListBucket and GetObject permissions
3. Specify the bucket ARN in the resource section

## References

- [AWS QuickSight Permission Errors](https://repost.aws/knowledge-center/quicksight-permission-errors)
- [GitHub Actions OIDC with AWS](https://docs.github.com/en/actions/deployment/security-hardening-your-deployments/configuring-openid-connect-in-amazon-web-services)
- [EKS Access Entries](https://docs.aws.amazon.com/eks/latest/userguide/access-entries.html)
- [AWS Glue Crawlers](https://docs.aws.amazon.com/glue/latest/dg/add-crawler.html)


