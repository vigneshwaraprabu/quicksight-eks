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

---

## Introduction

This guide provides comprehensive steps to set up AWS QuickSight with EKS clusters, AWS Glue, and GitHub Actions using OIDC authentication for secure, credential-free deployments.

### What You'll Learn
- How to configure OIDC authentication for GitHub Actions
- Setting up EKS access with IAM roles
- Creating AWS Glue crawlers for data cataloging
- Visualizing data in Amazon QuickSight
- Troubleshooting common issues

---

## Prerequisites

Before you begin, ensure you have:

- ✅ AWS account with administrator or appropriate IAM permissions
- ✅ AWS CLI installed and configured ([Installation Guide](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html))
- ✅ Python 3.11 or higher installed
- ✅ GitHub repository with Actions enabled
- ✅ Basic understanding of AWS IAM, EKS, and S3

### Install Required Dependencies

```bash
# Install Python libraries
pip install boto3 kubernetes

# Verify installations
python3 --version
aws --version
kubectl version --client
```

---

## AWS OIDC Authentication Setup

OIDC (OpenID Connect) allows GitHub Actions to authenticate with AWS without storing long-lived credentials.

### Step 1: Create OIDC Identity Provider in AWS IAM

1. Open the **AWS IAM Console**
2. Navigate to **Identity Providers** → **Add Provider**
3. Select **OpenID Connect**
4. Configure:
   - **Provider URL**: `https://token.actions.githubusercontent.com`
   - **Audience**: `sts.amazonaws.com`
5. Click **Get thumbprint** → **Add Provider**

### Step 2: Create IAM Role for GitHub Actions

1. Go to **IAM** → **Roles** → **Create Role**
2. Select **Web Identity** as trusted entity type
3. Choose the OIDC provider you just created
4. Select audience: `sts.amazonaws.com`
5. Attach required policies:
   - `AmazonEC2ReadOnlyAccess`
   - `AmazonEKSClusterPolicy` (read-only)
   - Custom policy for S3 and STS operations

#### Trust Policy Configuration

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

> **Note**: Replace `YOUR_ORG/YOUR_REPO` with your actual GitHub repository path (e.g., `myorg/quicksight-project`)

#### Permissions Policy for OIDC Role

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AssumeTargetRoles",
      "Effect": "Allow",
      "Action": "sts:AssumeRole",
      "Resource": "arn:aws:iam::853973692277:role/EC2RoleforMSK"
    },
    {
      "Sid": "GetCallerIdentity",
      "Effect": "Allow",
      "Action": "sts:GetCallerIdentity",
      "Resource": "*"
    }
  ]
}
```

### Step 3: Update GitHub Actions Workflow

Create or update `.github/workflows/eks-inventory.yml`:

```yaml
name: EKS Inventory with OIDC

on:
  workflow_dispatch:
  push:
    branches: [main]
    paths:
      - 'custom_script.py'
      - '.github/workflows/eks-inventory.yml'

permissions:
  id-token: write   # Required for requesting JWT token
  contents: read    # Required for actions/checkout

jobs:
  run-inventory:
    runs-on: ubuntu-latest
    
    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install boto3 kubernetes

      - name: Configure AWS credentials using OIDC
        uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: arn:aws:iam::853973692277:role/GithubActionsRole
          aws-region: us-east-1

      - name: Verify AWS Identity
        run: |
          echo "Authenticated as:"
          aws sts get-caller-identity

      - name: Run EKS inventory script
        run: |
          python3 custom_script.py --bucket vignesh-s3-debezium-test --account-list accounts.csv

      - name: Upload output artifact
        uses: actions/upload-artifact@v4
        with:
          name: eks-inventory-report
          path: output.csv
