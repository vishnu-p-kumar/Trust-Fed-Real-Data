# Model README: Electricity Theft and Anomaly Detection

This file explains the models used in the project, why each model is used, why that model was chosen for this problem, and what other models could be used instead.

The project does not use only one model because electricity theft detection is not a single task. It includes:

- anomaly detection
- theft classification
- demand forecasting
- pole tamper detection
- risk scoring
- explainable AI
- data drift monitoring
- hyperparameter optimization

## 1. Model Overview

| Task | Model Used | File | Output |
| --- | --- | --- | --- |
| Meter anomaly detection | Isolation Forest | `src/train_models.py`, `src/detect_anomaly.py` | `anomaly_score`, `is_anomaly` |
| Theft classification | Random Forest Classifier | `src/train_models.py`, `src/theft_detector.py` | `random_forest_probability` |
| Theft classification | XGBoost Classifier | `src/train_models.py`, `src/theft_detector.py` | `xgboost_probability` |
| XGBoost fallback | HistGradientBoostingClassifier | `src/train_models.py` | boosted theft probability |
| Final theft decision | Random Forest + XGBoost probability blend | `src/theft_detector.py` | `theft_probability`, `status` |
| Demand forecasting | LSTM | `src/demand_forecasting.py` | next hour, next day, next week forecast |
| Demand forecasting | Transformer Regressor | `src/transformer_forecasting.py` | transformer forecast comparison |
| Forecast fallback | Seasonal baseline forecaster | `src/demand_forecasting.py`, `src/transformer_forecasting.py` | stable forecast without deep learning |
| Pole tamper detection | Isolation Forest + heuristics | `src/pole_tamper_detector.py` | `tamper_probability`, `tamper_flag` |
| Explainability | SHAP or feature-importance fallback | `src/explainable_ai.py` | prediction reasons |
| Drift monitoring | Evidently or statistical fallback | `src/data_drift_monitor.py` | drift report |
| Optimization | Optuna | `src/model_optimizer.py` | best hyperparameters |

## 2. Why Multiple Models Are Used

Electricity theft cannot be solved reliably using only one algorithm.

A meter may be suspicious because:

- consumption suddenly drops
- consumption suddenly spikes
- voltage becomes irregular
- power factor becomes poor
- night usage becomes abnormal
- actual and expected consumption differ
- pole-level supplied energy does not match metered energy
- current live data differs from training data

Because of this, the project uses a layered model design:

1. Isolation Forest detects unusual meter behavior.
2. Random Forest learns labelled theft patterns.
3. XGBoost improves supervised theft probability.
4. Probability calibration combines model output with anomaly and wastage signals.
5. Risk scoring converts prediction into operational severity.
6. LSTM and Transformer forecast future demand.
7. Pole tamper detection finds illegal connections that may not be visible at meter level.

## 3. Isolation Forest

### Where It Is Used

Files:

- `src/train_models.py`
- `src/detect_anomaly.py`
- `src/pole_tamper_detector.py`

Saved model:

- `models/isolation_forest.pkl`

### Why It Is Used

Isolation Forest is used for anomaly detection. Electricity theft and abnormal meter behavior are rare compared with normal usage. Isolation Forest is good for this because it isolates unusual points faster than normal points.

In this project, it creates:

- `anomaly_score`
- `is_anomaly`

### Why This Model Was Chosen

Isolation Forest was chosen because:

- it works well for rare abnormal records
- it does not require every abnormal pattern to be labelled
- it is faster than many distance-based anomaly methods
- it works well with tabular engineered features
- it is easy to train and deploy
- it can detect unknown suspicious behavior, not only known theft types

### Why It Is Suitable For This Project

The project has synthetic theft labels, but real theft can happen in many unknown ways. A supervised classifier can learn only the patterns it has seen. Isolation Forest adds an unsupervised safety layer that can detect unusual behavior even if the exact theft type was not labelled.

Example:

A meter may not match a known `meter_bypass` pattern, but if it has strange voltage, unusual night consumption, and unexpected current-power relationship, Isolation Forest can still mark it as anomalous.

### What Could Be Used Instead

