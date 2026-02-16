# QuickSight Duplicate Data Prevention Guide

## Problem Summary
When refreshing QuickSight datasets, duplicate entries appear because:
- Time-based values (`AMI_Age`, `NodeUptime`) change on each script execution
- QuickSight appends new data instead of replacing old data
- Grouping by `ClusterName` doesn't work because other columns differ

## Solution Implemented

### Code Changes Made
1. **Added `DataExtractedAt` column**: Timestamp of when data was extracted
2. **Added `RecordID` column**: Unique hash based on stable identifiers
   - Based on: `AccountID + Region + ClusterName + InstanceID`
   - Does NOT include time-based values like uptime or AMI age
   - Same logical record always gets the same RecordID

## QuickSight Configuration Options

### **Option 1: Full Refresh (Recommended - Simplest)**

This completely replaces old data with new data on each refresh.

**Steps:**
1. Go to QuickSight Console → Datasets
2. Select your dataset → Click "Edit dataset"
3. In dataset settings, ensure:
   - **Import mode**: SPICE
   - **Query mode**: Direct query (if using S3)
4. For refresh schedules:
   - Go to "Refresh" tab
   - Create/Edit refresh schedule
   - Set **Incremental refresh**: OFF (disabled)
   
**Pros:**
- No duplicates - old data is completely replaced
- Simple to configure
- Works for all data sources

**Cons:**
- Re-imports all data each time (slower for large datasets)

---

### **Option 2: Incremental Refresh with RecordID**

Use the `RecordID` column to identify and update existing records.

**Steps:**
1. Go to QuickSight Console → Datasets
2. Select your dataset → Click "Edit dataset"
3. Enable incremental refresh:
   - Click "Refresh" tab
   - Create a refresh schedule
   - Enable **"Incremental refresh"**
   - Set **Lookup columns**: Select `RecordID`
4. QuickSight will:
   - Update records with matching RecordID
   - Add new records not previously seen

**Pros:**
- Faster refreshes (only processes changes)
- Efficient for large datasets

**Cons:**
- Requires RecordID column (✅ now implemented)
- Slightly more complex setup

---

### **Option 3: Use DataExtractedAt for Time-Series Analysis**

Keep historical data and filter by latest extraction time in analyses.

**Steps:**
1. Keep all data (duplicates become historical records)
2. In your QuickSight analyses:
   - Add a filter: `DataExtractedAt = max(DataExtractedAt)`
   - Or create a calculated field:
     ```
     ifelse(DataExtractedAt = max(DataExtractedAt), 1, 0)
     ```
   - Filter to show only latest data

**Pros:**
- Maintains historical trends
- Can analyze how metrics change over time
- No data loss

**Cons:**
- Dataset grows over time
- Need to filter in each analysis

---

## S3 Configuration (If using S3 as source)

### Option A: Overwrite S3 File (Recommended)
Your script already overwrites the local file. Ensure S3 upload also overwrites:

```python
# In s3_handler.py, the upload should use the same key
# This will overwrite the previous file
s3_client.upload_file(
    local_file,
    bucket_name,
    f"{prefix}/{filename}"  # Same path = overwrite
)
```

### Option B: Versioned S3 Files with Manifest
If you want to keep history in S3:

1. Upload with timestamp: `eks_analysis_YYYY-MM-DD.csv`
2. Create a manifest file pointing to the latest file
3. Point QuickSight to the manifest

---

## Recommended Approach

### For Most Use Cases: **Full Refresh**
1. ✅ Code changes already implemented (timestamp + RecordID added)
2. Configure QuickSight for full refresh (Option 1 above)
3. Script overwrites local and S3 files
4. QuickSight replaces all data on refresh

### For Large Datasets: **Incremental Refresh**
1. ✅ Code changes already implemented
2. Use RecordID as lookup column (Option 2 above)
3. QuickSight updates existing records, adds new ones

### For Historical Tracking: **Time-Series with Filter**
1. ✅ Code changes already implemented
2. Append data instead of replacing (modify script)
3. Use DataExtractedAt filter in analyses (Option 3 above)

---

## Testing the Fix

1. **Run your script twice:**
   ```bash
   python eks_analyzer.py
   # Wait a few minutes
   python eks_analyzer.py
   ```

2. **Check the CSV:**
   - Same clusters should have identical RecordID
   - DataExtractedAt will be different
   - AMI_Age and NodeUptime will be different (expected)

3. **Refresh QuickSight dataset**
   - With full refresh: Old data disappears, new data appears
   - With incremental: Records with same RecordID get updated

---

## Additional QuickSight Tips

### Create a "Latest Data Only" Dataset
1. Create a dataset filter in QuickSight:
   - `DataExtractedAt = max(DataExtractedAt)`
2. Save as a new dataset named "EKS Analysis (Latest)"
3. Use this dataset for operational dashboards

### Create a "Historical Trends" Dataset
1. Keep all data (no filters)
2. Use for trend analysis over time
3. Group by `DataExtractedAt` to see changes

### Cleanup Old Data
If using append mode, periodically clean old data:
```sql
-- In Athena/S3 Select (if applicable)
SELECT * FROM eks_analysis 
WHERE DataExtractedAt >= current_date - interval '30' day
```

---

## Troubleshooting

### Still seeing duplicates?
1. Check QuickSight refresh mode (Full vs Incremental)
2. Verify RecordID is being generated (check CSV file)
3. Clear SPICE cache: Dataset → Actions → Clear SPICE cache
4. Re-import dataset from scratch

### RecordID not working?
- Ensure InstanceID is included in RecordID (handled for N/A cases)
- Check that RecordID column exists in dataset schema
- Refresh dataset schema: Edit dataset → Refresh fields

### Want to start fresh?
1. Delete existing QuickSight dataset
2. Run script to generate new CSV with timestamp + RecordID
3. Re-create dataset in QuickSight
4. Configure refresh mode

---

## Summary

**Problem**: QuickSight showed duplicates because time-based values changed each run.

**Solution**: 
- ✅ Added `RecordID` based on stable identifiers (Account, Region, Cluster, Instance)
- ✅ Added `DataExtractedAt` timestamp for tracking
- ⚙️ Configure QuickSight for full refresh (simplest) or incremental refresh with RecordID

**Next Step**: Configure your QuickSight dataset using one of the options above!
