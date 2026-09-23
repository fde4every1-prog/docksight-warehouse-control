import pandas as pd
import numpy as np

# Load the updated orders.csv template and inventory_snapshot.csv to understand distributions and constraints
orders_df = pd.read_csv('../data/raw/orders.csv')
inventory_df = pd.read_csv('../data/raw/inventory_snapshot.csv')

print("Orders columns:", orders_df.columns.tolist())
print(orders_df.head(2))
print("Orders info:")
for col in orders_df.columns:
    print(f"--- {col} ---")
    if col in ['order_id', 'created_at', 'carrier_cutoff']:
        print("Sample:", orders_df[col].iloc[:3].tolist())
    else:
        print(orders_df[col].value_counts(normalize=True))

# Let's inspect the relationship between created_at, carrier_cutoff, priority, and service_level
orders_df['created_dt'] = pd.to_datetime(orders_df['created_at'])
orders_df['cutoff_dt'] = pd.to_datetime(orders_df['carrier_cutoff'])
orders_df['delta_hours'] = (orders_df['cutoff_dt'] - orders_df['created_dt']).dt.total_seconds() / 3600

print("Delta hours summary:")
print(orders_df.groupby(['service_level', 'priority'])['delta_hours'].describe())
print("\nUnique delta hours:")
print(orders_df['delta_hours'].value_counts())

print("\nDate range of created_at:")
print("Min:", orders_df['created_dt'].min(), "Max:", orders_df['created_dt'].max())

# Let's check cross-tabulations to ensure we reproduce any correlations
print("Cross-tab oms_status vs wms_status:")
print(pd.crosstab(orders_df['oms_status'], orders_df['wms_status'], normalize='index').round(3))

print("\nCross-tab warehouse_id vs customer_region:")
print(pd.crosstab(orders_df['warehouse_id'], orders_df['customer_region'], normalize='index').round(3))

# Check order_id formatting in orders.csv
print("Order ID min/max:", orders_df['order_id'].min(), orders_df['order_id'].max())
print("Total rows:", len(orders_df))

# If generating 7000 orders, should they be ORD-000001 to ORD-007000? Yes!
# Let's write the synthetic generator function
np.random.seed(42)

N = 7000

# 1. order_id: ORD-100001 to ORD-107000
synthetic_order_ids = [f"ORD-{i:06d}" for i in range(100001, 100001 + N)]

# 2. warehouse_id: sample based on orders_df distribution
wh_dist = orders_df['warehouse_id'].value_counts(normalize=True)
synthetic_wh = np.random.choice(wh_dist.index, size=N, p=wh_dist.values)

# 3. sku: pick valid random SKU from inventory_snapshot matching warehouse_id
warehouse_skus = inventory_df.groupby('warehouse_id')['sku'].unique().to_dict()
synthetic_skus = [np.random.choice(warehouse_skus[wh]) for wh in synthetic_wh]

# 4. order_quantity: 1
synthetic_qty = np.ones(N, dtype=int)

# 5. priority: sample based on priority distribution
priority_dist = orders_df['priority'].value_counts(normalize=True)
synthetic_priority = np.random.choice(priority_dist.index, size=N, p=priority_dist.values)

# 6. created_at: uniformly or chronologically distributed between 2026-08-01 and 2026-09-05
start_ts = pd.to_datetime('2026-08-01 06:00:00').timestamp()
end_ts = pd.to_datetime('2026-09-05 18:00:00').timestamp()

# Generate random timestamps and sort them chronologically
random_ts = np.sort(np.random.uniform(start_ts, end_ts, size=N))
synthetic_created_dt = pd.to_datetime(random_ts, unit='s').floor('min')
synthetic_created_at = synthetic_created_dt.strftime('%Y-%m-%dT%H:%M:00')

# 7. carrier_cutoff: delta hours sampled from [4, 6, 8, 12, 24] with observed probabilities
delta_dist = orders_df['delta_hours'].value_counts(normalize=True)
synthetic_deltas = np.random.choice(delta_dist.index, size=N, p=delta_dist.values)
synthetic_cutoff_dt = synthetic_created_dt + pd.to_timedelta(synthetic_deltas, unit='h')
synthetic_carrier_cutoff = synthetic_cutoff_dt.strftime('%Y-%m-%dT%H:%M:00')

# 8. oms_status & wms_status: preserve the joint transition probabilities
oms_dist = orders_df['oms_status'].value_counts(normalize=True)
synthetic_oms = np.random.choice(oms_dist.index, size=N, p=oms_dist.values)

# wms transition conditional on oms
crosstab_wms = pd.crosstab(orders_df['oms_status'], orders_df['wms_status'], normalize='index')
synthetic_wms = []
for oms in synthetic_oms:
    probs = crosstab_wms.loc[oms]
    wms_val = np.random.choice(probs.index, p=probs.values)
    synthetic_wms.append(wms_val)

# 9. customer_region: sampled based on distribution
region_dist = orders_df['customer_region'].value_counts(normalize=True)
synthetic_region = np.random.choice(region_dist.index, size=N, p=region_dist.values)

# 10. service_level: sampled based on distribution
service_dist = orders_df['service_level'].value_counts(normalize=True)
synthetic_service = np.random.choice(service_dist.index, size=N, p=service_dist.values)

# Assemble DataFrame
synthetic_orders_df = pd.DataFrame({
    'order_id': synthetic_order_ids,
    'sku': synthetic_skus,
    'order_quantity': synthetic_qty,
    'warehouse_id': synthetic_wh,
    'priority': synthetic_priority,
    'created_at': synthetic_created_at,
    'carrier_cutoff': synthetic_carrier_cutoff,
    'oms_status': synthetic_oms,
    'wms_status': synthetic_wms,
    'customer_region': synthetic_region,
    'service_level': synthetic_service
})

print("Synthetic orders shape:", synthetic_orders_df.shape)
print(synthetic_orders_df.head())
print("\nValidation - null counts:")
print(synthetic_orders_df.isna().sum())

# Validate warehouse_id and sku pairs against inventory
inv_pairs = set(zip(inventory_df['warehouse_id'], inventory_df['sku']))
synth_pairs = list(zip(synthetic_orders_df['warehouse_id'], synthetic_orders_df['sku']))
print("All synth warehouse-sku pairs valid in inventory?:", all(p in inv_pairs for p in synth_pairs))

# Save to CSV
synthetic_orders_df.to_csv('synthetic_orders_7000.csv', index=False)
print("File written to synthetic_orders_7000.csv successfully.")