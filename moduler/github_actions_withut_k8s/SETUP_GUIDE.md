# Quick Setup Guide - Role Assumption Edition

## What Changed

✅ **Removed**: SSO authentication (no browser needed)  
✅ **Added**: AWS IAM role assumption via GitHub Actions OIDC  
✅ **Hardcoded**: S3 upload to account 908676838269 with role PatchingAccess

## Architecture

```
GitHub Actions
    ↓ (OIDC)
GithubActionsRole (853973692277)
    ↓ (AssumeRole)
Account Roles (from accounts.csv)
    ↓ (Analyze)
EKS Clusters
    ↓ (AssumeRole)
PatchingAccess (908676838269)
    ↓ (Upload)
S3 Bucket
```

## Prerequisites Checklist

### ✓ Base Account Setup (853973692277)

- [x] OIDC provider: `token.actions.githubusercontent.com`
- [x] Base role: `GithubActionsRole`
- [ ] Trust policy allows your GitHub repo
- [ ] Permissions include `sts:AssumeRole` for target roles

### ✓ Target Accounts (from accounts.csv)

For each account, ensure the role has:
- [ ] Trust policy allows `GithubActionsRole` to assume it
- [ ] Permissions for: `eks:ListClusters`, `eks:DescribeCluster`
- [ ] Permissions for: `ec2:DescribeInstances`, `ec2:DescribeImages`
- [ ] Permissions for: `ssm:GetParameter`

### ✓ S3 Upload Account (908676838269)

- [ ] Role: `PatchingAccess`
- [ ] Trust policy allows `GithubActionsRole`
- [ ] Permission: `s3:PutObject` to `mmtag-reports/eks-reports/*`

## Required IAM Policies

### 1. Base Role Trust Policy

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
        "StringLike": {
          "token.actions.githubusercontent.com:sub": "repo:YOUR_ORG/YOUR_REPO:*"
        }
      }
    }
  ]
}
```

### 2. Base Role Permissions

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": "sts:AssumeRole",
      "Resource": [
        "arn:aws:iam::*:role/PatchingAccess",
        "arn:aws:iam::*:role/EC2RoleforMSK"
      ]
    },
    {
      "Effect": "Allow",
      "Action": "sts:GetCallerIdentity",
      "Resource": "*"
    }
  ]
}
```

### 3. Target Role Trust Policy

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

### 4. Target Role Permissions

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "sts:GetCallerIdentity",
        "eks:ListClusters",
        "eks:DescribeCluster",
        "ec2:DescribeInstances",
        "ec2:DescribeImages"
      ],
      "Resource": "*"
    },
    {
      "Effect": "Allow",
      "Action": "ssm:GetParameter",
      "Resource": [
        "arn:aws:ssm:*:*:parameter/aws/service/eks/optimized-ami/*",
        "arn:aws:ssm:*:*:parameter/aws/service/bottlerocket/*"
      ]
    }
  ]
}
```

### 5. S3 Role Additional Permission

```json
{
  "Effect": "Allow",
  "Action": "s3:PutObject",
  "Resource": "arn:aws:s3:::vignesh-s3-debezium-test/eks-reports/*"
}
```

## Testing

### 1. Verify Base Role

```bash
# Manually assume base role
aws sts assume-role \
  --role-arn arn:aws:iam::853973692277:role/GithubActionsRole \
  --role-session-name test

# If successful, you'll get credentials
```

### 2. Test Target Role Assumption

```bash
# Assume target role from base role
aws sts assume-role \
  --role-arn arn:aws:iam::ACCOUNT_ID:role/PatchingAccess \
  --role-session-name test
```

### 3. Test EKS Access

```bash
# After assuming target role
aws eks list-clusters --region us-east-1
```

### 4. Test S3 Upload

```bash
# After assuming S3 role
aws s3 cp test.txt s3://vignesh-s3-debezium-test/eks-reports/
```

## Running the Script

### From GitHub Actions

The workflow automatically runs on:
- Manual trigger (`workflow_dispatch`)
- Push to workflow file or script

### Locally (for testing)

```bash
# 1. Set up AWS credentials (assume base role manually)
export AWS_ACCESS_KEY_ID="..."
export AWS_SECRET_ACCESS_KEY="..."
export AWS_SESSION_TOKEN="..."

# 2. Run the script
cd quicksight/moduler/github_actions_withut_k8s
python3 eks_analyzer.py --account-list accounts.csv
```

## Troubleshooting

### ❌ "Failed to get base caller identity"

**Problem**: GitHub Actions can't assume base role

**Fix**:
1. Check OIDC provider exists in base account
2. Verify trust policy on `GithubActionsRole`
3. Ensure workflow has `id-token: write` permission

### ❌ "Access denied assuming role"

**Problem**: Base role can't assume target role

**Fix**:
1. Check trust policy on target role
2. Verify base role has `sts:AssumeRole` permission
3. Ensure role name matches accounts.csv

### ❌ "Access denied to list EKS clusters"

**Problem**: Target role missing EKS permissions

**Fix**:
1. Add EKS permissions to target role policy
2. Check for SCPs blocking EKS access

### ❌ "Failed to assume S3 upload role"

**Problem**: Can't assume role in S3 account

**Fix**:
1. Verify hardcoded values in `role_assumption.py`:
   - `S3_UPLOAD_ACCOUNT = "908676838269"`
   - `S3_UPLOAD_ROLE = "PatchingAccess"`
2. Check trust policy on S3 role

## Files Modified

```
✓ modules/role_assumption.py          (NEW - handles role assumption)
✓ modules/aws_session.py               (MODIFIED - accepts boto3 session)
✓ eks_analyzer.py                      (MODIFIED - uses role assumption)
✓ .github/workflows/gha_without_k8s.yml (MODIFIED - updated run command)
✓ README_GITHUB_ACTIONS.md             (NEW - comprehensive docs)
```

## Files No Longer Used

```
✗ modules/sso_auth.py                  (Not needed for GitHub Actions)
✗ modules/kubernetes_operations.py     (Not used in withut_k8s version)
```

## Next Steps

1. **Review IAM policies** in all accounts
2. **Update trust policies** to allow role assumption
3. **Test locally** with manual role assumption
4. **Trigger workflow** in GitHub Actions
5. **Monitor CloudTrail** for role assumption activity

## Support

- **Documentation**: See `README_GITHUB_ACTIONS.md`
- **Logs**: Check GitHub Actions workflow logs
- **IAM**: Review CloudTrail for AssumeRole events
