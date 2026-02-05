import pandas as pd
import constants
from modules import EKSAuditor

def main():
    auditor = EKSAuditor()
    all_results = []
    
    # Read the CSV with Account and Region columns
    df = pd.read_csv(constants.INPUT_CSV_PATH)
    
    for index, row in df.iterrows():
        account = str(row['account_number']) # Keep as string to preserve leading zeros
        region = str(row['region'])
        
        # Perform the audit for this specific row
        results = auditor.perform_audit(region, account)
        all_results.extend(results)
    
    # Final upload to S3
    auditor.upload_to_s3(all_results)

if __name__ == "__main__":
    main()