```

### Benefits of OIDC

| Benefit | Description |
|---------|-------------|
| 🔒 **No Stored Secrets** | No long-lived credentials in GitHub Secrets |
| 🔄 **Auto-Rotation** | Tokens are short-lived and automatically refreshed |
| 🛡️ **Enhanced Security** | Reduced risk of credential leakage |
| 🎯 **Fine-Grained Control** | Restrict access by repository, branch, or environment |
| 📊 **Audit Trail** | Better tracking of who accessed what |

---

## EKS Access Configuration

### Understanding the Authentication Flow

```
GitHub Actions (OIDC)
       ↓
GithubActionsRole (Initial Auth)
       ↓
Assumes → EC2RoleforMSK (from accounts.csv)
       ↓
Accesses → EKS Cluster
```

> **Important**: The OIDC role only provides initial authentication. The role in `accounts.csv` is what actually accesses the EKS clusters and must have proper EKS access entries.

### Step 1: Required IAM Permissions

The role specified in `accounts.csv` (e.g., `EC2RoleforMSK`) needs these permissions:

#### Inline Policy: EKS-And-EC2-ReadAccess

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
      "Sid": "SSMParameterAccess",
      "Effect": "Allow",
      "Action": "ssm:GetParameter",
      "Resource": "arn:aws:ssm:*:*:parameter/aws/service/eks/optimized-ami/*"
    },
    {
      "Sid": "STSCallerIdentity",
      "Effect": "Allow",
      "Action": "sts:GetCallerIdentity",
      "Resource": "*"
    },
    {
      "Sid": "S3BucketAccess",
      "Effect": "Allow",
      "Action": [
        "s3:PutObject",
        "s3:GetObject",
        "s3:ListBucket"
      ],
      "Resource": [
        "arn:aws:s3:::vignesh-s3-debezium-test",
        "arn:aws:s3:::vignesh-s3-debezium-test/*"
      ]
    }
  ]
}
```

### Step 2: Create EKS Access Entries

For **each** EKS cluster, add the role from `accounts.csv`:

```bash
# Set variables
CLUSTER_NAME="poc-cluster1"
ROLE_ARN="arn:aws:iam::853973692277:role/EC2RoleforMSK"
REGION="us-east-1"

# Create access entry
aws eks create-access-entry \
  --cluster-name $CLUSTER_NAME \
  --principal-arn $ROLE_ARN \
  --type STANDARD \
  --region $REGION

# Associate cluster admin policy
aws eks associate-access-policy \
  --cluster-name $CLUSTER_NAME \
  --principal-arn $ROLE_ARN \
  --policy-arn arn:aws:eks::aws:cluster-access-policy/AmazonEKSClusterAdminPolicy \
  --access-scope type=cluster \
  --region $REGION

# Verify access entries
aws eks list-access-entries \
  --cluster-name $CLUSTER_NAME \
  --region $REGION
```

#### Repeat for All Clusters

```bash
# For pradeep-modmed-cluster
aws eks create-access-entry \
  --cluster-name pradeep-modmed-cluster \
  --principal-arn arn:aws:iam::853973692277:role/EC2RoleforMSK \
  --type STANDARD \
  --region us-east-1

aws eks associate-access-policy \
  --cluster-name pradeep-modmed-cluster \
  --principal-arn arn:aws:iam::853973692277:role/EC2RoleforMSK \
  --policy-arn arn:aws:eks::aws:cluster-access-policy/AmazonEKSClusterAdminPolicy \
  --access-scope type=cluster \
  --region us-east-1
```

### Step 3: Verify Configuration

```bash
# Test role assumption
aws sts assume-role \
  --role-arn arn:aws:iam::853973692277:role/EC2RoleforMSK \
  --role-session-name test-session

# Verify identity
aws sts get-caller-identity

# Test EKS cluster access
aws eks describe-cluster \
  --name poc-cluster1 \
  --region us-east-1

# Test kubectl access
aws eks update-kubeconfig \
  --name poc-cluster1 \
  --region us-east-1

kubectl get nodes
```

---

## AWS Glue Crawler Setup

