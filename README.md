# QuickSight Setup Guide

## Introduction
This guide provides steps to set up AWS QuickSight with an EKS cluster and AWS Glue.

## Prerequisites
- AWS account
- AWS CLI installed
- Python 3 installed
- Boto3 and Kubernetes libraries
```bash
pip install boto3 kubernetes
```

## Troubleshooting
If you encounter issues, refer to the following errors and solutions:

### Error: Unhandled Error
```
E0202 16:14:14.839654   13459 memcache.go:265] "Unhandled Error" err="couldn't get current server API group list: the server has asked for the client to provide credentials"
```
**Solution:** Ensure the EKS Cluster has the appropriate AWS Role attached for access.

### Error: Forbidden
```
Error from server (Forbidden): nodes is forbidden: User "system:node:ip-10-0-12-76.ec2.internal" cannot list resource "nodes" in API group "" at the cluster scope.
```
**Solution:** Ensure the Cluster has both ClusterRole and ClusterRoleBinding configured.

## Steps to Grant EKS Access to IAM Role
1. **IAM Role Setup:**
   - Trust Relationship: EC2
   - Policy: EKS Read
   ```json
   {
       "Version": "2012-10-17",
       "Statement": [
           {
               "Sid": "EKSReadAccess",
               "Effect": "Allow",
               "Action": [
                   "eks:ListClusters",
                   "eks:DescribeCluster"
               ],
               "Resource": "*"
           },
           {
               "Sid": "EC2NodeInspection",
               "Effect": "Allow",
               "Action": [
                   "ec2:DescribeInstances",
                   "ec2:DescribeImages",
                   "ec2:DescribeTags"
               ],
               "Resource": "*"
           },
           {
               "Sid": "STSCallerIdentity",
               "Effect": "Allow",
               "Action": "sts:GetCallerIdentity",
               "Resource": "*"
           }
       ]
   }
   ```

2. **Access Entry Creation:**
   ```bash
   aws eks create-access-entry \
     --cluster-name poc-cluster1 \
     --principal-arn arn:aws:iam::853973692277:role/EC2RoleforMSK \
     --type STANDARD

   aws eks list-access-entries --cluster-name poc-cluster1
   ```

3. **Grant Access Entry to "AmazonEKSClusterAdminPolicy"**
   ```bash
   # k apply -f clusterrolebinding.yaml
   ```

4. **Verify Identity**
   ```bash
   aws sts get-caller-identity
   ```

## Steps to Create an AWS Glue Crawler
1. Open the AWS Glue Console.
2. In the navigation pane, choose Crawlers.
3. Choose Create crawler and enter a name (e.g., output-csv-crawler).
4. For Data source configuration, choose S3 and specify the path: `s3://vignesh-s3-debezium-test/reports/`.
5. Select Crawl all sub-folders if needed.
6. For IAM role, create or select a role with permissions to access S3 and Glue.
7. For Output configuration, choose or create a database in the Glue Data Catalog.
8. Run the crawler to create a table in the Glue Data Catalog.

## Verification
After the crawler runs, verify the table in the Glue Console. Ensure the schema reflects the CSV columns.

## Visualize in Amazon QuickSight
1. Open the Amazon QuickSight Console.
2. Choose Datasets and then New dataset.
3. Select AWS Glue as the data source and choose the created database and table.
4. Create an analysis and build visualizations.
5. Publish the analysis as a dashboard.

For detailed permissions, ensure your IAM role for QuickSight has access to Glue and S3.




Pipeline retry loop exhausted, Original exception details: java.sql.SQLException: Query execution 7c4d0921-039b-4614-85a8-1c0fe5547ef6 failed or was cancelled. State: FAILED, Reason: PERMISSION_DENIED: User: arn:aws:sts::853973692277:assumed-role/aws-quicksight-service-role-v0/QuickSight-RoleSession-1770060821999 is not authorized to perform: s3:ListBucket on resource: "arn:aws:s3:::vignesh-s3-debezium-test" because no identity-based policy allows the s3:ListBucket action (Service: S3, Status Code: 403, Request ID: 6DMA39KR4MV8YCZD, Extended Request ID: OJLD7AwcJJf/qE+ddVqBgMo5Fgi6pbLgBddAgM6KCHk+hLiO71Me576H61ffOUcT/RMt2eGSgVvJq/xFR/VC0A==)

Solution:
Attach the required permission to the QuickSight Service Role. 

References:
https://repost.aws/knowledge-center/quicksight-permission-errors


