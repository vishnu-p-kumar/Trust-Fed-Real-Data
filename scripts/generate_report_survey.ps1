$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$outputPath = Join-Path $projectRoot "Report_survey.docx"
$tempRoot = Join-Path $projectRoot "reports\\.report_survey_docx"

if (Test-Path $tempRoot) {
    Remove-Item $tempRoot -Recurse -Force
}

$null = New-Item -ItemType Directory -Path $tempRoot
$null = New-Item -ItemType Directory -Path (Join-Path $tempRoot "_rels")
$null = New-Item -ItemType Directory -Path (Join-Path $tempRoot "docProps")
$null = New-Item -ItemType Directory -Path (Join-Path $tempRoot "word")
$null = New-Item -ItemType Directory -Path (Join-Path $tempRoot "word\\_rels")

function Escape-Xml {
    param([string]$Text)

    if ($null -eq $Text) {
        return ""
    }

    return [System.Security.SecurityElement]::Escape($Text)
}

function New-ParagraphXml {
    param(
        [string]$Text,
        [int]$FontSize,
        [string]$Alignment = "left",
        [switch]$Bold
    )

    $escaped = Escape-Xml $Text
    $sizeValue = $FontSize * 2
    $alignmentXml = ""
    if ($Alignment -eq "center") {
        $alignmentXml = '<w:jc w:val="center"/>'
    }
    elseif ($Alignment -eq "both") {
        $alignmentXml = '<w:jc w:val="both"/>'
    }

    $boldXml = ""
    if ($Bold) {
        $boldXml = "<w:b/>"
    }

    return @"
<w:p>
  <w:pPr>
    $alignmentXml
    <w:spacing w:line="360" w:lineRule="auto"/>
  </w:pPr>
  <w:r>
    <w:rPr>
      $boldXml
      <w:sz w:val="$sizeValue"/>
      <w:szCs w:val="$sizeValue"/>
    </w:rPr>
    <w:t xml:space="preserve">$escaped</w:t>
  </w:r>
</w:p>
"@
}

