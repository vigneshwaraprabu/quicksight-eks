# EKS Cluster Analyzer - GitHub Actions Edition

This version uses AWS IAM role assumption for GitHub Actions instead of SSO authentication.

## Architecture Flow

```
GitHub Actions (OIDC)
    ↓ assumes
Base Role (GithubActionsRole in 853973692277)
    ↓ assumes
Target Account Roles (from accounts.csv)
    ↓ analyzes
EKS Clusters & Nodes
    ↓ saves to
CSV File
    ↓ assumes
S3 Upload Role (908676838269/PatchingAccess)
    ↓ uploads to
S3 Bucket (mmtag-reports)
```

## Prerequisites

### 1. GitHub OIDC Configuration

Your base account (853973692277) already has:
- **OIDC Provider**: `token.actions.githubusercontent.com`
- **Base Role**: `GithubActionsRole`

### 2. Required IAM Policies

#### Base Role (GithubActionsRole) - Trust Policy

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

#### Base Role - Permissions Policy

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AssumeTargetRoles",
      "Effect": "Allow",
      "Action": "sts:AssumeRole",
      "Resource": [
        "arn:aws:iam::*:role/PatchingAccess",
        "arn:aws:iam::*:role/EC2RoleforMSK"
      ]
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

### 3. Target Account Roles

Each target account needs a role (e.g., `PatchingAccess` or `EC2RoleforMSK`) with:

#### Trust Policy

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "AWS": "arn:aws:iam::853973692277:role/GithubActionsRole"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
```

#### Permissions Policy

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Sid": "STSAccess",
            "Effect": "Allow",
            "Action": "sts:GetCallerIdentity",
            "Resource": "*"
        },
        {
            "Sid": "EKSReadAccess",
            "Effect": "Allow",
            "Action": [
                "eks:ListClusters",
                "eks:DescribeCluster"
            ],
            "Resource": "*"
        },
        {
            "Sid": "EC2ReadAccess",
            "Effect": "Allow",
            "Action": [
                "ec2:DescribeInstances",
                "ec2:DescribeImages"
            ],
            "Resource": "*"
        },
        {
            "Sid": "SSMParameterReadAccess",
            "Effect": "Allow",
            "Action": "ssm:GetParameter",
            "Resource": [
                "arn:aws:ssm:*:*:parameter/aws/service/eks/optimized-ami/*",
                "arn:aws:ssm:*:*:parameter/aws/service/bottlerocket/*"
            ]
        },
        {
            "Sid": "AccountInfoAccess",
            "Effect": "Allow",
            "Action": [
                "iam:ListAccountAliases",
                "organizations:DescribeAccount"
            ],
            "Resource": "*"
        },
        {
            "Sid": "S3UploadAccess",
            "Effect": "Allow",
            "Action": [
                "s3:PutObject"
            ],
            "Resource": "arn:aws:s3:::vignesh-s3-debezium-test/*"
        }
    ]
}
```

### 4. S3 Upload Role

In account **908676838269**, the **PatchingAccess** role needs:

#### Trust Policy
(Same as target accounts - allows GithubActionsRole to assume it)

#### Additional Permissions

```json
{
  "Sid": "S3UploadAccess",
  "Effect": "Allow",
  "Action": "s3:PutObject",
  "Resource": "arn:aws:s3:::mmtag-reports/eks-reports/*"
}
```

## Usage

### Input File: accounts.csv

```csv
account_id,role_name,region
562238536321,PatchingAccess,us-east-1
244564253140,PatchingAccess,"us-east-1,us-west-2"
853973692277,EC2RoleforMSK,us-east-1
```

### Command Line

```bash
# Basic usage (from workflow directory)
cd quicksight/moduler/github_actions_withut_k8s
python eks_analyzer.py

# Custom CSV file
python eks_analyzer.py --account-list my_accounts.csv

# Custom S3 destination
python eks_analyzer.py --s3-bucket my-bucket --s3-prefix reports/eks

# Skip S3 upload (local only)
python eks_analyzer.py --skip-s3
```

### GitHub Actions Workflow

The workflow file is at `.github/workflows/gha_without_k8s.yml`:

```yaml
- name: Generate kubeconfig for all EKS clusters
  run: |
    python3 moduler/github_actions_withut_k8s/eks_analyzer.py \
      --s3-bucket vignesh-s3-debezium-test \
      --account-list "accounts.csv"
```

## Output

### CSV File

**Filename**: `eks_analysis_output_YYYY_MM_DD.csv`

**Columns** (19 total):
- AccountID, AccountName, Region, ClusterName, ClusterVersion
- InstanceID, Current_AMI_ID, Current_AMI_Publication_Date, AMI_Age(in days)
- OS_Version, InstanceType, NodeState, NodeUptime
- Latest_AMI_ID, New_AMI_Publication_Date
- PatchPendingStatus, NodeReadinessStatus, Cluster_Compliance
- Audit_Timestamp

### S3 Upload

- **Bucket**: Configurable (default: `mmtag-reports`)
- **Prefix**: Configurable (default: `eks-reports`)
- **Filename**: Preserves original name (not timestamped)
- **Location**: `s3://mmtag-reports/eks-reports/eks_analysis_output_YYYY_MM_DD.csv`

