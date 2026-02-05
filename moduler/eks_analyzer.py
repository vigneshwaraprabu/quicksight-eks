#!/usr/bin/env python3

import sys
from modules.aws_session import AWSSession
from modules.csv_handler import CSVHandler
from modules.cluster_analyzer import ClusterAnalyzer


def print_header():
    print("\n" + "=" * 100)
    print("EKS CLUSTER ANALYZER")
    print("=" * 100 + "\n")


def print_section(title: str):
    print("\n" + "=" * 100)
    print(f"{title}")
    print("=" * 100)


def main():
    csv_file = "accounts.csv"
    output_file = "eks_analysis_output.csv"
    
    print_header()
    
    print(f"INFO: Reading accounts from {csv_file}")
    csv_handler = CSVHandler()
    accounts = csv_handler.read_accounts(csv_file)
    
    if not accounts:
        print("ERROR: No accounts to process")
        return 1
    
    print(f"INFO: Found {len(accounts)} account-region combination(s) to process")
    all_results = []
    
    for account_info in accounts:
        account_id = account_info["account_id"]
        region = account_info["region"]
        
        print_section(f"PROCESSING: Account {account_id} | Region {region}")
        
        try:
            aws_session = AWSSession(region)
            aws_session.print_identity(account_id)
            
            analyzer = ClusterAnalyzer(aws_session.session, region)
            results = analyzer.analyze_clusters(account_id)
            
            if results:
                all_results.extend(results)
                print(f"\nINFO: Completed analysis for {account_id} ({region})")
            else:
                print(f"\nWARNING: No data collected for {account_id} ({region})")
                
        except Exception as e:
            print(f"\nERROR: Failed to process {account_id} in {region}: {e}")
            continue
    
    print_section("FINALIZING RESULTS")
    csv_handler.write_cluster_data(output_file, all_results)
    
    print(f"\nINFO: Analysis complete")
    print(f"INFO: Processed {len(accounts)} account-region combination(s)")
    print(f"INFO: Total records: {len(all_results)}")
    print(f"INFO: Output file: {output_file}")
    print("\n" + "=" * 100 + "\n")
    
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nWARNING: Interrupted by user")
        sys.exit(130)
    except Exception as e:
        print(f"\nCRITICAL: Unexpected error: {e}")
        sys.exit(1)