$sections = @(
    @{
        Chapter = "Abstract"
        Body = @(
            "This report presents a detailed study of the project Smart Grid Electricity Theft, Anomaly, and Energy Wastage Detection System developed for Bengaluru smart-grid conditions. The project addresses one of the most important challenges in modern power distribution: the ability to detect suspicious energy usage patterns, recognise equipment or behavior anomalies, estimate power wastage, and forecast future demand using a unified data-driven architecture. In conventional electricity distribution systems, theft is often discovered late, usually after large commercial losses have already been recorded or after field inspections reveal illegal connections, tampered meters, or suspicious consumption deviations. Such delayed response creates financial stress for utilities and also affects planning quality and service reliability.",
            "To address this gap, the project builds an end-to-end pipeline that begins with synthetic smart meter data generation and continues through preprocessing, feature engineering, machine learning based prediction, risk scoring, efficiency evaluation, forecasting, and live system delivery. The data generator creates hourly meter readings within realistic Bengaluru coordinates and simulates several theft scenarios including meter bypass, abnormal spikes, illegal connection, constant under-reporting, and tampered meter behavior. Weather influence, seasonal variation, load curves, usage-profile diversity, and electrical quality measures such as voltage and power factor are incorporated to make the data sufficiently rich for model training and system demonstration.",
            "The analytical core of the project combines Isolation Forest for anomaly detection, Random Forest and gradient-boost style classification for theft prediction, weighted risk scoring for prioritization, efficiency metrics for wastage analysis, LSTM and Transformer based time-series forecasting, and optional explainability and drift monitoring components. These outputs are integrated into a FastAPI backend, a WebSocket based live monitoring service, a dashboard interface, SQLite based storage snapshots, automated report generation, and a geographic theft heatmap. The result is a project that demonstrates both academic relevance and practical utility by showing how modern data science can transform raw smart meter signals into actionable operational intelligence."
        )
    },
    @{
        Chapter = "Introduction"
        Subsections = @(
            @{
                Heading = "Background of the Problem"
                Paragraphs = @(
                    "Electricity distribution systems are under constant pressure to deliver reliable power while controlling technical and commercial losses. Among the non-technical losses, electricity theft remains one of the most damaging issues because it directly affects billing accuracy, utility revenue, and planning efficiency. Theft can take many forms including meter tampering, direct tapping, under-reporting of load, illegal connections, and manipulation of meter electronics. In urban environments, especially where demand is high and load profiles are highly dynamic, such theft becomes difficult to detect using manual inspection alone.",
                    "Traditional monitoring approaches depend heavily on post-event billing analysis, complaint-based investigation, or scheduled field visits. These methods are slow, expensive, and not scalable when thousands of smart meters are distributed across multiple regions. Even where smart meters are available, raw voltage, current, and consumption data must still be converted into meaningful intelligence. A utility needs to know not only whether a meter looks suspicious, but also whether the issue is likely theft, general anomaly, equipment quality degradation, or energy wastage. It also needs to know which cases should be investigated first."
                )
            },
            @{
                Heading = "Need for an Integrated Smart Grid System"
                Paragraphs = @(
                    "A modern smart-grid solution therefore requires more than a single classifier. It must combine data generation or collection, reliable preprocessing, feature extraction, anomaly detection, supervised classification, forecasting, spatial visualization, and decision support. The presence of time-dependent behavior further complicates the problem because legitimate electricity use often changes with daily routine, weekdays versus weekends, weather conditions, festive seasons, and usage category. A method that flags every high-usage meter as suspicious will clearly fail. The system must learn context, trends, and relative deviations.",
                    "This project responds to that requirement by creating a modular architecture where each part contributes a specific role. Synthetic data generation provides a controlled research environment, feature engineering transforms raw measurements into learning-friendly variables, anomaly and theft models capture suspicious behavior from different perspectives, and forecasting modules estimate upcoming load so the system can support operational planning as well as theft detection. Additional components such as risk scoring and efficiency analysis convert prediction output into managerial insight."
                )
            },
            @{
                Heading = "Project Objectives"
                Paragraphs = @(
                    "The first objective of the project is to generate realistic smart meter datasets for Bengaluru that include normal consumption behavior, weather context, area-based location information, usage profiles, and seeded theft patterns. The second objective is to train models that can identify anomalies and classify likely electricity theft using engineered electrical and temporal features. The third objective is to estimate power demand for future horizons such as the next hour, next day, and next week.",
                    "The fourth objective is to transform prediction outputs into actionable operations through risk scoring and efficiency analysis. The fifth objective is to expose the complete analytics system through an API and dashboard so it behaves like a deployable monitoring platform rather than a disconnected academic script. The final objective is to support automated outputs such as heatmaps, reports, and historical storage so that the project can be extended toward real-time decision support."
                )
            },
            @{
                Heading = "Scope of the Project"
                Paragraphs = @(
                    "The scope of this project covers the full data and analytics lifecycle. It includes smart meter data simulation, preprocessing, feature engineering, anomaly detection, supervised theft detection, risk scoring, efficiency estimation, demand forecasting, data drift checking, alerting hooks, API exposure, live updates, and reporting. The project uses Bengaluru as the simulated city and represents multiple local areas in the coordinate map. This helps the heatmap components behave more realistically.",
                    "At the same time, the project is designed to remain practical on ordinary development machines. For that reason, several components use fallback implementations when advanced libraries are not installed. This is an important scope decision because it ensures the complete platform can still run end to end without forcing every environment to install heavy optional packages such as PyTorch or Evidently."
                )
            },
            @{
                Heading = "Significance of the Study"
                Paragraphs = @(
                    "This project is significant because it demonstrates how multiple data science methods can be combined to solve a utility problem in a realistic workflow. It is not limited to theft classification accuracy. Instead, it shows how a utility may generate data, monitor the grid, rank incidents by risk, understand regional patterns, inspect suspicious clusters, and forecast future load using one coordinated pipeline.",
                    "For students and researchers, the project serves as a strong demonstration of applied machine learning in the power systems domain. For practitioners, it provides a prototype architecture that can later be connected to real meter streams, operational dashboards, and alert channels. The combination of analytics depth and deployment-oriented design makes the project more useful than a single notebook-based experiment."
                )
            }
        )
    },
    @{
        Chapter = "Literature Survey"
        Subsections = @(
            @{
                Heading = "Conventional Approaches to Electricity Theft Detection"
                Paragraphs = @(
                    "Early electricity theft studies relied on rule-based inspection systems, billing audits, and domain heuristics. These approaches compared current billing cycles with previous months, checked unusually low reporting against neighborhood averages, or used physical inspection to identify direct tapping and meter tampering. While such methods are easy to understand, they do not scale well and often generate many false positives because legitimate changes in occupancy, equipment usage, or business activity can produce similar behavior.",
                    "Rule-based systems also struggle to capture complex interactions between variables. For example, high nighttime consumption may be legitimate for industrial operations, while moderate night usage could be suspicious for residential meters if it is combined with low reported voltage stability or an unusual power-current gap. The literature increasingly shows that theft detection requires multivariate pattern recognition rather than simple thresholding."
                )
            },
            @{
                Heading = "Use of Unsupervised Learning in Theft and Anomaly Detection"
                Paragraphs = @(
                    "Unsupervised learning has become important in smart-grid analytics because abnormal or fraudulent events are rare by nature and are not always labeled in production data. Methods such as Isolation Forest, clustering, distance-based outlier detection, and autoencoder style reconstruction have been proposed to isolate records that look structurally different from normal consumption patterns. These methods are valuable when utilities do not have large and reliable fraud labels.",
                    "Isolation Forest is especially well-suited to tabular smart meter data because it attempts to isolate outliers through recursive partitioning. Records that require fewer splits to isolate are treated as more unusual. In the context of electricity data, this behavior is useful because rare theft signatures and unusual electrical disturbances often occupy sparse areas of the feature space. The literature generally supports its use as an effective first-stage anomaly detector."
                )
            },
            @{
                Heading = "Supervised Classification for Theft Prediction"
                Paragraphs = @(
                    "When labeled data is available, supervised classification usually offers stronger theft discrimination than pure anomaly detection. Tree-based models such as Decision Trees, Random Forest, Gradient Boosting, and XGBoost are frequently used because electricity consumption problems are mostly structured-data problems with nonlinear feature interactions. These models handle mixed feature scales, capture thresholds effectively, and often provide strong accuracy with limited preprocessing.",
                    "Random Forest is widely appreciated for its stability, resistance to overfitting, and interpretability through feature importance. Gradient boosting models are preferred when ranking suspicious cases is more important than only assigning a hard class label. Several studies report that combining multiple classifiers or blending probabilities gives more reliable theft detection than depending on one model alone. This motivates the ensemble strategy used in the present project."
                )
            },
            @{
                Heading = "Feature Engineering in Smart Meter Analytics"
                Paragraphs = @(
                    "A strong pattern across the literature is that raw smart-meter values are rarely sufficient for high-quality detection. Researchers often derive temporal and electrical indicators such as hourly behavior, daily seasonality, weekend influence, rolling averages, load variability, peak-to-average relationships, voltage deviations, power factor characteristics, and weather-adjusted usage ratios. Such engineered features help models distinguish legitimate high demand from suspicious inconsistency.",
                    "This idea is directly reflected in the project. Rather than treating consumption alone as the main variable, the implementation derives rolling average consumption, consumption variance, peak usage ratio, night usage ratio, weather-consumption ratio, power factor loss, voltage irregularity, and current-power gap. These engineered variables represent the same principle highlighted in prior work: fraud and wastage are often visible not in a single reading but in patterns across time, context, and electrical quality."
                )
            },
            @{
                Heading = "Load Forecasting in Smart Grids"
                Paragraphs = @(
                    "Literature on smart grids consistently emphasizes the importance of load forecasting because utilities must balance generation planning and supply decisions based on anticipated demand. Classical statistical models such as ARIMA remain useful for short-term forecasting, but deep learning methods are increasingly adopted for their ability to learn nonlinear and long-range temporal dependencies. Among these, LSTM has become a common baseline for hourly and daily electricity load prediction.",
                    "More recent studies use attention mechanisms and Transformer based architectures for sequence forecasting. These approaches can model relationships across broader time ranges without the recurrence bottleneck of RNNs. Even when Transformers are not always superior on small datasets, they are valuable in research prototypes because they provide a second forecasting path and support comparative analysis. This project follows that idea by maintaining both LSTM and Transformer style forecasters."
                )
            },
            @{
                Heading = "Explainability, Risk Scoring, and Operational Decision Support"
                Paragraphs = @(
                    "A known limitation of pure machine learning detection systems is that utilities often hesitate to trust a suspicious prediction without reasoning support. As a result, explainable AI methods such as SHAP and feature attribution have gained importance in applied power analytics. Instead of saying only that a meter is suspicious, explainability frameworks identify whether the decision was influenced by voltage irregularity, high night usage, unusual variance, or other contributing signals.",
                    "Another trend in the literature is the movement from detection to prioritization. A utility cannot inspect every alert immediately, so systems increasingly produce risk scores or confidence rankings that combine model predictions with business logic or engineering indicators. This helps limited field teams focus on the most important cases first. The present project extends this principle further by producing risk level categories and dominant-risk explanations."
                )
            },
            @{
                Heading = "Research Gap Addressed by This Project"
                Paragraphs = @(
                    "Many surveyed systems focus on one analytical layer such as fraud detection, forecasting, or clustering, but fewer projects integrate all these elements into a working platform. Another gap is the absence of deployment-oriented design in many academic prototypes. Results are often demonstrated in notebooks without API integration, monitoring loops, dashboards, storage, or generated reports.",
                    "This project addresses that gap by presenting a unified smart-grid platform. It combines synthetic data simulation, anomaly detection, theft classification, demand forecasting, risk scoring, efficiency analysis, drift monitoring, API endpoints, WebSocket delivery, and reporting. That combination makes it suitable as both a survey-backed academic project and a practical engineering prototype."
                )
            }
        )
    },
    @{
        Chapter = "Novality of the project"
        Subsections = @(
            @{
                Heading = "End-to-End Integration Instead of a Single Model"
                Paragraphs = @(
                    "The most important novelty of the project lies in its end-to-end nature. Many projects in this domain end after producing a classification result, but this system moves far beyond that point. It begins with realistic smart meter data simulation, trains multiple model families, performs realtime style inference, stores snapshots, updates a dashboard, creates a geographic heatmap, and generates periodic reports. By connecting all these stages, the project behaves more like a utility analytics platform than a single research script.",
                    "This integrated design is especially valuable from a project perspective because it reflects how real-world analytics systems are used. Detection output has little operational value if it cannot be delivered, inspected, stored, and acted upon. The project therefore treats prediction, visualization, API exposure, and reporting as equally important parts of the solution."
                )
            },
            @{
                Heading = "Rich Synthetic Data with Seeded Theft Behavior"
                Paragraphs = @(
                    "Another novel aspect is the dataset generation strategy. Instead of using oversimplified random values, the project simulates area-based Bengaluru smart meters with usage profiles, weather impact, seasonal variation, voltage behavior, current estimation, power factor changes, expected load, and wastage score. It also explicitly injects multiple theft types such as meter bypass, abnormal spikes, illegal connection, constant low consumption, and tampered meter patterns.",
                    "This is important because electricity theft is not one homogeneous event. Each fraud type distorts electrical behavior in a different way. By generating multiple theft mechanisms, the project creates a more representative training environment and allows downstream models to learn broader suspicious behavior patterns."
                )
            },
            @{
                Heading = "Hybrid Detection Logic"
                Paragraphs = @(
                    "The project does not rely on either anomaly detection or supervised classification alone. Instead, it combines unsupervised anomaly scoring with supervised theft probability estimation and then further enriches the result through risk scoring. This layered design is novel because it recognizes that a suspicious meter may be abnormal even when theft classification is not yet certain, and a meter may also deserve attention because of voltage instability or unusual night usage even before it crosses a hard threshold.",
                    "The risk engine therefore transforms raw model outputs into a more operational decision signal. This shift from binary prediction to ranked risk prioritization reflects a mature design mindset and strengthens the practical value of the system."
                )
            },
            @{
                Heading = "Dual Forecasting Strategy"
                Paragraphs = @(
                    "The inclusion of both LSTM and Transformer based forecasting is another strong novelty. In many student projects, forecasting is either absent or limited to a single sequence model. Here, the system supports two different deep-learning inspired forecasting approaches and provides a structure for comparing their outputs. It also computes an ensemble-style summary for operational use.",
                    "This choice matters because demand forecasting is not only an auxiliary task. In smart grids, accurate demand expectation helps differentiate legitimate high usage from suspicious reporting. By including forecasting inside the same platform, the project connects consumption prediction with theft monitoring and grid planning."
                )
            },
            @{
                Heading = "Operational Modules Beyond Detection"
                Paragraphs = @(
                    "The project also stands out because it introduces modules rarely included together in academic electricity theft work: energy efficiency scoring, drift monitoring, automated PDF report generation, and multi-channel alert hooks. Each of these modules contributes a different operational dimension.",
                    "For example, efficiency analysis identifies wasteful usage that may not be theft but still matters for utility performance. Drift monitoring checks whether data behavior is changing over time, which is crucial for maintaining reliable model behavior after deployment."
                )
            },
            @{
                Heading = "Robust Fallback Architecture"
                Paragraphs = @(
                    "A final novelty is the way the project handles optional dependencies. Instead of failing when advanced packages are absent, it provides fallback behavior such as HistGradientBoosting in place of XGBoost, baseline forecasting in place of unavailable deep-learning models, and heuristic drift checks in place of Evidently. This design improves portability and makes the project demonstrably runnable across constrained environments.",
                    "That kind of graceful degradation is often overlooked in academic projects, yet it is an important software-engineering contribution. It shows that the system was designed not only for ideal conditions but also for practical usability."
                )
            }
        )
    },
    @{
        Chapter = "Algorithm used"
        Subsections = @(
            @{
                Heading = "Data Generation and Simulation Algorithm"
                Paragraphs = @(
                    "The project begins with a simulation algorithm that constructs a catalog of smart meters distributed across Bengaluru areas. Each meter is assigned a usage profile such as residential, commercial, industrial, night-usage heavy, or air-conditioning heavy. Hourly timestamps are created over the selected number of simulation days, and area-specific coordinates are jittered around predefined geographic anchors so that the generated meters appear spatially realistic.",
                    "For every meter and timestamp, the generator calculates expected consumption using a base load curve, day-of-week effects, hour-of-day behavior, seasonal variation, and weather influence. Actual load is then perturbed with stochastic noise to create realistic variability. When a theft event is seeded, the generator modifies the reported consumption pattern according to the chosen theft type. For example, meter bypass reduces reported load relative to actual usage, abnormal spikes inflate actual load irregularly, and illegal connection introduces hidden demand not reflected correctly in metered consumption. Additional electrical variables such as voltage, current, power factor, expected consumption, and wastage score are computed to support downstream analytics."
                )
            },
            @{
                Heading = "Preprocessing and Feature Engineering"
                Paragraphs = @(
                    "Before modeling, the data passes through preprocessing and feature engineering. The records are sorted by meter and timestamp, and time-based fields such as hour of day and day of week are derived from the timestamp column. Grouped rolling statistics are then computed for each meter, including rolling average consumption and rolling consumption variance. These statistics help identify whether the current reading is consistent with the meter's recent history.",
                    "The system also derives domain-aware features such as peak usage ratio, night usage ratio, weather-consumption ratio, power factor loss, voltage irregularity, and current-power gap. Peak usage ratio captures how close a current reading is to the meter's historical peak. Night usage ratio measures the share of energy consumed during suspicious late-night windows. Weather-consumption ratio adjusts usage against environmental conditions. Power factor loss and voltage irregularity reflect electrical quality, while current-power gap measures physical mismatch between related readings. The final feature matrix is created using both numeric variables and one-hot encoded categorical features, allowing tree models to use area and usage-profile information directly."
                )
            },
            @{
                Heading = "Isolation Forest for Anomaly Detection"
                Paragraphs = @(
                    "Isolation Forest is used as the primary anomaly detection algorithm. It is trained mostly on normal-like patterns so that unusual points are isolated quickly in random tree partitions. In the project implementation, the anomaly model is fit using a subset dominated by non-theft records, and the anomaly score threshold is derived from the reference score distribution. This allows the model to flag new records that look structurally different from ordinary behavior, even if they do not perfectly match a known theft label.",
                    "The advantage of Isolation Forest is that it works well in a rare-event setting and does not require exhaustive labels for all abnormal events. In practice, a suspicious reading may come from theft, device malfunction, reporting delay, or some other operational issue. The anomaly model therefore serves as a broad warning layer that supports early investigation and complements the theft classifier."
                )
            },
            @{
                Heading = "Random Forest for Supervised Theft Classification"
                Paragraphs = @(
                    "Random Forest is one of the supervised algorithms used to estimate electricity theft probability. It trains multiple decision trees on bootstrapped samples and averages their predictions to improve stability and reduce variance. This is highly suitable for smart meter data because the input contains nonlinear relationships across consumption, voltage, current, weather, temporal behavior, and engineered ratios.",
                    "In the implementation, the Random Forest classifier is trained on the engineered feature matrix using theft labels seeded during data generation. The model outputs a probability rather than only a hard class. This is important because practical monitoring systems need rankings, not just binary labels. A meter with moderate suspicion may still deserve monitoring even if it is not classified with maximum confidence."
                )
            },
            @{
                Heading = "Boosted Classification Model"
                Paragraphs = @(
                    "The second supervised classifier is a boosted model. When the XGBoost package is available, the system uses XGBoost with tuned depth, learning rate, and estimator settings. If the dependency is absent, the pipeline falls back to HistGradientBoostingClassifier. In both cases, the purpose is to model sharp decision boundaries and nonlinear interactions more aggressively than bagging methods typically do.",
                    "Boosting is effective in structured fraud-style problems because it sequentially improves weak learners by focusing on difficult examples. Within this project, the boosted classifier contributes an independent theft probability signal that is later blended with the Random Forest output. This two-model arrangement improves robustness and reduces dependence on any one classifier's bias."
                )
            },
            @{
                Heading = "Ensemble Theft Probability"
                Paragraphs = @(
                    "Instead of relying on only Random Forest or only the boosted classifier, the system computes a blended theft probability. The implementation uses a weighted combination where both models contribute to the final decision score. This approach reflects a practical ensemble philosophy: if two strong structured-data models view the same meter as suspicious, confidence increases; if they disagree, the blended score moderates the outcome.",
                    "The ensemble strategy is particularly useful in electricity theft detection because suspicious behavior may be subtle and heterogeneous. One model may respond strongly to tree-like threshold effects while another captures stable nonlinear relations in a different way. Their combined probability therefore becomes a more reliable basis for downstream risk scoring."
                )
            },
            @{
                Heading = "Risk Scoring Algorithm"
                Paragraphs = @(
                    "After anomaly and theft probabilities are computed, the project converts these raw outputs into a risk score between 0 and 100. The risk algorithm combines normalized anomaly score, theft-related probability components, voltage irregularity, and night usage ratio through weighted aggregation. The resulting value is then mapped to risk levels such as Low, Medium, High, and Critical.",
                    "This step is algorithmically important because it transforms model outputs into operations language. A field team can prioritize Critical or High meters first, while analysts can still study Medium-risk groups without overloading limited inspection capacity. The system also identifies the dominant factor behind each risk score, such as anomaly-driven risk or voltage-irregularity-dominated risk, which improves interpretability."
                )
            },
            @{
                Heading = "Energy Efficiency and Wastage Analysis"
                Paragraphs = @(
                    "The efficiency algorithm compares expected and consumed energy while incorporating power factor quality. It computes useful energy, total energy, estimated losses, and a final efficiency score expressed on a percentage scale. Meters with poor efficiency or high wastage score are flagged for attention.",
                    "This module is important because not every problematic meter is necessarily fraudulent. Some may reflect operational inefficiency, abnormal device behavior, or wasteful consumption. By separating efficiency analysis from theft prediction, the project broadens its usefulness from fraud identification to overall energy management."
                )
            },
                Heading = "Demand Forecasting with LSTM"
                Paragraphs = @(
                    "The LSTM forecasting algorithm works on aggregated demand over time. The historical series is scaled and converted into lookback windows so that the model learns to predict the next value from recent observations. The network structure includes stacked LSTM layers, dropout for regularization, and dense layers for output projection. The model is used to estimate next-hour, next-day, and next-week demand quantities.",
                    "LSTM is appropriate here because electricity demand is sequential and depends on recent temporal context. The model can learn periodicity and local trend behavior without requiring rigid statistical assumptions. When the data volume is too small or TensorFlow is unavailable, the system falls back to a baseline seasonal forecaster. This ensures the forecasting stage remains available in all environments."
                )
            },
            @{
                Heading = "Transformer Based Forecasting"
                Paragraphs = @(
                    "The Transformer forecasting module offers a second sequence modeling path. After scaling the demand series and forming lookback windows, the project trains a Transformer regressor built on input projection, positional parameters, encoder layers, and a small feedforward output head. The model predicts future demand iteratively by feeding the last prediction back into the rolling forecast window.",
                    "Transformers are useful because they can learn dependencies across broader time ranges more flexibly than purely recurrent models. Even when used as an optional advanced path, they strengthen the research depth of the project. Their inclusion allows direct comparison between recurrent and attention-based forecasting strategies and supports a more comprehensive smart-grid analytics platform."
                )
            },
            @{
                Heading = "Drift Monitoring and Alerting"
                Paragraphs = @(
                    "A deployed machine-learning system must also monitor whether current data differs from the data on which the model was originally trained. For this reason, the project includes a drift monitoring module. When Evidently is installed, the system can use richer drift analysis; otherwise, it performs fallback statistical checks on feature distributions and concept-related shifts such as theft rate or prediction rate changes.",
                    "The alert engine complements this by offering notification hooks for email, Slack, and Telegram when configured. This means the project is not only able to detect issues but can also be extended toward active operational response. Such deployment-aware additions raise the project above the level of a static academic implementation."
                )
            },
            @{
                Heading = "API, WebSocket, Database, and Dashboard Flow"
                Paragraphs = @(
                    "The analytical outputs are delivered through a FastAPI backend that exposes endpoints for health status, overview, meter details, anomalies, theft events, weather impact, forecasting, risk scores, efficiency, and drift reports. A prediction endpoint allows new readings to be scored on demand. This makes the project accessible to both dashboards and external services.",
                    "The runtime loop periodically advances through simulated live data, generates updated predictions, writes tables into SQLite, refreshes cached summaries, and sends snapshots to connected WebSocket clients. The dashboard then uses these payloads to display charts, tables, and heatmaps. This complete flow demonstrates the practical delivery of machine-learning insights to an end user."
                )
            }
        )
    },
    @{
        Chapter = "Conclusion"
        Body = @(
            "The Smart Grid Electricity Theft, Anomaly, and Energy Wastage Detection System demonstrates that electricity-theft analysis becomes significantly more meaningful when it is framed as a complete smart-grid intelligence problem rather than as an isolated classification task. The project successfully combines synthetic data generation, realistic theft seeding, feature engineering, anomaly detection, supervised classification, demand forecasting, efficiency analysis, drift monitoring, API services, dashboard support, and report generation in one coherent platform.",
            "From an analytical perspective, the project shows the value of hybrid modeling. Isolation Forest captures unusual behavior that may not yet resemble labeled theft. Random Forest and boosting models classify likely theft using structured feature interactions. Risk scoring converts raw outputs into prioritized action, while efficiency analysis distinguishes wasteful usage from direct fraud. Forecasting modules add a predictive planning layer."
            "From a software-engineering perspective, the project is equally strong. It includes modular source files, saved models, generated artifacts, REST and WebSocket delivery, database snapshots, heatmap creation, and periodic reporting. The fallback design for optional heavy libraries also makes the system portable and resilient across different execution environments. This is especially valuable for academic demonstration because it ensures the project can still be run even when all advanced dependencies are not present.",
            "Overall, the project provides a strong example of how data science, machine learning, and smart-grid thinking can be combined into a practical decision-support prototype. It is useful as a final-year project because it demonstrates domain understanding, algorithmic breadth, system integration, and deployment awareness at the same time. In future work, the same architecture can be extended with real smart-meter feeds, more advanced explainability, online learning, stronger geo-spatial reasoning, and utility-grade inspection workflows. Even in its present form, it offers a detailed and meaningful contribution to the study of intelligent electricity monitoring."
        )
    },
    @{
        Chapter = "References"
        Body = @(
            "Liu, F. T., Ting, K. M., and Zhou, Z. H. Isolation Forest. Proceedings of the 2008 IEEE International Conference on Data Mining, 2008.",
            "Breiman, L. Random Forests. Machine Learning, Vol. 45, No. 1, 2001.",
            "Chen, T., and Guestrin, C. XGBoost: A Scalable Tree Boosting System. Proceedings of the 22nd ACM SIGKDD International Conference on Knowledge Discovery and Data Mining, 2016.",
            "Friedman, J. H. Greedy Function Approximation: A Gradient Boosting Machine. Annals of Statistics, 2001.",
            "Hochreiter, S., and Schmidhuber, J. Long Short-Term Memory. Neural Computation, 1997.",
            "Vaswani, A., Shazeer, N., Parmar, N., Uszkoreit, J., Jones, L., Gomez, A. N., Kaiser, L., and Polosukhin, I. Attention Is All You Need. Advances in Neural Information Processing Systems, 2017.",
            "Lundberg, S. M., and Lee, S. I. A Unified Approach to Interpreting Model Predictions. Advances in Neural Information Processing Systems, 2017.",
            "MacQueen, J. Some Methods for Classification and Analysis of Multivariate Observations. Proceedings of the Fifth Berkeley Symposium on Mathematical Statistics and Probability, 1967.",
            "Ester, M., Kriegel, H. P., Sander, J., and Xu, X. A Density-Based Algorithm for Discovering Clusters in Large Spatial Databases with Noise. Proceedings of KDD, 1996.",
            "Aggarwal, C. C. Outlier Analysis. Springer, 2017.",
            "Ghahramani, Z. Probabilistic Machine Learning and Artificial Intelligence. Nature, 2015.",
            "Goodfellow, I., Bengio, Y., and Courville, A. Deep Learning. MIT Press, 2016.",
            "Geron, A. Hands-On Machine Learning with Scikit-Learn, Keras, and TensorFlow. O Reilly Media, latest edition.",
            "Montgomery, D. C., Jennings, C. L., and Kulahci, M. Introduction to Time Series Analysis and Forecasting. Wiley, 2015.",
            "Power-system smart grid surveys, utility analytics reports, and machine learning references on anomaly detection, forecasting, clustering, explainability, and fraud analytics were also consulted conceptually while structuring the project survey."
        )
    }
)

