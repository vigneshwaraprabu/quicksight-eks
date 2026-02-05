# EKS Cluster Analyzer - Modular Version (SSO Enabled)

## Overview
Refactored, modular version of the EKS cluster analysis tool with AWS SSO authentication support, improved organization, optimization, and maintainability. Analyzes EKS clusters across multiple AWS accounts using single sign-on authentication.

## Project Structure

```
quicksight/modular/
├── eks_analyzer.py              # Main entry point with SSO workflow
├── accounts.csv                 # Input: Account, role, and region list
├── eks_analysis_output.csv      # Output: Analysis results
└── modules/
    ├── __init__.py             # Module initialization
    ├── sso_auth.py             # SSO authentication management
    ├── aws_session.py          # AWS session and identity management
    ├── eks_operations.py       # EKS cluster operations
    ├── node_operations.py      # EC2 node and AMI operations
    ├── kubernetes_operations.py # Kubernetes API interactions
    ├── csv_handler.py          # CSV reading and writing
    └── cluster_analyzer.py     # Main analysis orchestration
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

## Key Improvements

### 🔐 SSO Authentication
- **Single Sign-On**: Browser-based AWS SSO authentication
- **Multi-account support**: Authenticate once, access all accounts
- **Profile-based sessions**: Automatic role assumption per account
- **Secure**: Uses temporary credentials with automatic refresh
- **Role flexibility**: Role name fetched from CSV (not hardcoded)

### 🎯 Modularity
- **Separated concerns**: Each module has a single, well-defined responsibility
- **Easy to test**: Individual modules can be tested independently
- **Reusable**: Modules can be used in other scripts
- **Maintainable**: Changes are localized to specific modules

### ⚡ Optimizations
- **Reduced code duplication**: Common patterns extracted into methods
- **Better error handling**: Specific exceptions handled appropriately
- **Resource cleanup**: Proper cleanup with try-finally blocks
- **Efficient data flow**: No unnecessary data transformations

### 🛡️ Removed Unnecessary Code
- ❌ Removed `get_current_identity()` - incorporated into AWSSession
- ❌ Removed redundant print statements
- ❌ Removed hardcoded role_name - now fetched from CSV
- ❌ Removed emoji symbols - replaced with INFO/ERROR/WARNING/CRITICAL
- ❌ Removed all docstrings and comments for cleaner code
- ❌ Cleaned up unused imports
- ❌ Removed duplicate logic for uptime/age calculations

### 🔧 Better Structure
- **Type hints**: Added throughout for better IDE support
- **Docstrings**: Clear documentation for all classes and methods
- **Class-based design**: Better encapsulation and state management
- **Consistent naming**: Clear, descriptive names throughout

### ⏱️ Timeout Handling
- **Subprocess timeouts**: 30s for kubeconfig generation
- **API timeouts**: 10s for Kubernetes API calls
- **Connection timeouts**: Proper timeout configuration

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
