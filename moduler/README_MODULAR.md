# EKS Cluster Analyzer - Modular Version

## Overview
Refactored, modular version of the EKS cluster analysis tool with improved organization, optimization, and maintainability.

## Project Structure

```
quicksight/
├── eks_analyzer.py              # Main entry point
├── accounts.csv                 # Input: Account and region list
├── eks_analysis_output.csv      # Output: Analysis results
└── modules/
    ├── __init__.py             # Module initialization
    ├── aws_session.py          # AWS session and identity management
    ├── eks_operations.py       # EKS cluster operations
    ├── node_operations.py      # EC2 node and AMI operations
    ├── kubernetes_operations.py # Kubernetes API interactions
    ├── csv_handler.py          # CSV reading and writing
    └── cluster_analyzer.py     # Main analysis orchestration
```

## Modules Description

### 1. `aws_session.py`
- Manages AWS session creation
- Handles caller identity verification
- Single responsibility: Authentication

### 2. `eks_operations.py`
- Lists EKS clusters
- Gets cluster versions
- Fetches latest EKS optimized AMIs from SSM
- All EKS-specific API calls

### 3. `node_operations.py`
- Retrieves EC2 instances for clusters
- Calculates AMI age and node uptime
- Parses OS versions from AMI descriptions
- Determines patch pending status
- All EC2-specific operations

### 4. `kubernetes_operations.py`
- Generates kubeconfig for EKS clusters
- Queries Kubernetes API for node readiness
- Handles K8s authentication and timeouts
- Proper cleanup of temporary files

### 5. `csv_handler.py`
- Reads account configuration from CSV
- Writes analysis results to CSV
- Single responsibility: Data I/O

### 6. `cluster_analyzer.py`
- Orchestrates the analysis workflow
- Coordinates between different modules
- Aggregates data into final results
- Main business logic

### 7. `eks_analyzer.py`
- Main entry point
- Command-line interface
- Error handling and user feedback
- Progress reporting

## Key Improvements

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
- ❌ Removed hardcoded values - now in proper constants
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

### Basic Usage
```bash
python eks_analyzer.py
```

### Input CSV Format
```csv
account_id,region
123456789012,"us-east-1,us-west-2"
987654321098,us-east-1
```

### Output CSV Columns
- AccountID
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

```bash
pip install boto3 kubernetes
```

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

| Aspect | Original | Modular |
|--------|----------|---------|
| Lines of code | ~373 | ~650 (spread across 7 files) |
| Testability | Low | High |
| Reusability | Low | High |
| Maintainability | Medium | High |
| Error handling | Basic | Comprehensive |
| Documentation | Minimal | Complete |
| Type safety | None | Type hints throughout |

## Migration Guide

Replace usage of `custom_script_without_sso.py`:
```bash
# Old way
python custom_script_without_sso.py

# New way
python eks_analyzer.py
```

No changes needed to CSV format or output - fully compatible!

## Future Enhancements

Potential additions:
- [ ] Logging to file
- [ ] Configuration file support
- [ ] Parallel processing for multiple accounts
- [ ] Cost analysis integration
- [ ] Slack/Email notifications
- [ ] JSON output format option
- [ ] CLI arguments for flexibility
- [ ] Detailed HTML reports