| Alternative Model | Could Be Used For | Advantage | Limitation |
| --- | --- | --- | --- |
| One-Class SVM | anomaly detection | strong classic anomaly method | slow and sensitive to scaling/kernel choice |
| Local Outlier Factor | anomaly detection | detects local density anomalies | less convenient for streaming prediction |
| Autoencoder | anomaly detection | learns complex normal patterns | needs neural network tuning and more data |
| KNN anomaly detection | anomaly detection | simple distance-based logic | slow for large datasets |
| DBSCAN | anomaly clustering | finds dense normal groups | difficult to tune for mixed smart-meter data |
| Elliptic Envelope | anomaly detection | simple statistical method | assumes data has Gaussian-like distribution |

## 4. Random Forest Classifier

### Where It Is Used

Files:

- `src/train_models.py`
- `src/theft_detector.py`

Saved model:

- `models/random_forest.pkl`

### Why It Is Used

Random Forest is used for supervised theft classification. The generated dataset contains an `is_theft` label, so the model can learn the difference between normal and theft records.

It produces:

- `random_forest_probability`

### Why This Model Was Chosen

Random Forest was chosen because:

- it works very well on tabular data
- it handles nonlinear relationships
- it is more stable than a single decision tree
- it handles noisy synthetic data well
- it does not require feature scaling
- it can use many electrical and weather features together
- it supports class balancing with `class_weight="balanced_subsample"`

### Why It Is Suitable For This Project

Smart-meter theft detection uses structured features:

- voltage
- current
- power
- consumption
- power factor
- temperature
- humidity
- rainfall
- expected consumption
- rolling average
- night usage ratio
- wastage score
- area
- usage profile

Random Forest is suitable because it can learn combinations of these features. For example, theft may not be visible from consumption alone, but consumption plus voltage irregularity plus night usage may reveal suspicious behavior.

### What Could Be Used Instead

| Alternative Model | Could Be Used For | Advantage | Limitation |
| --- | --- | --- | --- |
| Decision Tree | theft classification | very easy to explain | overfits easily |
| Logistic Regression | baseline theft classification | simple and interpretable | too linear for complex theft patterns |
| Support Vector Machine | theft classification | strong on smaller datasets | slower and needs careful scaling |
| KNN | theft classification | simple similarity-based model | slow during prediction |
| Naive Bayes | baseline classification | very fast | unrealistic independence assumption |
| Extra Trees Classifier | theft classification | similar to Random Forest, often faster | can be more random and less stable |

## 5. XGBoost Classifier

### Where It Is Used

Files:

- `src/train_models.py`
- `src/theft_detector.py`

Saved model:

- `models/xgboost_model.pkl`

### Why It Is Used

XGBoost is used as the stronger boosted theft classifier. It learns decision trees sequentially. Each new tree focuses on mistakes made by previous trees.

It produces:

- `xgboost_probability`

### Why This Model Was Chosen

XGBoost was chosen because:

- it performs very well on structured tabular datasets
- it is widely used in fraud detection and risk scoring
- it captures complex decision boundaries
- it often gives stronger probability ranking than Random Forest
- it handles nonlinear feature interactions well
- it works well for imbalanced classification when tuned properly

### Why It Is Suitable For This Project

Electricity theft is similar to fraud detection. The suspicious class is rare, and important signals may be hidden in feature combinations.

For example:

- low reported consumption with high expected consumption
- high current with low consumption
- voltage drop during night hours
- high seeded theft probability plus anomaly score

XGBoost can learn such complex boundaries better than simple linear models.

### Why Random Forest And XGBoost Are Both Used

The project combines both models instead of depending on only one.

In `src/theft_detector.py`, the first blend is:

```text
blended = 0.45 * random_forest_probability + 0.55 * xgboost_probability
```

Then the final theft probability is calibrated using:

```text
theft_probability =
    0.70 * blended_model_probability
  + 0.20 * seeded_theft_probability
  + 0.07 * anomaly_score
  + 0.03 * wastage_score
```

This gives most importance to the supervised models, but still considers anomaly and wastage evidence.

### What Could Be Used Instead

