#!/usr/bin/env python3

import os
import sys
import argparse
import boto3
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
from modules.aws_session import AWSSession
from modules.csv_handler import CSVHandler
from modules.cluster_analyzer import ClusterAnalyzer
from modules.sso_auth import SSOAuthenticator
from modules.s3_handler import S3Handler
from modules.logger import Logger


# Fixed regions to scan
REGIONS_TO_SCAN = ['us-east-1', 'us-east-2', 'us-west-2', 'ap-south-1', 'eu-central-1']
# IAM role to use for all accounts
IAM_ROLE = 'PatchingAccess'
# Number of parallel workers
MAX_WORKERS = 15


def parse_arguments():
    parser = argparse.ArgumentParser(
        description='EKS Cluster Analyzer with Auto Account Discovery',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
This script automatically discovers and analyzes all AWS accounts you have access to.

Features:
  • Auto-discovers all accounts via AWS Organizations
  • Uses PatchingAccess role for all accounts
  • Scans regions: us-east-1, us-east-2, us-west-2, ap-south-1
  • Parallel execution for faster processing
  • Generates comprehensive CSV report
  
Example:
  python3 eks_analyzer.py
  python3 eks_analyzer.py --skip-s3
  python3 eks_analyzer.py --workers 20
        '''
    )
    parser.add_argument('--s3-bucket', 
                       default='mmtag-reports',
                       help='S3 bucket name for output upload (default: mmtag-reports)')
    parser.add_argument('--s3-prefix', 
                       default='eks-reports',
                       help='S3 prefix/folder for output upload (default: eks-reports)')
    parser.add_argument('--s3-account', 
                       default='908676838269',
                       help='AWS account ID where S3 bucket is located (default: 908676838269)')
    parser.add_argument('--skip-s3', 
                       action='store_true',
                       help='Skip S3 upload and only save locally')
    parser.add_argument('--workers',
                       type=int,
                       default=MAX_WORKERS,
                       help=f'Number of parallel workers (default: {MAX_WORKERS})')
    return parser.parse_args()


def process_account_region(account_id, region, scan_num, total_scans, print_lock):
    """Process a single account-region combination"""
    try:
        with print_lock:
            Logger.section(f"[{scan_num}/{total_scans}] Account {account_id} | Region {region}")
            Logger.info(f"Starting analysis...")
        
        aws_session = AWSSession(region, profile_name=account_id)
        
        with print_lock:
            aws_session.print_identity(account_id)
            account_name = aws_session.get_account_name()
            Logger.info(f"Account Name: {account_name}")
        
        analyzer = ClusterAnalyzer(aws_session.session, region)
        
        with print_lock:
            Logger.info(f"Listing EKS clusters...")
        
        results = analyzer.analyze_clusters(account_id, account_name)
        
        with print_lock:
            if results:
                Logger.success(f"✓ Collected {len(results)} record(s) from {account_id} ({region})")
            else:
                Logger.info(f"✓ No EKS clusters in {account_id} ({region})")
        
        return {'success': True, 'results': results, 'account_id': account_id, 'region': region}
        
    except Exception as e:
        error_msg = str(e)
        with print_lock:
            Logger.error(f"✗ Failed: {account_id} in {region}")
            Logger.error(f"Error: {error_msg[:150]}", indent=1)
            
            if "NoCredentialProviders" in error_msg or "InvalidClientTokenId" in error_msg:
                Logger.error("SSO credentials expired", indent=1)
            elif "AccessDenied" in error_msg:
                Logger.error(f"No '{IAM_ROLE}' role access", indent=1)
            elif "Timeout" in error_msg or "timed out" in error_msg.lower():
                Logger.error("Operation timed out", indent=1)
        
        return {'success': False, 'results': [], 'account_id': account_id, 'region': region}


def main():
    args = parse_arguments()
    current_date = datetime.now().strftime("%Y_%m_%d")
    output_file = f"eks_analysis_output_{current_date}.csv"
    
    Logger.header("EKS CLUSTER ANALYZER - AUTO DISCOVERY")
    
    csv_handler = CSVHandler()
    
    # Step 1: SSO Authentication
    Logger.section("SSO AUTHENTICATION")
    Logger.info("Initiating AWS SSO login...")
    Logger.info("Your browser will open for authentication", indent=1)
    
    # Always perform SSO login to ensure fresh credentials
    if not SSOAuthenticator.authenticate(None):
        Logger.error("SSO authentication failed")
        Logger.error("Please ensure:", indent=1)
        Logger.error("1. AWS CLI v2 is installed", indent=2)
        Logger.error("2. You have an SSO profile configured", indent=2)
        Logger.error("3. Run: aws configure sso (if not configured)", indent=2)
        return 1
    
    Logger.success("SSO authentication successful!")
    Logger.blank()
    
    # Step 2: Discover All Accounts
    Logger.section("ACCOUNT DISCOVERY")
    account_ids = SSOAuthenticator.discover_accounts()
    
    if not account_ids:
        Logger.error("No accounts discovered. Exiting.")
        return 1
    
    # Step 3: Setup SSO Profiles for All Accounts
    Logger.section("SSO PROFILE SETUP")
    Logger.info(f"Setting up SSO profiles with '{IAM_ROLE}' role for {len(account_ids)} account(s)")
    
    accounts_data = {account_id: IAM_ROLE for account_id in account_ids}
    
    # Add S3 account if not already present
    if args.s3_account not in accounts_data:
        accounts_data[args.s3_account] = IAM_ROLE
        Logger.info(f"Including S3 account {args.s3_account} for report upload")
    
    SSOAuthenticator.setup_profiles(accounts_data)
    
    # Step 4: Build Scan List
    Logger.section("SCAN CONFIGURATION")
    Logger.info(f"IAM Role: {IAM_ROLE}")
    Logger.info(f"Regions: {', '.join(REGIONS_TO_SCAN)}")
    Logger.info(f"Parallel Workers: {args.workers}")
    
    total_scans = len(account_ids) * len(REGIONS_TO_SCAN)
    Logger.success(f"Total combinations to scan: {total_scans}")
    Logger.blank()
    
    # Step 5: Process All Account-Region Combinations in Parallel
    all_results = []
    successful = 0
    failed = 0
    completed = 0
    print_lock = Lock()
    
    # Build list of tasks
    tasks = []
    scan_count = 0
    for account_id in account_ids:
        for region in REGIONS_TO_SCAN:
            scan_count += 1
            tasks.append((account_id, region, scan_count, total_scans))
    
    Logger.info(f"Starting parallel execution with {args.workers} workers...")
    Logger.blank()
    
    # Execute tasks in parallel
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        # Submit all tasks
        future_to_task = {
            executor.submit(process_account_region, account_id, region, scan_num, total_scans, print_lock): (account_id, region)
            for account_id, region, scan_num, total_scans in tasks
        }
        
        # Process completed tasks as they finish
        for future in as_completed(future_to_task):
            result = future.result()
            completed += 1
            
            if result['success']:
                successful += 1
                all_results.extend(result['results'])
            else:
                failed += 1
            
            # Print progress update every 10 completions
            if completed % 10 == 0:
                with print_lock:
                    Logger.blank()
                    Logger.info(f"Progress: {completed}/{total_scans} completed ({successful} successful, {failed} failed)")
                    Logger.blank()
    
    # Step 6: Write Results
    Logger.section("RESULTS SUMMARY")
    Logger.info(f"Total accounts scanned: {len(account_ids)}")
    Logger.info(f"Total regions per account: {len(REGIONS_TO_SCAN)}")
    Logger.info(f"Successful scans: {successful}/{total_scans}")
    Logger.info(f"Failed scans: {failed}/{total_scans}")
    Logger.info(f"Total EKS records collected: {len(all_results)}")
    
    csv_handler.write_cluster_data(output_file, all_results)
    Logger.success(f"Report saved: {output_file}")
    
    # Step 7: Upload to S3 (Optional)
    if not args.skip_s3 and all_results:
        try:
            Logger.section("S3 UPLOAD")
            Logger.info(f"Uploading to account {args.s3_account}")
            
            s3_session = AWSSession("us-east-1", profile_name=args.s3_account)
            s3_handler = S3Handler(s3_session.session)
            
            success = s3_handler.upload_file(
                local_file=output_file,
                bucket=args.s3_bucket,
                prefix=args.s3_prefix,
                preserve_filename=True
            )
            
            if not success:
                Logger.warning("S3 upload failed, but local file is available")
                
        except Exception as e:
            Logger.error(f"S3 upload error: {e}")
            Logger.warning("Local file saved successfully despite S3 upload failure")
    elif args.skip_s3:
        Logger.info("Skipping S3 upload (--skip-s3 flag set)")
    
    # Step 8: Cleanup
    Logger.section("CLEANUP")
    SSOAuthenticator.cleanup_cache()
    
    Logger.blank()
    Logger.success("✓ Analysis Complete!")
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
        import traceback
        traceback.print_exc()
        sys.exit(1)