AWS Glue crawlers automatically discover and catalog data schema from S3.

### Step 1: Create IAM Role for Glue Crawler

1. Go to **IAM** → **Roles** → **Create Role**
2. Select **AWS Glue** as the service
3. Attach policies:
   - `AWSGlueServiceRole`
   - Custom S3 policy (see below)

#### S3 Access Policy for Glue

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
        "arn:aws:s3:::vignesh-s3-debezium-test/reports/*"
      ]
    }
  ]
}
```

### Step 2: Create Glue Database

```bash
# Using AWS CLI
aws glue create-database \
  --database-input '{
    "Name": "eks_inventory_db",
    "Description": "Database for EKS inventory reports"
  }' \
  --region us-east-1

# Or use AWS Console
# Navigate to AWS Glue → Databases → Add database
```

### Step 3: Create and Configure Crawler

1. Open **AWS Glue Console**
2. Navigate to **Crawlers** → **Create crawler**
3. Configure crawler settings:

| Setting | Value |
|---------|-------|
| **Name** | `output-csv-crawler` |
| **Data source** | S3 |
| **S3 path** | `s3://vignesh-s3-debezium-test/reports/` |
| **Crawl all sub-folders** | Yes |
| **IAM role** | GlueServiceRole (created in Step 1) |
| **Target database** | `eks_inventory_db` |
| **Table prefix** | `eks_` (optional) |
| **Schedule** | On demand or Daily at midnight |

### Step 4: Run Crawler

```bash
# Start crawler using AWS CLI
aws glue start-crawler \
  --name output-csv-crawler \
  --region us-east-1

# Check crawler status
aws glue get-crawler \
  --name output-csv-crawler \
  --region us-east-1 \
  --query 'Crawler.State'
```

### Step 5: Verify Table Creation

1. Go to **AWS Glue Console** → **Databases** → `eks_inventory_db`
2. Click on **Tables** → Verify table created
3. Check schema columns match CSV structure:
   - AccountID
   - Region
   - ClusterName
   - ClusterVersion
   - InstanceID
   - AMI_ID
   - etc.

---

## QuickSight Visualization

### Step 1: Setup QuickSight Account

If you haven't already:

1. Go to **Amazon QuickSight Console**
2. Sign up for QuickSight (if first time)
3. Choose **Enterprise** edition for full features
4. Select region: `us-east-1`

### Step 2: Configure QuickSight IAM Role

1. Navigate to **QuickSight** → **Manage QuickSight** → **Security & permissions**
2. Click on **Manage** under IAM role
3. Add inline policy:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "s3:GetObject",
        "s3:GetObjectVersion",
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
        "glue:GetDatabases",
        "glue:GetTable",
        "glue:GetTables",
        "glue:GetPartition",
        "glue:GetPartitions"
      ],
      "Resource": [
        "arn:aws:glue:us-east-1:853973692277:catalog",
        "arn:aws:glue:us-east-1:853973692277:database/eks_inventory_db",
        "arn:aws:glue:us-east-1:853973692277:table/eks_inventory_db/*"
      ]
    }
  ]
}
```

### Step 3: Create Dataset

1. Open **QuickSight Console**
2. Click **Datasets** → **New dataset**
3. Select **AWS Glue** as data source
4. Configure connection:
   - **Data source name**: `EKS Inventory`
   - **Database**: `eks_inventory_db`
   - **Table**: Select the table created by crawler
5. Choose **Import to SPICE** for faster queries
6. Click **Visualize**

### Step 4: Create Analysis and Dashboard

#### Sample Visualizations

1. **Cluster Distribution by Region**
   - Chart type: Pie chart
   - Value: Count of ClusterName
   - Group by: Region

2. **Node Readiness Status**
   - Chart type: KPI
   - Value: Count of NodeReadinessStatus
   - Filter: NodeReadinessStatus = "Ready"

3. **AMI Age Distribution**
   - Chart type: Bar chart
   - Y-axis: Count of InstanceID
   - X-axis: AMI_Age (bins)

4. **Patch Status by Cluster**
   - Chart type: Stacked bar chart
   - Y-axis: Count
   - X-axis: ClusterName
   - Group by: PatchStatus

#### Publish Dashboard

1. Click **Share** → **Publish dashboard**
2. Name: `EKS Inventory Dashboard`
3. Grant access to users/groups
4. Set refresh schedule (optional)

---

## Troubleshooting

### Common Issues and Solutions

#### 1. Error: 401 Unauthorized When Accessing EKS

**Symptoms:**
```
❌ Failed to fetch node readiness for cluster: (401)
Reason: Unauthorized
HTTP response body: {"kind":"Status","apiVersion":"v1","metadata":{},"status":"Failure","message":"Unauthorized","reason":"Unauthorized","code":401}
```

**Root Cause:**  
The role in `accounts.csv` (e.g., `EC2RoleforMSK`) doesn't have EKS access entries.

**Solution:**
```bash
# Add access entry for the role
aws eks create-access-entry \
  --cluster-name YOUR_CLUSTER_NAME \
  --principal-arn arn:aws:iam::853973692277:role/EC2RoleforMSK \
  --type STANDARD \
  --region us-east-1