| Alternative Model | Could Be Used For | Advantage | Limitation |
| --- | --- | --- | --- |
| LightGBM | boosted theft classifier | very fast and accurate | extra dependency |
| CatBoost | boosted theft classifier | excellent with categorical data | extra dependency |
| HistGradientBoostingClassifier | boosted classifier | built into scikit-learn | may be less powerful than XGBoost |
| GradientBoostingClassifier | boosted classifier | simple scikit-learn option | slower and older |
| AdaBoost | boosted classifier | simple boosting method | weaker on complex tabular data |
| Neural Network MLP | theft classification | can learn complex patterns | needs more tuning and less interpretable |

## 6. HistGradientBoostingClassifier Fallback

### Where It Is Used

File:

- `src/train_models.py`

### Why It Is Used

This model is used only when XGBoost is not available.

The code checks:

```python
from xgboost import XGBClassifier
```

If import fails, the project uses:

```python
HistGradientBoostingClassifier
```

### Why This Fallback Was Chosen

It was chosen because:

- it is available in scikit-learn
- it is a boosting model
- it keeps the project running without XGBoost
- it avoids breaking training on machines where XGBoost installation fails

### What Could Be Used Instead

- `GradientBoostingClassifier`
- `AdaBoostClassifier`
- `ExtraTreesClassifier`
- `LightGBM` if installed
- `CatBoost` if installed

## 7. Final Theft Probability Model

### Where It Is Used

File:

- `src/theft_detector.py`

### Why It Is Used

The final theft decision is not made from one model directly. The project combines:

- Random Forest probability
- XGBoost probability
- anomaly score
- seeded theft probability
- wastage score

### Why This Approach Was Chosen

This approach was chosen because theft detection is a high-risk decision. Depending on only one model may create unstable results.

The blended method is better because:

- Random Forest adds stability
- XGBoost adds stronger boosted classification
- Isolation Forest adds anomaly evidence
- wastage score adds domain-specific electrical evidence
- seeded theft probability stabilizes live demo theft candidates

### Final Status Rules

The project assigns:

- `Electricity Theft` if `theft_probability` meets the saved model threshold (currently a 0.5 fallback; tune on validation data before research use)
- `Anomaly` if `is_anomaly == 1`
- `Power Wastage` if `wastage_score >= 0.35`
- `Normal` otherwise

### What Could Be Used Instead

| Alternative | Explanation |
| --- | --- |
| Hard voting ensemble | Use majority vote from different models |
| Soft voting ensemble | Average probabilities from multiple models |
| Stacking classifier | Train a meta-model over model outputs |
| CalibratedClassifierCV | Improve probability calibration |
| Business-rule engine | Use expert-defined theft rules |
| Bayesian model | Combine evidence probabilistically |

## 8. LSTM Demand Forecaster

### Where It Is Used

File:

- `src/demand_forecasting.py`

Saved model:

- `models/lstm_model.h5`

### Why It Is Used

LSTM is used for demand forecasting. Electricity consumption is time-series data, meaning future demand depends on past demand.

The project predicts:

- next hour demand
- next day demand
- next week demand

### Why This Model Was Chosen

LSTM was chosen because:

- it is designed for sequence data
- it can learn hourly and daily usage patterns
- it can remember information from previous time steps
- it is commonly used for time-series forecasting
- it is easy to explain in academic projects

### Why It Is Suitable For This Project

Electricity demand has patterns:

- morning usage
- evening peak usage
- night usage
- weekday/weekend difference
- weather-based variation

The LSTM uses a 24-hour lookback window, so it can learn daily consumption rhythm.

### What Could Be Used Instead

| Alternative Model | Could Be Used For | Advantage | Limitation |
| --- | --- | --- | --- |
| ARIMA/SARIMA | demand forecasting | good classical time-series model | less flexible for nonlinear behavior |
| Prophet | demand forecasting | handles seasonality well | extra dependency |
| GRU | demand forecasting | lighter than LSTM | similar benefit, less commonly explained |
| Temporal CNN | demand forecasting | fast sequence model | less intuitive for interviews |
| Random Forest Regressor | demand forecasting | works on engineered lag features | not naturally sequential |
| XGBoost Regressor | demand forecasting | strong tabular forecasting with lags | requires careful feature design |
| Moving Average | baseline forecast | simple and stable | cannot learn complex patterns |

