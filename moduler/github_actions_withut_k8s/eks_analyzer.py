#!/usr/bin/env python3

import os
import sys
import argparse
from datetime import datetime
from typing import Dict
from modules.aws_session import AWSSession
from modules.csv_handler import CSVHandler
from modules.cluster_analyzer import ClusterAnalyzer
from modules.role_assumption import RoleAssumption
from modules.s3_handler import S3Handler
from modules.logger import Logger


def parse_arguments():
    parser = argparse.ArgumentParser(description='EKS Cluster Analyzer with Role Assumption (GitHub Actions)')
    parser.add_argument('--s3-bucket', 
                       default='mmtag-reports',
                       help='S3 bucket name for output upload (default: mmtag-reports)')
    parser.add_argument('--s3-prefix', 
                       default='eks-reports',
                       help='S3 prefix/folder for output upload (default: eks-reports)')
    parser.add_argument('--skip-s3', 
                       action='store_true',
                       help='Skip S3 upload and only save locally')
    parser.add_argument('--account-list', 
                       default='accounts.csv',
                       help='CSV file with account list (default: accounts.csv)')
    return parser.parse_args()


def main():
    args = parse_arguments()
    csv_file = args.account_list
    current_date = datetime.now().strftime("%Y_%m_%d")
    output_file = f"eks_analysis_output_{current_date}.csv"
    
    Logger.header("EKS CLUSTER ANALYZER (GITHUB ACTIONS)")
    
    if not os.path.exists(csv_file):
        Logger.error(f"CSV file '{csv_file}' not found in current directory")
        Logger.error(f"Current directory: {os.getcwd()}", indent=1)
        return 1
    
    Logger.info(f"Reading accounts from {csv_file}")
    csv_handler = CSVHandler()
    accounts = csv_handler.read_accounts(csv_file)
    
    if not accounts:
        Logger.error("No valid accounts to process")
        Logger.error("Check CSV format: account_id,role_name,region", indent=1)
        return 1
    
    Logger.success(f"Found {len(accounts)} account-region combination(s) to process")
    
    # Initialize role assumption with base credentials from GitHub Actions
    Logger.section("INITIALIZING ROLE ASSUMPTION")
    role_assumer = RoleAssumption()
    
    # Verify base credentials
    base_identity = role_assumer.get_base_caller_identity()
    if not base_identity:
        Logger.error("Failed to get base caller identity")
        Logger.error("Ensure GitHub Actions has assumed the base role correctly", indent=1)
        return 1
    
    Logger.info(f"Base role identity:")
    Logger.info(f"Account: {base_identity.get('Account', 'N/A')}", indent=1)
    Logger.info(f"Arn: {base_identity.get('Arn', 'N/A')}", indent=1)
    Logger.success("Base role verification successful")
    
    all_results = []
    
    
    for account_info in accounts:
        account_id = account_info["account_id"]
        role_name = account_info["role_name"]
        region = account_info["region"]
        
        Logger.section(f"PROCESSING: Account {account_id} | Region {region}")
        
        try:
            # Assume role in target account
            assumed_session = role_assumer.assume_role(account_id, role_name, region)
            
            if not assumed_session:
                Logger.error(f"Failed to assume role in account {account_id}, skipping")
                continue
            
            # Create AWS session wrapper
            aws_session = AWSSession(assumed_session, region)
            
            aws_session.print_identity(account_id)
            account_name = aws_session.get_account_name()
            Logger.info(f"Account Name: {account_name}")
            
            # Analyze clusters
            analyzer = ClusterAnalyzer(assumed_session, region)
            results = analyzer.analyze_clusters(account_id, account_name)
            
            if results:
                all_results.extend(results)
                Logger.success(f"Collected {len(results)} record(s) from {account_id} ({region})")
            else:
                Logger.warning(f"No data collected for {account_id} ({region})")
                
        except Exception as e:
            error_msg = str(e)
            Logger.error(f"Failed to process {account_id} in {region}: {error_msg}")
            if "AccessDenied" in error_msg:
                Logger.error("Check trust relationship and IAM permissions for role assumption", indent=1)
            elif "InvalidClientTokenId" in error_msg:
                Logger.error("Invalid credentials. Check GitHub Actions OIDC configuration", indent=1)
            continue
    
    Logger.section("FINALIZING RESULTS")
    csv_handler.write_cluster_data(output_file, all_results)
    
    Logger.blank()
    Logger.success("Analysis complete")
    Logger.info(f"Processed {len(accounts)} account-region combination(s)")
    Logger.info(f"Total records: {len(all_results)}")
    Logger.info(f"Local output file: {output_file}")
    
    # Upload to S3 if not skipped
    if not args.skip_s3:
        try:
            Logger.section("UPLOADING TO S3")
            
            # Assume S3 upload role
            s3_assumed_session = role_assumer.assume_s3_upload_role()
            
            if not s3_assumed_session:
                Logger.error("Failed to assume S3 upload role")
                Logger.warning("Local file saved successfully despite S3 upload failure")
            else:
                s3_handler = S3Handler(s3_assumed_session)
                
                # Upload with original filename (not timestamped)
                success = s3_handler.upload_file(
                    local_file=output_file,
                    bucket=args.s3_bucket,
                    prefix=args.s3_prefix,
                    preserve_filename=True
                )
                
                if not success:
                    Logger.warning("Local file saved successfully despite S3 upload failure")
                
        except Exception as e:
            Logger.error(f"S3 upload error: {e}")
            Logger.warning("Local file saved successfully despite S3 upload failure")
    else:
        Logger.info("Skipping S3 upload (--skip-s3 flag set)")
    
    
    Logger.separator()
    Logger.blank()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        Logger.blank()
        Logger.warning("Interrupted by user")
        sys.exit(130)
    except Exception as e:
        Logger.blank()
        Logger.critical(f"Unexpected error: {e}")
        sys.exit(1)
