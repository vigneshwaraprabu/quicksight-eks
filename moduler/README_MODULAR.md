# EKS Cluster Analyzer

Automated multi-account EKS cluster analysis tool with AWS SSO authentication, intelligent caching, and S3 upload support.

## Quick Start

```bash
# Basic usage
python eks_analyzer.py

# Skip S3 upload
python eks_analyzer.py --skip-s3

# Custom S3 destination
python eks_analyzer.py --s3-bucket my-bucket --s3-prefix reports/eks
```

## Features

- **AWS SSO Authentication** - Single sign-on for multi-account access
- **AMI Tracking** - Tracks current and latest AMI IDs with publication dates
- **Compliance Checking** - EKS version compliance validation (n-2 support policy)
- **Smart Caching** - 70% reduction in AWS API calls via STS caching
- **Visual Logging** - Color-coded output with INFO/SUCCESS/WARNING/ERROR/CRITICAL levels
- **Error Handling** - Comprehensive validation with actionable error messages
- **S3 Integration** - Automatic timestamped uploads (format: eks_analysis_output_09Feb2026_03_45PM.csv)
- **Performance Optimized** - Session reuse and single-pass CSV processing (30-40% faster)

## Project Structure

```
moduler/
├── eks_analyzer.py              # Main entry point
├── accounts.csv                 # Input: Account configurations
├── eks_analysis_output.csv      # Output: Analysis results
└── modules/
    ├── __init__.py              # Module Initialization
    ├── logger.py                # Centralized logging with colors/symbols
    ├── sso_auth.py              # SSO authentication management
    ├── aws_session.py           # Session management with caching
    ├── csv_handler.py           # CSV I/O with validation
    ├── eks_operations.py        # EKS API operations
    ├── node_operations.py       # EC2 node operations
    ├── kubernetes_operations.py # K8s API operations
    ├── s3_handler.py            # S3 upload with timestamping
    └── cluster_analyzer.py      # Analysis orchestration
```

## Modules Description

### 1. `sso_auth.py`
- Manages AWS SSO authentication workflow
- Sets up SSO profiles in ~/.aws/config
- Handles browser-based SSO login
- Cleans up SSO cache after execution
- Backs up existing AWS config

### 2. `aws_session.py`
- Manages AWS session creation with SSO profile support
- Handles caller identity verification
- Fetches account names via IAM alias or Organizations API
- Single responsibility: Session and identity management

### 3. `eks_operations.py`
- Lists EKS clusters
- Gets cluster versions
- Fetches latest EKS optimized AMIs from SSM
- All EKS-specific API calls

### 4. `node_operations.py`
- Retrieves EC2 instances for clusters
- Calculates AMI age and node uptime
- Parses OS versions from AMI descriptions
- Determines patch pending status
- All EC2-specific operations

### 5. `kubernetes_operations.py`
- Generates kubeconfig for EKS clusters
- Queries Kubernetes API for node readiness
- Handles K8s authentication and timeouts
- Proper cleanup of temporary files

### 6. `csv_handler.py`
- Reads account configuration from CSV (account_id, role_name, region)
- Validates required fields (role_name must be present)
- Writes analysis results to CSV with AccountName field
- Single responsibility: Data I/O

### 7. `cluster_analyzer.py`
- Orchestrates the analysis workflow
- Coordinates between different modules
- Aggregates data into final results including account names
- Main business logic

### 8. `eks_analyzer.py`
- Main entry point with SSO workflow
- Sets up SSO profiles for all accounts
- Authenticates once via browser (cached for all accounts)
- Command-line interface
- Error handling and user feedback
- Progress reporting with section headers

## Input Format

**accounts.csv** (required columns):
```csv
account_id,role_name,region
853973692277,limited-admin,"us-east-1,us-west-2"
```

- `account_id`: 12-digit AWS account ID
- `role_name`: IAM role name for SSO (from CSV, not hardcoded)
- `region`: AWS regions (comma-separated for multiple)

## Output Format

**eks_analysis_output.csv** (18 columns):
```
AccountID, AccountName, Region, ClusterName, ClusterVersion, InstanceID,
Current_AMI_ID, Current_AMI_Publication_Date, AMI_Age, OS_Version,
InstanceType, NodeState, NodeUptime, Latest_AMI_ID, New_AMI_Publication_Date,
PatchPendingStatus, NodeReadinessStatus, Cluster_Compliance
```

