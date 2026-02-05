# AWS SSO Integration for EKS Cluster Analysis

## Overview
The `custom_script_sso.py` has been enhanced to use AWS SSO (Single Sign-On) authentication instead of relying on the current AWS session credentials. This integration is based on the authentication pattern from `sso_cli_based.py`.

## Key Changes

### 1. **SSO Configuration Setup**
- Added `setup_aws_config_for_accounts()` function that automatically configures AWS CLI profiles with SSO settings for each account
- Reads account information from CSV and creates corresponding SSO profiles in `~/.aws/config`
- Backs up existing config file before making changes

### 2. **SSO Authentication**
- Added `run_sso_login()` function that initiates browser-based SSO authentication
- Uses AWS CLI to handle the SSO login flow
- Only needs to authenticate once for all accounts

### 3. **Profile-Based Sessions**
- Modified session creation to use SSO profiles: `boto3.Session(profile_name=account_id, region_name=region)`
- Each account is accessed through its dedicated SSO profile
- Maintains all existing EKS cluster analysis functionality

### 4. **Enhanced Error Handling**
- Added graceful handling of keyboard interrupts
- Automatic cleanup of SSO cache on exit
- Better error messages for authentication failures

### 5. **CSV Format Update**
The CSV file (`accounts_sso.csv`) now requires a `role_name` column:
```csv
account_id,role_name,region
853973692277,limited-admin,"us-east-1,us-west-2"
```

## Configuration Required

Before running the script, update these constants in `custom_script_sso.py`:

```python
SSO_START_URL = "https://pcsg.awsapps.com/start/#/"  # Your SSO start URL
SSO_REGION = "us-east-1"  # Your SSO region
```

## How It Works

1. **Step 1**: Reads all accounts from `accounts_sso.csv`
2. **Step 2**: Sets up AWS CLI profiles with SSO configuration for each account
3. **Step 3**: Prompts for SSO authentication (opens browser)
4. **Step 4**: Processes each account/region using the authenticated SSO session

## Usage

```bash
python custom_script_sso.py
```

### Expected Flow:
1. Script reads account information
2. Configures AWS CLI profiles
3. Opens browser for SSO authentication
4. Processes all EKS clusters across all accounts/regions
5. Generates `output_sso.csv` with cluster analysis
6. Cleans up SSO cache

## Benefits

✅ **Secure**: Uses SSO authentication instead of long-lived credentials  
✅ **Convenient**: Single login for multiple accounts  
✅ **Auditable**: All actions are tied to your SSO identity  
✅ **Compliant**: Follows AWS best practices for authentication  

## Files Modified

- `custom_script_sso.py`: Enhanced with SSO authentication
- `accounts_sso.csv`: Updated format to include role_name column

## Troubleshooting

### "AWS CLI not found"
Install AWS CLI: `pip install awscli`

### "SSO login failed"
- Verify SSO_START_URL and SSO_REGION are correct
- Check your network connection
- Ensure you have access to the specified role in each account

### "Unauthorized access to cluster"
- Verify the IAM role has EKS access entries configured
- Check the role name in the CSV matches what's configured in AWS SSO