## 9. Transformer Regressor

### Where It Is Used

File:

- `src/transformer_forecasting.py`

Saved model:

- `models/transformer_forecaster.pt`

### Why It Is Used

The Transformer Regressor is used as an advanced forecasting model. It gives a second forecast path that can be compared with LSTM.

### Why This Model Was Chosen

Transformer forecasting was chosen because:

- transformers are modern sequence models
- attention can learn relationships across the lookback window
- it can model longer-range dependencies
- it gives a useful comparison against LSTM
- it makes the forecasting module more complete

### Why It Is Suitable For This Project

Electricity demand can depend on multiple previous time positions, not only the most recent hour. Transformer attention can learn which previous time steps are important.

Example:

The demand at 8 PM today may be related to:

- 7 PM today
- 8 PM yesterday
- weekend/weekday patterns
- previous peak hours

### What Could Be Used Instead

| Alternative Model | Could Be Used For | Advantage | Limitation |
| --- | --- | --- | --- |
| LSTM | sequence forecasting | simpler and proven | may struggle with longer dependencies |
| GRU | sequence forecasting | lighter than LSTM | similar limitations |
| Temporal Fusion Transformer | advanced forecasting | strong time-series transformer | more complex |
| Informer | long-sequence forecasting | efficient long-range attention | advanced implementation |
| N-BEATS | time-series forecasting | strong deep forecasting model | extra implementation effort |
| XGBoost Regressor | forecast with lag features | strong and practical | requires manual lag features |

## 10. Seasonal Baseline Forecaster

### Where It Is Used

Files:

- `src/demand_forecasting.py`
- `src/transformer_forecasting.py`

### Why It Is Used

The baseline forecaster is used when:

- TensorFlow is unavailable
- PyTorch is unavailable
- the dataset is too small
- trained deep learning model files are missing

### Why This Model Was Chosen

It was chosen because the project should not fail if deep learning dependencies are missing. The dashboard and API should still return forecast values.

### What Could Be Used Instead

- moving average
- exponential smoothing
- seasonal naive forecast
- ARIMA
- Prophet

## 11. Pole Tamper Detection Model

### Where It Is Used

Files:

- `src/pole_monitoring.py`
- `src/pole_tamper_detector.py`

### Why It Is Used

Meter-level theft detection may miss illegal direct tapping from a pole. Pole monitoring compares supplied energy and metered energy.

Core idea:

```text
energy_gap = supplied_energy - meter_energy_sum - technical_losses
```

If the gap is very high, it may indicate:

- illegal connection
- hidden load
- unmetered usage
- pole tampering
- technical fault

### Why This Approach Was Chosen

It combines domain logic and anomaly detection:

- energy-balance rules catch obvious mismatch
- Isolation Forest catches abnormal pole behavior compared with history
- heuristic scoring keeps the result explainable

### What Could Be Used Instead

| Alternative Model | Could Be Used For | Advantage | Limitation |
| --- | --- | --- | --- |
| Pure rule-based detection | pole tamper detection | easy to explain | may miss subtle cases |
| Regression model | predict expected pole energy | useful for mismatch detection | needs good historical data |
| Graph Neural Network | transformer-pole-meter topology | models grid structure directly | much more complex |
| Bayesian network | uncertainty-aware tamper detection | interpretable probabilistic reasoning | harder to build |
| Autoencoder | pole anomaly detection | learns normal pole patterns | needs more data |

## 12. SHAP Explainability

### Where It Is Used

File:

- `src/explainable_ai.py`

### Why It Is Used

SHAP is used to explain why a prediction is suspicious. A theft detection system should not only say "theft probability is high"; it should explain which features contributed.

### Why This Method Was Chosen

SHAP was chosen because:

- it is widely used for model explainability
- it works well with tree-based models
- it gives feature-level contribution values
- it helps make predictions understandable to inspectors

### What Could Be Used Instead

