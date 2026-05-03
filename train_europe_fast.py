#!/usr/bin/env python3
"""
Fast training: Ridge RF + simplified CV for large datasets.
"""
import json, sys, math, pickle
import numpy as np
from collections import defaultdict
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, r2_score

DATA_PATH = '/home/j/crop-mcp/europe_training_data.json'
MODEL_PATH = '/home/j/crop-mcp/europe_yield_model.pkl'

# CLI: --crop name → load crop-specific data/model
import sys as _sys
_crop_name = "wheat"
for i, arg in enumerate(_sys.argv):
    if arg == "--crop" and i + 1 < len(_sys.argv):
        _crop_name = _sys.argv[i + 1]
if _crop_name != "wheat":
    DATA_PATH = f'/home/j/crop-mcp/europe_training_data_{_crop_name}.json'
    MODEL_PATH = f'/home/j/crop-mcp/europe_yield_model_{_crop_name}.pkl'

with open(DATA_PATH) as f:
    all_data = json.load(f)

print("=" * 60)
print(f"🌾 {_crop_name.upper()} YIELD MODEL (V4) — {len(all_data)} samples")
print("=" * 60)

countries = sorted(set(d['country'] for d in all_data))
country_idx = {c: i for i, c in enumerate(countries)}
years = sorted(set(d["year"] for d in all_data))

NUM_FEATURES = ["gdd", "precip_mm", "solar_kwh", "soil_moisture", "solar_anom_pct", "soil_anom_pct",
                "soc_g_kg", "ph", "clay_pct", "sand_pct", "silt_pct",
                "nitrogen_g_kg", "cec_cmol_kg"]

def prep_data(data_subset):
    X, y = [], []
    for d in data_subset:
        row = [d[k] for k in NUM_FEATURES]
        oh = [0] * len(countries)
        oh[country_idx[d['country']]] = 1
        row.extend(oh)
        X.append(row)
        y.append(d["yield_t_ha"])
    return np.array(X), np.array(y)

print(f"Countries: {countries}")
print(f"Years: {min(years)}–{max(years)}")
print(f"Features: {len(NUM_FEATURES)} numeric + {len(countries)} countries = {len(NUM_FEATURES)+len(countries)} total")

# ── 1. Simplified CV (every 3rd year test) ──
print("\n" + "=" * 60)
print("📊 SIMPLIFIED CV (every 3rd year held out)")
print("=" * 60)

test_years = years[::3]
train_years = [y for y in years if y not in test_years]

train_data = [d for d in all_data if d["year"] in train_years]
test_data = [d for d in all_data if d["year"] in test_years]

X_train, y_train = prep_data(train_data)
X_test, y_test = prep_data(test_data)

models = [
    ("Ridge (alpha=5)", Ridge(alpha=5.0)),
    ("RF 100 trees", RandomForestRegressor(n_estimators=100, max_depth=8, random_state=42, n_jobs=2)),
    ("RF 200 trees", RandomForestRegressor(n_estimators=200, max_depth=8, random_state=42, n_jobs=2)),
]

best_model = None
best_mae = float('inf')

for name, clf in models:
    clf.fit(X_train, y_train)
    preds = clf.predict(X_test)
    mae = mean_absolute_error(y_test, preds)
    r2 = r2_score(y_test, preds)
    rel = mae / np.mean(y_test) * 100
    print(f"{name:.<25} MAE {mae:.3f} ({rel:.1f}%)  R² {r2:.3f}")
    if mae < best_mae:
        best_mae = mae
        best_model = (name, clf)

# ── 2. Full LOYO (only best model) ──
print("\n" + "=" * 60)
print(f"🎯 LOYO CV: {best_model[0]}")
print("=" * 60)

best_clf = best_model[1]
y_true_all, y_pred_all = [], []

# Re-fit best model for LOYO
for test_year in years:
    train = [d for d in all_data if d["year"] != test_year]
    test = [d for d in all_data if d["year"] == test_year]
    X_tr, y_tr = prep_data(train)
    X_te, y_te = prep_data(test)
    m = type(best_clf)(**{k: v for k, v in best_clf.get_params().items() if k != 'n_jobs'})
    if hasattr(m, 'n_jobs'):
        m.n_jobs = 2
    m.fit(X_tr, y_tr)
    preds = m.predict(X_te)
    y_true_all.extend(y_te)
    y_pred_all.extend(preds)

mae_loyo = mean_absolute_error(y_true_all, y_pred_all)
r2_loyo = r2_score(y_true_all, y_pred_all)
rel_loyo = mae_loyo / np.mean(y_true_all) * 100
print(f"LOYO MAE: {mae_loyo:.3f} t/ha ({rel_loyo:.1f}%)  R² {r2_loyo:.3f}")

# ── 3. Train final model ──
print("\n" + "=" * 60)
print("🎯 FINAL MODEL (all 1483 samples)")
print("=" * 60)

X_all, y_all = prep_data(all_data)
final = RandomForestRegressor(n_estimators=200, max_depth=10, random_state=42, n_jobs=2)
final.fit(X_all, y_all)

FEATURE_NAMES = NUM_FEATURES + [f"country_{c}" for c in countries]
importances = final.feature_importances_
print("\nTop 15 Feature Importances:")
for k, v in sorted(zip(FEATURE_NAMES, importances), key=lambda x: -x[1])[:15]:
    print(f"  {k:.<30} {v:.3f}")

# ── 4. Country baselines ──
country_stats = defaultdict(list)
for d in all_data:
    country_stats[d['country']].append(d['yield_t_ha'])

country_baselines = {}
print(f"\n{'Country':<8} {'Mean':<8} {'Samples':<8} {'Range':<15}")
print("-" * 39)
for c in sorted(countries):
    ys = country_stats[c]
    country_baselines[c] = {
        'mean': round(np.mean(ys), 2), 'std': round(np.std(ys), 2),
        'min': round(min(ys), 2), 'max': round(max(ys), 2), 'n_samples': len(ys),
    }
    print(f"{c:<8} {np.mean(ys):<8.2f} {len(ys):<8} {min(ys):.2f}–{max(ys):.2f}")

# ── 5. Save ──
model_pkg = {
    'model': final,
    'feature_names': FEATURE_NAMES,
    'num_features': NUM_FEATURES,
    'countries': countries,
    'country_idx': country_idx,
    'country_baselines': country_baselines,
    'train_years': years,
    'cv_mae': mae_loyo,
    'cv_mae_pct': rel_loyo,
    'mean_yield': float(np.mean(y_all)),
    'n_samples': len(all_data),
    'best_estimator': best_model[0] if best_model else "RF_200",
}
with open(MODEL_PATH, 'wb') as f:
    pickle.dump(model_pkg, f)

print(f"\n✅ Model saved: {MODEL_PATH}")
print(f"   LOYO MAE: {mae_loyo:.3f} t/ha ({rel_loyo:.1f}%)")
print(f"   Samples: {len(all_data)} | Countries: {len(countries)}")
