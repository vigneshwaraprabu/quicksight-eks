# Quick Start Guide - SSO Integration

## Prerequisites
```bash
pip install boto3 kubernetes awscli
```

## Setup Steps

### 1. Configure SSO Settings
Edit [custom_script_sso.py](custom_script_sso.py#L17-L18):
```python
SSO_START_URL = "https://your-org.awsapps.com/start/#/"  # Your SSO URL
SSO_REGION = "us-east-1"  # Your SSO region
```

### 2. Prepare Account CSV
Edit [accounts_sso.csv](accounts_sso.csv) with your AWS accounts:
```csv
account_id,role_name,region
853973692277,limited-admin,"us-east-1,us-west-2"
123456789012,AdminRole,us-east-1
```

**CSV Format:**
- `account_id`: AWS account ID
- `role_name`: SSO role name (e.g., "limited-admin", "AdminRole")
- `region`: Single region or comma-separated list

### 3. Run the Script
```bash
cd /Users/vigneshwaraprabu/Downloads/ModMed/git/quicksight
python custom_script_sso.py
```

## What Happens

### Step 1: Reads Accounts
```
[Step 1/4] Reading account information from CSV...
✅ Found 2 account(s) to process
```

### Step 2: Configures Profiles
```
[Step 2/4] Setting up AWS SSO configuration...
📋 Backed up existing file to /Users/xxx/.aws/config.backup_20260205_143022
✅ Added SSO profiles to /Users/xxx/.aws/config
```

### Step 3: SSO Login
```
[Step 3/4] Authenticating via AWS SSO...
🔐 Starting AWS SSO login...
This will open your browser for authentication.
✅ SSO login successful!
```
*Your browser will open for authentication*

### Step 4: Processes Clusters
```
[Step 4/4] Processing EKS clusters for all accounts...
🔄 Processing account 853973692277 (us-east-1) ...
=== Account: 853973692277 | Region: us-east-1 | UserId: xxx | Arn: xxx ===
EKS Clusters:
 - my-cluster-1: Instance i-0abc123 (AMI: ami-xyz, Type: t3.large)
✅ Success
```

### Cleanup
```
[Cleanup] Removing SSO authentication cache...
✅ Cleaned up SSO cache at /Users/xxx/.aws/sso/cache
```

## Output

Results are written to `output_sso.csv`:
```csv
AccountID,Region,ClusterName,ClusterVersion,InstanceID,AMI_ID,AMI_Age,OS_Version,...
853973692277,us-east-1,my-cluster,1.28,i-0abc123,ami-xyz,45 days,Amazon Linux 2,...
```

## Troubleshooting

### Browser doesn't open
- Check your default browser settings
- Try running: `aws sso login --profile <account_id>` manually

### "Unauthorized access to cluster"
- Ensure the SSO role has EKS access entries
- Check IAM permissions for EKS and EC2

### "AWS CLI not found"
```bash
pip install awscli
# or
brew install awscli  # macOS
```

### Multiple regions not working
Ensure proper CSV format with quotes:
```csv
account_id,role_name,region
123456789012,MyRole,"us-east-1,us-west-2,eu-west-1"
```

## Key Differences from Original

| Aspect | Original (`custom_script.py`) | New SSO Version |
|--------|------------------------------|-----------------|
| **Authentication** | Uses current AWS credentials | SSO browser-based login |
| **Multi-account** | Manual credential switching | Automatic via profiles |
| **CSV Format** | `account_id,region` | `account_id,role_name,region` |
| **Setup** | Manual config | Automatic profile creation |
| **Security** | Depends on credential management | Short-lived SSO tokens |

## Files Created/Modified

- ✅ [custom_script_sso.py](custom_script_sso.py) - Main script with SSO
- ✅ [accounts_sso.csv](accounts_sso.csv) - Account configuration
- 📝 [SSO_INTEGRATION_README.md](SSO_INTEGRATION_README.md) - Detailed docs
- 📝 [CHANGES_SUMMARY.md](CHANGES_SUMMARY.md) - What changed
- 📝 [QUICKSTART.md](QUICKSTART.md) - This file

## Reference Implementation

The SSO pattern was adapted from [sso_cli_based.py](sso_cli_based.py), which demonstrates:
- AWS config file management
- SSO login flow
- Profile-based session creation
- Cleanup procedures