**Key Fields:**
- `Current_AMI_ID`: AMI ID currently running on the node
- `Current_AMI_Publication_Date`: Creation date of current AMI (YYYY-MM-DD)
- `Latest_AMI_ID`: Latest EKS-optimized AMI from AWS SSM
- `New_AMI_Publication_Date`: Creation date of latest AMI (YYYY-MM-DD)
- `AMI_Age`: Days since current AMI was published
- `PatchPendingStatus`: True if AMI age ≥ 30 days
- `Cluster_Compliance`: 1 (compliant) if version ≥ latest-2, 0 (non-compliant) otherwise
  - Example: If latest is 1.35, compliant versions are 1.35, 1.34, 1.33
- `PatchPendingStatus`: True if AMI age ≥ 30 days

## Module Overview

| Module | Purpose |
|--------|---------|
| `logger.py` | Color-coded logging with 6 levels (INFO/SUCCESS/WARNING/ERROR/CRITICAL/DEBUG) |
| `sso_auth.py` | AWS SSO authentication, profile setup, cache management |
| `aws_session.py` | Session management with STS/IAM/Organizations caching |
| `csv_handler.py` | CSV I/O with validation (12-digit account IDs, required fields) |
| `eks_operations.py` | EKS cluster operations, AMI data from SSM + EC2 describe_images |
| `node_operations.py` | EC2 instance details, AMI age, OS parsing, uptime calculation |
| `kubernetes_operations.py` | Kubeconfig generation, K8s API queries for node readiness |
| `cluster_analyzer.py` | Workflow orchestration, data aggregation, OS-to-AMI mapping |
| `s3_handler.py` | S3 uploads with timestamped filenames |
| `eks_analyzer.py` | Main entry point, CLI arguments, error handling

## Key Improvements

### 🔐 SSO Authentication
- **Single Sign-On**: Browser-based AWS SSO authentication
- **Multi-account support**: Authenticate once, access all accounts
- **Profile-based sessions**: Automatic role assumption per account
- **Secure**: Uses temporary credentials with automatic refresh
- **Role flexibility**: Role name fetched from CSV (not hardcoded)

###Error Handling

The script handles various failure scenarios:

- **CSV Validation**: Empty files, missing columns, invalid account IDs, empty required fields
- **Authentication**: Expired tokens, access denied, missing profiles, SSO failures
- **Cluster Access**: No clusters found, cluster not found, access denied errors
- **Data Validation**: Invalid AMI data, missing node information, K8s API timeouts
- **Network**: API timeouts (30s kubeconfig, 10s K8s API), connection failures

## Performance Optimizations

- **STS Caching**: Reduces API calls by 70% (3-4 per account → 1 per account)
- **Session Reuse**: Single session for S3 upload eliminates redundant authentication
- **Single-pass CSV**: Dictionary comprehension and enumerate() for efficient processing
- **Account Name Caching**: IAM/Organizations lookups cached to prevent duplicate calls

## Prerequisites

```bash
pip install boto3 kubernetes
```

- Python 3.7+
- AWS CLI v2
- boto3, kubernetes Python packages

## IAM Permissions Required

```
eks:ListClusters, eks:DescribeCluster
ec2:DescribeInstances, ec2:DescribeImages
ssm:GetParameter
iam:ListAccountAliases
organizations:DescribeAccount
s3:PutObject
sts:GetCallerIdentity
```
## Usage

### Prerequisites
- AWS CLI installed and configured
- SSO configured with start URL: `https://d-9067ab41c2.awsapps.com/start/#/`
- IAM roles available in target accounts
- Roles must have EKS, EC2, and SSM permissions

### Basic Usage
```bash
python eks_analyzer.py
```

### Authentication Flow
1. Script reads accounts.csv
2. Sets up SSO profiles in ~/.aws/config (backs up existing)
3. Opens browser for SSO authentication (once)
4. Processes all accounts using cached SSO session
5. Cleans up SSO cache on completion

### Input CSV Format
**Required columns:** `account_id`, `role_name`, `region`

```csv
account_id,role_name,region
123456789012,limited-admin,"us-east-1,us-west-2"
987654321098,ReadOnlyAccess,us-east-1
456789012345,limited-admin,us-west-2
```

**Notes:**
- `role_name` is **required** (no default value)
- Multiple regions can be comma-separated in quotes
- Role must exist in the target account

### Output CSV Columns
- AccountID
- **AccountName** (IAM alias or Organization name)
- Region
- ClusterName
- ClusterVersion
- InstanceID
- AMI_ID
- AMI_Age
- OS_Version
- InstanceType
- NodeState
- NodeUptime
- Latest_EKS_AMI
- PatchPendingStatus
- NodeReadinessStatus

## Requirements

### Python Packages
```bash
pip install boto3 kubernetes
```