$bodyXml = New-Object System.Collections.Generic.List[string]
$bodyXml.Add((New-ParagraphXml -Text "Smart Grid Electricity Theft, Anomaly, and Energy Wastage Detection System" -FontSize 20 -Alignment "center" -Bold))
$bodyXml.Add((New-ParagraphXml -Text "Project Survey Report" -FontSize 16 -Alignment "center" -Bold))
$bodyXml.Add((New-ParagraphXml -Text "" -FontSize 12))

foreach ($section in $sections) {
    $bodyXml.Add((New-ParagraphXml -Text $section.Chapter -FontSize 20 -Alignment "center" -Bold))

    if ($section.ContainsKey("Subsections")) {
        foreach ($subsection in $section.Subsections) {
            $bodyXml.Add((New-ParagraphXml -Text $subsection.Heading -FontSize 16 -Bold))
            foreach ($paragraph in $subsection.Paragraphs) {
                $bodyXml.Add((New-ParagraphXml -Text $paragraph -FontSize 12 -Alignment "both"))
            }
        }
    }

    if ($section.ContainsKey("Body")) {
        foreach ($paragraph in $section.Body) {
            $bodyXml.Add((New-ParagraphXml -Text $paragraph -FontSize 12 -Alignment "both"))
        }
    }
}