# Associate admin policy
aws eks associate-access-policy \
  --cluster-name YOUR_CLUSTER_NAME \
  --principal-arn arn:aws:iam::853973692277:role/EC2RoleforMSK \
  --policy-arn arn:aws:eks::aws:cluster-access-policy/AmazonEKSClusterAdminPolicy \
  --access-scope type=cluster \
  --region us-east-1

# Verify
aws eks list-access-entries --cluster-name YOUR_CLUSTER_NAME
```

#### 2. Error: Kubernetes Client Using Wrong Credentials

**Symptoms:**
- Works with admin access keys but fails with OIDC
- `kubectl` commands work locally but not in GitHub Actions

**Root Cause:**  
The Kubernetes Python client uses the AWS SDK's credential chain, which might pick up the original OIDC role credentials instead of the assumed role credentials.

**Solution:**  
Explicitly set environment variables for the assumed role before making Kubernetes API calls:

```python
# Set environment variables before loading kubeconfig
os.environ['AWS_ACCESS_KEY_ID'] = assumed_creds.access_key
os.environ['AWS_SECRET_ACCESS_KEY'] = assumed_creds.secret_key
os.environ['AWS_SESSION_TOKEN'] = assumed_creds.token
```

See the `get_node_readiness()` function in `custom_script.py` for implementation details.

#### 3. Error: QuickSight S3 Permission Denied

**Symptoms:**
```
PERMISSION_DENIED: User: arn:aws:sts::853973692277:assumed-role/aws-quicksight-service-role-v0/...
is not authorized to perform: s3:ListBucket on resource: "arn:aws:s3:::vignesh-s3-debezium-test"
```

**Solution:**
1. Navigate to **IAM** → **Roles** → `aws-quicksight-service-role-v0`
2. Click **Add permissions** → **Create inline policy**
3. Add the S3 policy shown in [Step 2](#step-2-configure-quicksight-iam-role)
4. Save policy

#### 4. Error: Glue Crawler Fails to Create Table

**Symptoms:**
- Crawler runs successfully but no table is created
- Table schema is incorrect

**Solution:**
```bash
# Check crawler logs
aws glue get-crawler \
  --name output-csv-crawler \
  --query 'Crawler.LastCrawl'

# Verify S3 path is correct
aws s3 ls s3://vignesh-s3-debezium-test/reports/

# Ensure CSV file has headers
# Ensure file is not empty

