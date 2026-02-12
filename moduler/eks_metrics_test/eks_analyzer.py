#!/usr/bin/env python3

import os
import sys
import argparse
from typing import List
from modules.aws_session import AWSSession
from modules.cluster_analyzer import ClusterAnalyzer
from modules.csv_handler import CSVHandler
from modules.logger import Logger


def parse_arguments():
    parser = argparse.ArgumentParser(description='EKS Cluster Analyzer - Uses current AWS credentials')
    parser.add_argument('--regions', 
                       type=str,
                       help='Comma-separated list of AWS regions (e.g., us-east-1,us-west-2). If not provided, will read from regions.txt')
    parser.add_argument('--regions-file', 
                       default='regions.txt',
                       help='File containing regions, one per line (default: regions.txt)')
    return parser.parse_args()


def get_regions(args) -> List[str]:
    """Get regions from command line or file"""
    if args.regions:
        regions = [r.strip() for r in args.regions.split(',') if r.strip()]
        Logger.info(f"Using regions from command line: {', '.join(regions)}")
        return regions
    
    if os.path.exists(args.regions_file):
        Logger.info(f"Reading regions from {args.regions_file}")
        with open(args.regions_file, 'r') as f:
            regions = [line.strip() for line in f if line.strip() and not line.strip().startswith('#')]
        if regions:
            Logger.success(f"Found {len(regions)} region(s): {', '.join(regions)}")
            return regions
    
    Logger.error(f"No regions specified. Use --regions or create {args.regions_file}")
    Logger.error("Example: --regions us-east-1,us-west-2", indent=1)
    Logger.error(f"Or create {args.regions_file} with one region per line", indent=1)
    return []


def main():
    args = parse_arguments()
    output_file = "eks_analysis_output.csv"
    
    Logger.header("EKS CLUSTER ANALYZER")
    
    # Get regions
    regions = get_regions(args)
    if not regions:
        return 1
    
    # Verify AWS credentials
    Logger.section("VERIFYING AWS CREDENTIALS")
    try:
        test_session = AWSSession(regions[0])
        identity = test_session.get_caller_identity()
        account_id = identity['Account']
        account_name = test_session.get_account_name()
        
        Logger.success("AWS credentials verified")
        Logger.info(f"Account: {account_id} ({account_name})")
        Logger.info(f"User/Role: {identity.get('Arn', 'N/A')}", indent=1)
    except Exception as e:
        Logger.error(f"Failed to verify AWS credentials: {e}")
        Logger.error("Ensure you have valid AWS credentials configured", indent=1)
        Logger.error("Try: aws sts get-caller-identity", indent=1)
        return 1
    
    all_results = []
    csv_handler = CSVHandler()
    
    for region in regions:
        Logger.section(f"PROCESSING REGION: {region}")
        
        try:
            aws_session = AWSSession(region)
            
            analyzer = ClusterAnalyzer(aws_session.session, region)
            results = analyzer.analyze_clusters(account_id, account_name)
            
            if results:
                all_results.extend(results)
                Logger.success(f"Completed analysis for {region}")
            else:
                Logger.warning(f"No clusters found in {region}")
                
        except Exception as e:
            error_msg = str(e)
            Logger.error(f"Failed to process region {region}: {error_msg}")
            if "NoCredentialProviders" in error_msg:
                Logger.error("AWS credentials not found or expired", indent=1)
            elif "InvalidClientTokenId" in error_msg:
                Logger.error("Invalid AWS credentials", indent=1)
            elif "AccessDenied" in error_msg:
                Logger.error(f"Insufficient permissions in {region}", indent=1)
            continue
    
    Logger.section("FINALIZING RESULTS")
    csv_handler.write_cluster_data(output_file, all_results)
    
    Logger.blank()
    Logger.success("Analysis complete")
    Logger.info(f"Processed {len(regions)} region(s)")
    Logger.info(f"Total records: {len(all_results)}")
    Logger.info(f"Output file: {output_file}")
    
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