$documentXml = @"
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:wpc="http://schemas.microsoft.com/office/word/2010/wordprocessingCanvas"
 xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006"
 xmlns:o="urn:schemas-microsoft-com:office:office"
 xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"
 xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math"
 xmlns:v="urn:schemas-microsoft-com:vml"
 xmlns:wp14="http://schemas.microsoft.com/office/word/2010/wordprocessingDrawing"
 xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
 xmlns:w10="urn:schemas-microsoft-com:office:word"
 xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"
 xmlns:w14="http://schemas.microsoft.com/office/word/2010/wordml"
 xmlns:wpg="http://schemas.microsoft.com/office/word/2010/wordprocessingGroup"
 xmlns:wpi="http://schemas.microsoft.com/office/word/2010/wordprocessingInk"
 xmlns:wne="http://schemas.microsoft.com/office/word/2006/wordml"
 xmlns:wps="http://schemas.microsoft.com/office/word/2010/wordprocessingShape"
 mc:Ignorable="w14 wp14">
  <w:body>
    $($bodyXml -join "`r`n")
    <w:sectPr>
      <w:pgSz w:w="12240" w:h="15840"/>
      <w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440" w:header="708" w:footer="708" w:gutter="0"/>
    </w:sectPr>
  </w:body>
</w:document>
"@