### GitHub Actions Artifacts

Results are also uploaded as workflow artifacts:
- **Name**: `eks-inventory-output`
- **Retention**: 30 days
- **File**: `output.csv`

## Key Changes from SSO Version

| Feature | SSO Version | GitHub Actions Version |
|---------|-------------|------------------------|
| Authentication | Browser-based SSO | OIDC + Role Assumption |
| Session Management | SSO profiles | Boto3 sessions from AssumeRole |
| Credentials | Temporary SSO tokens | Temporary role credentials |
| Profile Setup | AWS config file | Not required |
| Browser Required | Yes | No |
| Cleanup | SSO cache cleanup | No cleanup needed |

## Configuration

### Hardcoded Values

In `modules/role_assumption.py`:

```python
S3_UPLOAD_ACCOUNT = "908676838269"
S3_UPLOAD_ROLE = "PatchingAccess"
```

To change these, edit the `RoleAssumption` class.

### Session Duration

Role sessions last 1 hour (3600 seconds). To adjust:

```python
# In modules/role_assumption.py, assume_role method
DurationSeconds=3600  # Change to desired duration (900-43200)
```

## Troubleshooting

### Error: "Failed to get base caller identity"

**Cause**: GitHub Actions couldn't assume the base role

**Solutions**:
1. Verify OIDC provider is configured in base account
2. Check base role trust policy allows your repository
3. Ensure workflow has `id-token: write` permission
4. Verify `role-to-assume` ARN in workflow file

### Error: "Access denied assuming role"

**Cause**: Base role can't assume target account role

**Solutions**:
1. Check target role trust policy allows base role ARN
2. Verify base role has `sts:AssumeRole` permission
3. Ensure role name in accounts.csv matches actual role
4. Check for SCPs blocking cross-account access

### Error: "Access denied to list EKS clusters"

**Cause**: Target role missing EKS permissions

**Solutions**:
1. Add `eks:ListClusters` and `eks:DescribeCluster` to target role
2. Check for SCPs blocking EKS access
3. Verify region is enabled in the account

### Error: "Failed to assume S3 upload role"

**Cause**: Can't assume role in S3 account (908676838269)

**Solutions**:
1. Verify S3 account ID and role name in `role_assumption.py`
2. Check trust policy on S3 account role
3. Ensure base role can assume role in S3 account

## API Calls Summary

### From Base Role (GithubActionsRole)
- `sts:GetCallerIdentity` - Verify base credentials
- `sts:AssumeRole` - Assume target account roles

### From Target Account Roles
- `sts:GetCallerIdentity` - Verify assumed credentials
- `eks:ListClusters` - List EKS clusters
- `eks:DescribeCluster` - Get cluster details
- `ec2:DescribeInstances` - Get node instances
- `ec2:DescribeImages` - Get AMI metadata
- `ssm:GetParameter` - Fetch latest AMI IDs

### From S3 Upload Role
- `sts:GetCallerIdentity` - Verify assumed credentials
- `s3:PutObject` - Upload CSV report

## Testing Locally

To test role assumption locally (without GitHub Actions):

```bash
# Assume the base role manually
aws sts assume-role \
  --role-arn arn:aws:iam::853973692277:role/GithubActionsRole \
  --role-session-name local-test

# Export credentials
export AWS_ACCESS_KEY_ID="..."
export AWS_SECRET_ACCESS_KEY="..."
export AWS_SESSION_TOKEN="..."

# Run the script
python eks_analyzer.py
```

## Security Best Practices

1. **Least Privilege**: Grant only necessary permissions to each role
2. **Trust Policies**: Restrict role assumption to specific principals
3. **Session Duration**: Use minimum required duration (default: 1 hour)
4. **Audit Logging**: Enable CloudTrail for all role assumptions
5. **Repository Protection**: Restrict workflow triggers to protected branches
6. **Secret Management**: Never hardcode credentials

## Monitoring

### CloudWatch Metrics

Monitor these for anomalies:
- IAM role assumption frequency
- Failed role assumption attempts
- S3 PutObject operations

### CloudTrail Events

Key events to monitor:
- `AssumeRole` - Role assumption activity
- `AssumeRoleWithWebIdentity` - OIDC authentication
- `PutObject` - S3 uploads

## Support

For issues:
1. Check GitHub Actions workflow logs for detailed error messages
2. Verify IAM policies and trust relationships
3. Test role assumption manually using AWS CLI
4. Review CloudTrail logs for denied API calls

## Module Reference

### `role_assumption.py`
- `assume_role()` - Assume role in target account
- `assume_s3_upload_role()` - Assume hardcoded S3 upload role
- `get_base_caller_identity()` - Verify base session

### `aws_session.py`
- `__init__(session, region)` - Initialize with boto3 session
- `get_caller_identity()` - Get current identity
- `get_account_name()` - Get friendly account name
- `print_identity()` - Log current identity

### `eks_analyzer.py`
- `main()` - Entry point
- `parse_arguments()` - CLI argument parsing