| Alternative | Use |
| --- | --- |
| LIME | local explanation for individual predictions |
| permutation importance | global feature importance |
| tree feature importance | simple model-level explanation |
| partial dependence plots | show feature effect |
| rule-based explanations | manually generated reasons |

## 13. Evidently Drift Monitoring

### Where It Is Used

File:

- `src/data_drift_monitor.py`

### Why It Is Used

Evidently is used to monitor drift between historical training data and recent live data.

Drift can happen because:

- weather changes
- user behavior changes
- new meters are added
- area demand changes
- theft patterns change
- sensor quality changes

### Why This Method Was Chosen

It was chosen because:

- it is designed for ML monitoring
- it can detect feature drift
- it can report data quality issues
- it supports production-style model monitoring

### What Could Be Used Instead

- Kolmogorov-Smirnov test
- Population Stability Index
- Jensen-Shannon divergence
- Chi-square test for categorical drift
- custom mean/variance shift checks
- NannyML
- WhyLabs

## 14. Optuna Hyperparameter Optimization

### Where It Is Used

File:

- `src/model_optimizer.py`

Saved output:

- `models/optimizer_best_params.json`

### Why It Is Used

Optuna is used to automatically tune model parameters.

It can tune:

- Isolation Forest contamination
- Random Forest max depth
- XGBoost learning rate

### Why This Method Was Chosen

Optuna was chosen because:

- it is efficient
- it is easy to integrate
- it searches better parameters automatically
- it avoids fully manual trial-and-error tuning

### What Could Be Used Instead

| Alternative | Advantage | Limitation |
| --- | --- | --- |
| GridSearchCV | simple exhaustive search | slow |
| RandomizedSearchCV | faster than grid search | less guided |
| Bayesian optimization | efficient | more setup |
| manual tuning | easy for small experiments | not systematic |
| Hyperopt | popular optimizer | extra dependency |

## 15. Why These Models Were Finally Selected

The final choices were made because they match the project requirements.

### For anomaly detection

Isolation Forest was selected because theft is rare and abnormal behavior may not always be labelled.

### For theft classification

Random Forest and XGBoost were selected because smart-meter data is structured/tabular and contains nonlinear feature interactions.

### For forecasting

LSTM and Transformer were selected because electricity demand is sequential time-series data.

### For reliability

Fallback models were added so the project can still run even if optional libraries are unavailable.

### For real-world usefulness

SHAP, drift monitoring, risk scoring, and pole tamper detection were added because a practical system needs more than raw prediction accuracy.

## 16. Complete Alternatives Summary

| Current Model | Main Purpose | Best Alternatives |
| --- | --- | --- |
| Isolation Forest | meter anomaly detection | One-Class SVM, LOF, autoencoder, DBSCAN |
| Random Forest | theft classification | Extra Trees, Decision Tree, SVM, Logistic Regression |
| XGBoost | boosted theft classification | LightGBM, CatBoost, HistGradientBoosting |
| LSTM | time-series forecasting | GRU, ARIMA, Prophet, Temporal CNN |
| Transformer | advanced forecasting | Temporal Fusion Transformer, Informer, N-BEATS |
| Seasonal baseline | fallback forecasting | moving average, exponential smoothing |
| SHAP | explainability | LIME, permutation importance, feature importance |
| Evidently | drift monitoring | PSI, KS test, WhyLabs, NannyML |
| Optuna | hyperparameter tuning | GridSearchCV, RandomizedSearchCV, Hyperopt |

## 17. Short Interview Answer

If asked "Which models did you use and why?", you can answer:

This project uses a multi-model approach. Isolation Forest is used for anomaly detection because theft is rare and abnormal behavior may not always be labelled. Random Forest and XGBoost are used for theft classification because smart-meter data is tabular and contains nonlinear relationships between voltage, current, consumption, weather, usage profile, and wastage. Their probabilities are blended and calibrated with anomaly score, wastage score, and seeded theft probability to produce the final theft probability. LSTM and Transformer models are used for demand forecasting because electricity consumption is time-series data. The project also includes fallback models, SHAP explainability, drift monitoring with Evidently, Optuna optimization, and pole-level tamper detection using energy-balance logic plus anomaly detection.