# Re-run crawler
aws glue start-crawler --name output-csv-crawler
```

#### 5. Error: GitHub Actions OIDC Token Expired

**Symptoms:**
```
Error: Could not assume role with OIDC: Token has expired
```

**Solution:**
- OIDC tokens are short-lived (typically 1 hour)
- Ensure the workflow completes within the token validity period
- If needed, split long-running jobs into multiple workflows

---

## Best Practices

### Security

- ✅ Use OIDC instead of long-lived credentials
- ✅ Apply least privilege principle to IAM roles
- ✅ Use separate roles for different environments (dev, staging, prod)
- ✅ Enable AWS CloudTrail for audit logging
- ✅ Regularly rotate IAM access keys (if any)

### Performance

- ✅ Use SPICE in QuickSight for faster queries
- ✅ Schedule Glue crawlers during off-peak hours
- ✅ Implement pagination in Python scripts for large datasets
- ✅ Cache EKS cluster information when possible

### Monitoring

- ✅ Set up CloudWatch alarms for failed GitHub Actions
- ✅ Monitor Glue crawler success/failure rates
- ✅ Track S3 bucket size and costs
- ✅ Use QuickSight usage metrics

---

## References

### AWS Documentation
- [AWS QuickSight Permission Errors](https://repost.aws/knowledge-center/quicksight-permission-errors)
- [EKS Access Entries](https://docs.aws.amazon.com/eks/latest/userguide/access-entries.html)
- [AWS Glue Crawlers](https://docs.aws.amazon.com/glue/latest/dg/add-crawler.html)
- [IAM Roles for OIDC](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_roles_providers_oidc.html)

### GitHub Documentation
- [GitHub Actions OIDC with AWS](https://docs.github.com/en/actions/deployment/security-hardening-your-deployments/configuring-openid-connect-in-amazon-web-services)
- [AWS Actions Configure Credentials](https://github.com/aws-actions/configure-aws-credentials)

### Additional Resources
- [Boto3 Documentation](https://boto3.amazonaws.com/v1/documentation/api/latest/index.html)
- [Kubernetes Python Client](https://github.com/kubernetes-client/python)
- [AWS CLI Command Reference](https://awscli.amazonaws.com/v2/documentation/api/latest/index.html)

---

## Support

For issues or questions:
1. Check the [Troubleshooting](#troubleshooting) section
2. Review GitHub Actions workflow logs
3. Check AWS CloudWatch logs for detailed error messages
4. Consult AWS documentation links above

---

**Last Updated:** February 2025  
**Version:** 1.0


SSO Based authentication:

python3 sso_cli_based.py ## will login and print ec2 instances


aws configure sso
presidio-sandbox
https://pcsg.awsapps.com/start/#/
us-east-1

aws configure sso                    253 ✘  test   01:33:09 PM 
SSO session name (Recommended): presidio-sandbox
SSO start URL [None]: https://pcsg.awsapps.com/start/#/
SSO region [None]: us-east-1
SSO registration scopes [sso:account:access]:
Attempting to open your default browser.
If the browser does not open, open the following URL:

https://oidc.us-east-1.amazonaws.com/authorize?response_type=code&client_id=kK8DPRKuGyGwchxCKyDvInVzLWVhc3QtMQ&redirect_uri=http%3A%2F%2F127.0.0.1%3A61591%2Foauth%2Fcallback&state=958fdcc6-5156-4290-bc1d-b3e5bf533a59&code_challenge_method=S256&scopes=sso%3Aaccount%3Aaccess&code_challenge=ci6-PnXD9ASJukiR6EnPnmCsLhxZZm6MP4XRff3Hplg
The only AWS account available to you is: 853973692277
Using the account ID 853973692277
The only role available to you is: limited-admin
Using the role name "limited-admin"
Default client Region [us-east-1]:
CLI default output format (json if not specified) [None]:
Profile name [limited-admin-853973692277]: presidio-sandbox
To use this profile, specify the profile name using --profile, as shown:

aws sts get-caller-identity --profile presidio-sandbox

aws sso login --profile your-sso-profile