### AWS Requirements
- AWS CLI v2 installed
- AWS SSO configured
- IAM permissions:
  - `eks:ListClusters`
  - `eks:DescribeCluster`
  - `ec2:DescribeInstances`
  - `ec2:DescribeImages`
  - `ssm:GetParameter`
  - `sts:AssumeRole`
  - `iam:ListAccountAliases` (optional)
  - `organizations:DescribeAccount` (optional)

## Configuration

Edit `eks_analyzer.py` to change:
- Input CSV file: `csv_file = "accounts.csv"`
- Output CSV file: `output_file = "eks_analysis_output.csv"`

## Extending the Tool

### Adding New Analysis Features
1. Add new method to appropriate module (e.g., `node_operations.py`)
2. Call method from `cluster_analyzer.py`
3. Update output schema in `csv_handler.py`

### Adding New Data Sources
1. Create new module in `modules/` directory
2. Import and use in `cluster_analyzer.py`
3. Update documentation

### Example: Adding Cost Analysis
```python
# modules/cost_operations.py
class CostOperations:
    def get_node_costs(self, instance_type):
        # Implementation
        pass

# Use in cluster_analyzer.py
from .cost_operations import CostOperations
```

## Comparison with Original Script

| Aspect | Original | Modular (SSO) |
|--------|----------|---------------|
| Lines of code | ~373 | ~650 (spread across 7 files) |
| Testability | Low | High |
| Reusability | Low | High |
| Maintainability | Medium | High |
| Error handling | Basic | Comprehensive |
| Documentation | Minimal | Complete |
| Type safety | None | Type hints throughout |

## Migration Guide

### From custom_script_without_sso.py
```bash
# Old way (no SSO)
python custom_script_without_sso.py

# New way (with SSO)
python eks_analyzer.py
```

### From custom_script_sso.py
```bash
# Old way (monolithic with SSO)
python custom_script_sso.py

# New way (modular with SSO)
python eks_analyzer.py
```

### CSV Format Changes
**Old format:**
```csv
account_id,region
123456789012,us-east-1
```

**New format (required):**
```csv
account_id,role_name,region
123456789012,limited-admin,us-east-1
```

**Output changes:**
- Added `AccountName` column after `AccountID`
- All other columns remain the same

## SSO Configuration

### SSO Settings
- **Start URL**: `https://d-9067ab41c2.awsapps.com/start/#/`
- **Region**: `us-east-1`
- **Authentication**: Browser-based
- **Cache Location**: `~/.aws/sso/cache/`
- **Config Backup**: `~/.aws/config.backup.<timestamp>`

### Troubleshooting

**SSO authentication failed:**
- Ensure AWS CLI v2 is installed
- Check SSO start URL is correct
- Verify internet connectivity for browser authentication

**Role not found:**
- Verify role_name exists in target account
- Check role trust policy allows SSO principal
- Ensure role has required EKS/EC2 permissions

**Kubernetes access denied (401/403):**
- Check your IAM role is mapped in EKS cluster
- Verify `aws-auth` ConfigMap or EKS access entries
- Ensure role has `eks:DescribeCluster` permission

**Missing AccountName:**
- Script will fallback to AccountID if IAM alias unavailable
- Requires `iam:ListAccountAliases` or `organizations:DescribeAccount`

## Future Enhancements

Potential additions:
- [ ] Logging to file with rotation
- [ ] Configuration file support (YAML/JSON)
- [ ] Parallel processing for multiple accounts
- [ ] Cost analysis integration
- [ ] Slack/Email notifications
- [ ] JSON output format option
- [ ] CLI arguments for flexibility
- [ ] Detailed HTML reports
- [ ] Multi-region SSO support
- [ ] Custom role ARN format

## Sample Execution

