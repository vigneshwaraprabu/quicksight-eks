# GitHub Actions OIDC Setup Guide

This guide shows you how to set up the **GithubActionsRole** in AWS account **853973692277** to allow GitHub Actions to authenticate using OIDC (OpenID Connect).

## Why OIDC Instead of Access Keys?

✅ **More Secure**: No long-lived credentials stored in GitHub  
✅ **Automatic Rotation**: Tokens are short-lived and auto-renewed  
✅ **Auditable**: CloudTrail logs all role assumptions  
✅ **No Secret Management**: No need to manage AWS access keys

## Step-by-Step Setup

### Step 1: Create OIDC Provider in AWS

1. **Log in to AWS Console** for account **853973692277**

2. **Go to IAM** → **Identity providers** → **Add provider**

3. **Configure the provider**:
   - **Provider type**: OpenID Connect
   - **Provider URL**: `https://token.actions.githubusercontent.com`
   - **Audience**: `sts.amazonaws.com`

4. **Click "Get thumbprint"** (AWS will automatically fetch it)

5. **Click "Add provider"**

#### Using AWS CLI:

```bash
aws iam create-open-id-connect-provider \
  --url https://token.actions.githubusercontent.com \
  --client-id-list sts.amazonaws.com \
  --thumbprint-list 6938fd4d98bab03faadb97b34396831e3780aea1 \
  --region us-east-1 \
  --profile <your-profile-for-853973692277>
```

### Step 2: Create the GithubActionsRole

1. **Go to IAM** → **Roles** → **Create role**

2. **Select trusted entity**: Web identity

3. **Configure web identity**:
   - **Identity provider**: `token.actions.githubusercontent.com`
   - **Audience**: `sts.amazonaws.com`

4. **Add condition** (important for security):
   - Click "Add condition"
   - **Condition key**: `token.actions.githubusercontent.com:sub`
   - **Operator**: StringLike
   - **Value**: `repo:YOUR_ORG/YOUR_REPO:*`
   
   Example: `repo:ModMed/eks-analyzer:*`

5. **Attach permissions** (see Step 3)

6. **Name the role**: `GithubActionsRole`

7. **Create the role**

#### Using AWS CLI:

First, create a trust policy file `github-trust-policy.json`:

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

**Replace**: `YOUR_ORG/YOUR_REPO` with your actual GitHub organization and repository name.

Then create the role:

```bash
aws iam create-role \
  --role-name GithubActionsRole \
  --assume-role-policy-document file://github-trust-policy.json \
  --description "Role for GitHub Actions OIDC authentication" \
  --profile <your-profile-for-853973692277>
```

### Step 3: Attach Permissions to GithubActionsRole

The role needs permission to assume other roles in target accounts.

