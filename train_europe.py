#!/usr/bin/env python3
"""
Train European wheat yield model on 15 countries × 59 NUTS2 regions.
Random Forest with Leave-One-Year-Out CV + Country one-hot encoding.
"""
import json, sys, math
import joblib
import numpy as np
from collections import defaultdict
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, r2_score

DATA_PATH = '/home/j/crop-mcp/europe_training_data.json'
MODEL_PATH = '/home/j/crop-mcp/europe_yield_model.pkl'

# Load data
with open(DATA_PATH) as f:
    all_data = json.load(f)

print("=" * 60)
print("🌾 EUROPEAN YIELD MODEL")
print("=" * 60)
print(f"Samples: {len(all_data)}")
print(f"Countries: {sorted(set(d['country'] for d in all_data))}")
print(f"Years range: {min(d['year'] for d in all_data)}–{max(d['year'] for d in all_data)}")

# Get all countries for one-hot encoding
countries = sorted(set(d['country'] for d in all_data))
country_idx = {c: i for i, c in enumerate(countries)}

# Feature keys (no country yet)
NUM_FEATURES = ["gdd", "precip_mm", "solar_kwh", "soil_moisture", "solar_anom_pct", "soil_anom_pct",
                # V4.1 Soil features (static per region)
                "soc_g_kg", "ph", "clay_pct", "sand_pct", "silt_pct",
                "nitrogen_g_kg", "cec_cmol_kg"]

def prep_data(data_subset):
    """Extract feature vectors: numeric + country one-hot."""
    X = []
    y = []
    for d in data_subset:
        row = [d[k] for k in NUM_FEATURES]
        # One-hot country
        one_hot = [0] * len(countries)
        one_hot[country_idx[d['country']]] = 1
        row.extend(one_hot)
        X.append(row)
        y.append(d["yield_t_ha"])
    return np.array(X), np.array(y)

# ── 1. Cross-validation: Leave-One-Year-Out ──
print("\n" + "=" * 60)
print("📊 LEAVE-ONE-YEAR-OUT CROSS-VALIDATION")
print("=" * 60)

years = sorted(set(d["year"] for d in all_data))
n_country = len(countries)

models = [
    ("Ridge Regression", Ridge(alpha=5.0)),
    ("Random Forest (50 trees)", RandomForestRegressor(n_estimators=50, max_depth=6, random_state=42)),
    ("Random Forest (200 trees)", RandomForestRegressor(n_estimators=200, max_depth=8, random_state=42)),
]

best_model = None
best_mae = float('inf')

for name, clf in models:
    y_true_all = []
    y_pred_all = []
    
    for test_year in years:
        train_data = [d for d in all_data if d["year"] != test_year]
        test_data = [d for d in all_data if d["year"] == test_year]
        
        X_train, y_train = prep_data(train_data)
        X_test, y_test = prep_data(test_data)
        
        clf.fit(X_train, y_train)
        preds = clf.predict(X_test)
        
        y_true_all.extend(y_test)
        y_pred_all.extend(preds)
    
    mae = mean_absolute_error(y_true_all, y_pred_all)
    r2 = r2_score(y_true_all, y_pred_all)
    mean_y = np.mean(y_true_all)
    rel_err = mae / mean_y * 100
    
    print(f"\n{name}:")
    print(f"  MAE: {mae:.3f} t/ha ({rel_err:.1f}%)")
    print(f"  R²:  {r2:.3f}")
    
    if mae < best_mae:
        best_mae = mae
        best_model = (name, clf, mae, r2)

print(f"\n🏆 Best: {best_model[0]} (MAE {best_model[2]:.3f} t/ha)")

# ── 2. Train final model ──
print("\n" + "=" * 60)
print("🎯 FINAL MODEL (all data)")
print("=" * 60)

X_all, y_all = prep_data(all_data)
final_model = RandomForestRegressor(n_estimators=200, max_depth=8, random_state=42)
final_model.fit(X_all, y_all)

# Feature names
FEATURE_NAMES = NUM_FEATURES + [f"country_{c}" for c in countries]

# Feature importance
importances = final_model.feature_importances_
print("\nFeature Importances:")
for k, v in sorted(zip(FEATURE_NAMES, importances), key=lambda x: -x[1]):
    print(f"  {k:.<25} {v:.3f}")

# ── 3. Country baseline calibration ──
print("\n" + "=" * 60)
print("🌍 COUNTRY CALIBRATION")
print("=" * 60)

country_stats = defaultdict(list)
for d in all_data:
    country_stats[d['country']].append(d['yield_t_ha'])

country_baselines = {}
print(f"{'Country':<8} {'Mean Yield':<12} {'Samples':<8} {'Range':<15}")
print("-" * 43)
for c in countries:
    yields = country_stats[c]
    country_baselines[c] = {
        'mean': round(np.mean(yields), 2),
        'std': round(np.std(yields), 2),
        'min': round(min(yields), 2),
        'max': round(max(yields), 2),
        'n_samples': len(yields),
    }
    print(f"{c:<8} {np.mean(yields):<12.2f} {len(yields):<8} {min(yields):.2f}–{max(yields):.2f}")

# ── 4. Save model ──
print("\n" + "=" * 60)
print("💾 SAVING MODEL")
print("=" * 60)

model_pkg = {
    'model': final_model,
    'feature_names': FEATURE_NAMES,
    'num_features': NUM_FEATURES,
    'countries': countries,
    'country_idx': country_idx,
    'country_baselines': country_baselines,
    'train_years': years,
    'cv_mae': best_model[2],
    'cv_mae_pct': best_model[2] / np.mean(y_all) * 100,
    'mean_yield': float(np.mean(y_all)),
    'n_samples': len(all_data),
    'best_estimator': best_model[0],
}

with open(MODEL_PATH, 'wb') as f:
    joblib.dump(model_pkg, f)

print(f"✅ Saved: {MODEL_PATH}")
print(f"   MAE: {best_model[2]:.3f} t/ha ({best_model[2]/np.mean(y_all)*100:.1f}%)")
print(f"   Samples: {len(all_data)}")
print(f"   Countries: {len(countries)}")

# ── 5. Per-country accuracy ──
print("\n" + "=" * 60)
print("📋 PER-COUNTRY ACCURACY")
print("=" * 60)

from sklearn.metrics import mean_absolute_error as mae_fn

for c in countries:
    c_data = [d for d in all_data if d['country'] == c]
    if len(c_data) < 10:
        continue
    
    errors = []
    for test_year in sorted(set(d['year'] for d in c_data)):
        train_data = [d for d in all_data if d['year'] != test_year]
        test_data = [d for d in c_data if d['year'] == test_year]
        if not test_data:
            continue
        
        X_train, y_train = prep_data(train_data)
        X_test, y_test = prep_data(test_data)
        
        rf = RandomForestRegressor(n_estimators=200, max_depth=8, random_state=42)
        rf.fit(X_train, y_train)
        preds = rf.predict(X_test)
        
        for p, a in zip(preds, y_test):
            errors.append(abs(p - a))
    
    c_mae = np.mean(errors) if errors else 0
    c_mean = country_baselines[c]['mean']
    print(f"  {c}: MAE {c_mae:.3f} ({c_mae/c_mean*100:.1f}%) — {len(c_data)} samples")

print("\n✅ European model ready!")
print(f"   Use in server.py: load '{MODEL_PATH}'")