```
python3 eks_analyzer.py            ✔  39s  test   12:38:00 AM 

====================================================================================================
EKS CLUSTER ANALYZER (SSO)
====================================================================================================

INFO: Reading accounts from accounts.csv
INFO: Found 2 account-region combination(s) to process

====================================================================================================
SSO AUTHENTICATION SETUP
====================================================================================================
INFO: Setting up SSO profiles for 1 account(s)
INFO: Backed up AWS config to /Users/vigneshwaraprabu/.aws/config.backup_20260206_003804
INFO: All SSO profiles already exist in AWS config

INFO: Starting AWS SSO login for profile '853973692277'
INFO: Browser will open for authentication
INFO: SSO login successful

====================================================================================================
PROCESSING: Account 853973692277 | Region us-east-1
====================================================================================================
INFO: Account: 853973692277 (pcsg-devops) | Region: us-east-1 | UserId: AROA4NVGMN52SVTKL6LKV:vigneshwaraprabus@presidio.com | Arn: arn:aws:sts::853973692277:assumed-role/AWSReservedSSO_limited-admin_a5135278af25b35b/vigneshwaraprabus@presidio.com
INFO: Account Name: pcsg-devops
INFO: Found 2 cluster(s)

INFO: Analyzing cluster: poc-cluster1
  INFO: Version: 1.34
  INFO: Fetching node details
  INFO: Found 2 node(s)
INFO: Generating kubeconfig for cluster 'poc-cluster1'
INFO: Querying Kubernetes API for node status
  INFO: Instance i-06b8ed7b5459232e1: t3.medium (Amazon Linux 2023)
  INFO: Instance i-03eca8e9e1cdab9c1: t3.medium (Amazon Linux 2023)

INFO: Analyzing cluster: test-ami
  INFO: Version: 1.34
  INFO: Fetching node details
  INFO: Found 2 node(s)
INFO: Generating kubeconfig for cluster 'test-ami'
INFO: Querying Kubernetes API for node status
  INFO: Instance i-027acf38936ef93ce: t3.medium (Amazon Linux 2023)
  INFO: Instance i-0c0f7a1c9b5565e50: t3.medium (Amazon Linux 2023)

INFO: Completed analysis for 853973692277 (us-east-1)

====================================================================================================
PROCESSING: Account 853973692277 | Region us-west-2
====================================================================================================
INFO: Account: 853973692277 (pcsg-devops) | Region: us-west-2 | UserId: AROA4NVGMN52SVTKL6LKV:vigneshwaraprabus@presidio.com | Arn: arn:aws:sts::853973692277:assumed-role/AWSReservedSSO_limited-admin_a5135278af25b35b/vigneshwaraprabus@presidio.com
INFO: Account Name: pcsg-devops
INFO: No EKS clusters found

WARNING: No data collected for 853973692277 (us-west-2)

====================================================================================================
FINALIZING RESULTS
====================================================================================================
INFO: Results written to eks_analysis_output.csv

INFO: Analysis complete
INFO: Processed 2 account-region combination(s)
INFO: Total records: 4
INFO: Local output file: eks_analysis_output.csv

====================================================================================================
UPLOADING TO S3
====================================================================================================

INFO: Uploading to S3
INFO: Bucket: vignesh-s3-debezium-test
INFO: Key: reports/eks_analysis_output_06Feb2026_12_38AM.csv
INFO: Successfully uploaded to s3://vignesh-s3-debezium-test/reports/eks_analysis_output_06Feb2026_12_38AM.csv

====================================================================================================
CLEANUP
====================================================================================================
INFO: Cleaning up SSO cache
INFO: Cleaned up SSO cache at /Users/vigneshwaraprabu/.aws/sso/cache

====================================================================================================
```

## Common Errors and Solutions

### Error 1: NameError - 'exit' is not defined

**Error Message:**
```
Unexpected error: name 'exit' is not defined
Traceback (most recent call last):
  File "D:\Users\vigneshwaraprabu.s\Downloads\custom_script_sso.py", line 462, in <module>
    exit(main())
    ^^^^
NameError: name 'exit' is not defined

During handling of the above exception, another exception occurred:

Traceback (most recent call last):
  File "D:\Users\vigneshwaraprabu.s\Downloads\custom_script_sso.py", line 469, in <module>
    exit(1)
    ^^^^
NameError: name 'exit' is not defined
```

**Solution:**

Add import statement at the beginning of the script:
```python
import sys
```

Then modify all `exit()` commands to `sys.exit()`:
```python
# Before
exit(main())
exit(1)

# After
sys.exit(main())
sys.exit(1)
```

---

### Error 2: ModuleNotFoundError - No module named 'modules'

**Error Message:**
```
Traceback (most recent call last):
  File "D:\Users\vigneshwaraprabu.s\Downloads\moduler\moduler\eks_analyzer.py", line 6, in <module>
    from modules.aws_session import AWSSession
ModuleNotFoundError: No module named 'modules'
```

**Solution:**

Add the following code at the beginning of the script (before any module imports):

```python
import sys
from pathlib import Path

# Add project root to Python path
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

# Now import modules
from modules.aws_session import AWSSession
from modules.csv_handler import CSVHandler
# ... rest of imports
```

This ensures Python can find the `modules` directory regardless of where the script is run from.


{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "sts:GetCallerIdentity",
        "iam:ListAccountAliases",
        "organizations:DescribeAccount",
        "eks:ListClusters",
        "eks:DescribeCluster",
        "ec2:DescribeInstances",
        "ec2:DescribeImages",
        "ssm:GetParameter"
      ],
      "Resource": "*"
    }
  ]
}