Create a permissions policy file `github-role-permissions.json`:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AssumeTargetAccountRoles",
      "Effect": "Allow",
      "Action": "sts:AssumeRole",
      "Resource": [
        "arn:aws:iam::*:role/PatchingAccess"
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

**Attach the policy**:

```bash
# Create the policy
aws iam create-policy \
  --policy-name GithubActionsAssumeRolePolicy \
  --policy-document file://github-role-permissions.json \
  --profile <your-profile-for-853973692277>

# Attach to the role
aws iam attach-role-policy \
  --role-name GithubActionsRole \
  --policy-arn arn:aws:iam::853973692277:policy/GithubActionsAssumeRolePolicy \
  --profile <your-profile-for-853973692277>
```

Or use an inline policy:

```bash
aws iam put-role-policy \
  --role-name GithubActionsRole \
  --policy-name AssumeTargetRoles \
  --policy-document file://github-role-permissions.json \
  --profile <your-profile-for-853973692277>
```

### Step 4: Configure Target Account Roles

For each target account in your `accounts.csv`, the role (e.g., `PatchingAccess` or `EC2RoleforMSK`) must trust the GithubActionsRole.

Create trust policy for target roles `target-trust-policy.json`:

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

**For each target account**:

```bash
# Update the trust policy for the role
aws iam update-assume-role-policy \
  --role-name PatchingAccess \
  --policy-document file://target-trust-policy.json \
  --profile <profile-for-target-account>
```

### Step 5: Verify the Setup

#### Test OIDC Provider

```bash
aws iam get-open-id-connect-provider \
  --open-id-connect-provider-arn arn:aws:iam::853973692277:oidc-provider/token.actions.githubusercontent.com \
  --profile <your-profile-for-853973692277>
```

#### Test Role Trust Policy

```bash
aws iam get-role \
  --role-name GithubActionsRole \
  --profile <your-profile-for-853973692277>
```

Check the `AssumeRolePolicyDocument` includes your GitHub repository.

#### Test from GitHub Actions

Trigger your workflow and check the "Verify Initial OIDC Identity" step output:

```bash
aws sts get-caller-identity
```

Expected output:
```json
{
    "UserId": "AROA...:GitHubActions",
    "Account": "853973692277",
    "Arn": "arn:aws:sts::853973692277:assumed-role/GithubActionsRole/GitHubActions"
}
```

## Security Best Practices

### 1. Restrict by Repository

Always limit which repositories can assume the role:

```json
"Condition": {
  "StringLike": {
    "token.actions.githubusercontent.com:sub": "repo:YOUR_ORG/YOUR_REPO:*"
  }
}
```

### 2. Restrict by Branch (Optional)

For production, restrict to specific branches:

```json
"Condition": {
  "StringLike": {
    "token.actions.githubusercontent.com:sub": "repo:YOUR_ORG/YOUR_REPO:ref:refs/heads/main"
  }
}
```

### 3. Restrict by Environment (Optional)

If using GitHub environments:

```json
"Condition": {
  "StringLike": {
    "token.actions.githubusercontent.com:sub": "repo:YOUR_ORG/YOUR_REPO:environment:production"
  }
}
```

### 4. Enable CloudTrail

Monitor all role assumptions:

```bash
aws cloudtrail lookup-events \
  --lookup-attributes AttributeKey=ResourceName,AttributeValue=GithubActionsRole \
  --profile <your-profile-for-853973692277>
```

## Troubleshooting

### Error: "Not authorized to perform sts:AssumeRoleWithWebIdentity"

**Cause**: OIDC provider not configured or trust policy incorrect

**Fix**:
1. Verify OIDC provider exists in IAM
2. Check trust policy on GithubActionsRole
3. Ensure `token.actions.githubusercontent.com:sub` matches your repo

### Error: "No OpenIDConnect provider found"

**Cause**: OIDC provider not created

**Fix**: Go back to Step 1 and create the OIDC provider

### Error: "Subject does not match"

**Cause**: Repository name in trust policy doesn't match actual repo

**Fix**: Update trust policy with correct `repo:ORG/REPO:*` format

### Error: "Access Denied" when assuming target roles

**Cause**: Target roles don't trust GithubActionsRole

**Fix**: Update trust policies in target accounts (Step 4)

## Workflow Configuration

Your workflow should include:

```yaml
permissions:
  id-token: write   # Required for OIDC
  contents: read

jobs:
  your-job:
    runs-on: ubuntu-latest
    steps:
      - name: Configure AWS credentials
        uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: arn:aws:iam::853973692277:role/GithubActionsRole
          aws-region: us-east-1
```

## Quick Verification Checklist

- [ ] OIDC provider created in account 853973692277
- [ ] GithubActionsRole created with correct trust policy
- [ ] Trust policy includes your GitHub repository
- [ ] GithubActionsRole has permission to assume target roles
- [ ] Target account roles trust GithubActionsRole
- [ ] Workflow has `id-token: write` permission
- [ ] Workflow uses `aws-actions/configure-aws-credentials@v4`

## Complete Example

Here's a complete trust policy for GithubActionsRole:

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
          "token.actions.githubusercontent.com:sub": [
            "repo:ModMed/eks-analyzer:*",
            "repo:ModMed/infrastructure:*"
          ]
        }
      }
    }
  ]
}
```

## References

- [AWS Documentation: OIDC with GitHub Actions](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_roles_providers_create_oidc.html)
- [GitHub Documentation: OIDC with AWS](https://docs.github.com/en/actions/deployment/security-hardening-your-deployments/configuring-openid-connect-in-amazon-web-services)
- [GitHub Actions: configure-aws-credentials](https://github.com/aws-actions/configure-aws-credentials)

## Support

If you encounter issues:
1. Check GitHub Actions workflow logs
2. Review IAM role trust policies
3. Check CloudTrail for detailed error messages
4. Verify OIDC provider thumbprint is correct
