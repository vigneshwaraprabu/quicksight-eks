#!/usr/bin/env python3

import os
import sys
import argparse
from typing import Dict
from modules.aws_session import AWSSession
from modules.csv_handler import CSVHandler
from modules.cluster_analyzer import ClusterAnalyzer
from modules.sso_auth import SSOAuthenticator
from modules.s3_handler import S3Handler
from modules.logger import Logger


def parse_arguments():
    parser = argparse.ArgumentParser(description='EKS Cluster Analyzer with SSO Authentication')
    parser.add_argument('--s3-bucket', 
                       default='vignesh-s3-debezium-test',
                       help='S3 bucket name for output upload (default: vignesh-s3-debezium-test)')
    parser.add_argument('--s3-prefix', 
                       default='reports',
                       help='S3 prefix/folder for output upload (default: reports)')
    parser.add_argument('--skip-s3', 
                       action='store_true',
                       help='Skip S3 upload and only save locally')
    return parser.parse_args()


def main():
    args = parse_arguments()
    csv_file = "accounts.csv"
    output_file = "eks_analysis_output.csv"
    
    Logger.header("EKS CLUSTER ANALYZER (SSO)")
    
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
    
    accounts_data = {}
    for account_info in accounts:
        account_id = account_info["account_id"]
        role_name = account_info["role_name"]
        accounts_data[account_id] = role_name
    
    Logger.section("SSO AUTHENTICATION SETUP")
    Logger.info(f"Setting up SSO profiles for {len(accounts_data)} account(s)")
    SSOAuthenticator.setup_profiles(accounts_data)
    
    first_account = list(accounts_data.keys())[0]
    if not SSOAuthenticator.authenticate(first_account):
        Logger.error("SSO authentication failed")
        return 1
    
    all_results = []
    
    for account_info in accounts:
        account_id = account_info["account_id"]
        region = account_info["region"]
        
        Logger.section(f"PROCESSING: Account {account_id} | Region {region}")
        
        try:
            aws_session = AWSSession(region, profile_name=account_id)
            aws_session.print_identity(account_id)
            
            account_name = aws_session.get_account_name()
            Logger.info(f"Account Name: {account_name}")
            
            analyzer = ClusterAnalyzer(aws_session.session, region)
            results = analyzer.analyze_clusters(account_id, account_name)
            
            if results:
                all_results.extend(results)
                Logger.success(f"Completed analysis for {account_id} ({region})")
            else:
                Logger.warning(f"No data collected for {account_id} ({region})")
                
        except Exception as e:
            error_msg = str(e)
            Logger.error(f"Failed to process {account_id} in {region}: {error_msg}")
            if "NoCredentialProviders" in error_msg:
                Logger.error("SSO credentials may have expired. Try re-authenticating", indent=1)
            elif "InvalidClientTokenId" in error_msg:
                Logger.error("Invalid credentials. Check SSO profile configuration", indent=1)
            elif "AccessDenied" in error_msg:
                Logger.error(f"Insufficient permissions for account {account_id}", indent=1)
            continue
    
    Logger.section("FINALIZING RESULTS")
    csv_handler.write_cluster_data(output_file, all_results)
    
    Logger.blank()
    Logger.success("Analysis complete")
    Logger.info(f"Processed {len(accounts)} account-region combination(s)")
    Logger.info(f"Total records: {len(all_results)}")
    Logger.info(f"Local output file: {output_file}")
    
    if not args.skip_s3:
        Logger.section("UPLOADING TO S3")
        first_account = list(accounts_data.keys())[0]
        first_region = accounts[0]["region"]
        s3_session = AWSSession(first_region, profile_name=first_account)
        s3_handler = S3Handler(s3_session.session)
        
        upload_success = s3_handler.upload_file(output_file, args.s3_bucket, args.s3_prefix)
        if not upload_success:
            Logger.warning("S3 upload failed, but local file is available")
    else:
        Logger.info("Skipping S3 upload (--skip-s3 flag set)")
    
    Logger.section("CLEANUP")
    Logger.info("Cleaning up SSO cache")
    SSOAuthenticator.cleanup_cache()
    
    Logger.separator()
    Logger.blank()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        Logger.blank()
        Logger.warning("Interrupted by user")
        SSOAuthenticator.cleanup_cache()
        sys.exit(130)
    except Exception as e:
        Logger.blank()
        Logger.critical(f"Unexpected error: {e}")
        sys.exit(1)