$contentTypesXml = @"
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
  <Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
  <Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>
</Types>
"@

$rootRelsXml = @"
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
  <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>
</Relationships>
"@

$documentRelsXml = @"
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"/>
"@

$coreXml = @"
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
 xmlns:dc="http://purl.org/dc/elements/1.1/"
 xmlns:dcterms="http://purl.org/dc/terms/"
 xmlns:dcmitype="http://purl.org/dc/dcmitype/"
 xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <dc:title>Report Survey</dc:title>
  <dc:creator>Codex</dc:creator>
  <cp:lastModifiedBy>Codex</cp:lastModifiedBy>
  <dcterms:created xsi:type="dcterms:W3CDTF">2026-03-24T00:00:00Z</dcterms:created>
  <dcterms:modified xsi:type="dcterms:W3CDTF">2026-03-24T00:00:00Z</dcterms:modified>
</cp:coreProperties>
"@

$appXml = @"
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"
 xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">
  <Application>Microsoft Office Word</Application>
</Properties>
"@

function Write-Utf8File {
    param(
        [string]$Path,
        [string]$Content
    )

    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($Path, $Content, $utf8NoBom)
}

Write-Utf8File -Path (Join-Path $tempRoot "[Content_Types].xml") -Content $contentTypesXml
Write-Utf8File -Path (Join-Path $tempRoot "_rels\\.rels") -Content $rootRelsXml
Write-Utf8File -Path (Join-Path $tempRoot "word\\document.xml") -Content $documentXml
Write-Utf8File -Path (Join-Path $tempRoot "word\\_rels\\document.xml.rels") -Content $documentRelsXml
Write-Utf8File -Path (Join-Path $tempRoot "docProps\\core.xml") -Content $coreXml
Write-Utf8File -Path (Join-Path $tempRoot "docProps\\app.xml") -Content $appXml

if (Test-Path $outputPath) {
    Remove-Item $outputPath -Force
}

Add-Type -AssemblyName System.IO.Compression.FileSystem
[System.IO.Compression.ZipFile]::CreateFromDirectory($tempRoot, $outputPath)

Write-Output "Created $outputPath"
