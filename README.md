# Replication Package: Kubernetes Components, Objects and Configuration Management

This package contains the source code, the generated data files and the scanner patterns for our empirical study of how open-source projects use Kubernetes components, objects and configuration management tools. With them, you can repeat the repository analysis for both research questions (**RQ1** and **RQ2**).

> **Note:** The manuscript for this study is not yet published. Table, figure and equation numbers below refer to the current version of the manuscript and may change.

## Contents

| Folder / file | What it contains |
|---|---|
| [`Codes/`](Codes) | Python scripts for the full pipeline: filtering, cloning, scanning, cadence analysis, statistics and plots |
| [`csv_files_generated_by_codes/`](csv_files_generated_by_codes) | All `.csv` files produced by the scripts (including `scan_output/`) |
| [`patterns_searched_by_the_scanner.csv`](patterns_searched_by_the_scanner.csv) | The patterns used to detect Persistent Entities (PEs), workloads and configuration management tools in the repositories |
| Survey and Interview Data | Not included in this repository (see [below](#survey-and-interview-data)) |

## Pipeline at a glance

```
repo_filtering.py ──► bulk_clone_full.py ──► k8s_focused_scanner.py ──► repo_summary.csv
   (criteria 1–4)        (1,429 repos)        (uses the patterns CSV)
                                                       │
release_k8s_info.py ──► compute_cadence.py ──► categorize_cadence.py ──► 565-repo cohort
                                                  (criterion 5)              │
                                                                             ▼
                                         RQ1 and RQ2 analyses, tables and figures
```

## Source code (`Codes/`)

### 1. Collecting the repositories

| Script | What it does | RQ |
|---|---|---|
| `repo_filtering.py` | Filters a large pool of repositories using criteria 1–4. | RQ1 |
| `bulk_clone_full.py` | Clones the 1,429 filtered repositories to the local machine. | RQ1 |
| `k8s_focused_scanner.py` | Scans the 1,429 repositories using the patterns in `patterns_searched_by_the_scanner.csv`. Builds key files such as `repo_summary.csv` (repository names, object counts, etc.), showing which PEs and configuration management tools each repository uses. | RQ1 |
| `repo_attributes.py` | Analyzes the attributes of the final 565 repositories: commits, contributors, stars, config script counts, etc. | — |

### 2. Release cadence

| Script | What it does | RQ |
|---|---|---|
| `release_k8s_info.py` | Extracts `REPO`, `RELEASEINDEX`, `RELEASEDATE` and `K8SFIRSTCOMMITDATE` from the cloned repositories. | RQ1 |
| `compute_cadence.py` | Uses the output of `release_k8s_info.py` to compute `OVERALLRELEASECADENCE`, `POSTK8SRELEASECADENCE` and `PREK8SRELEASECADENCE` per repository. | RQ2 |
| `categorize_cadence.py` | Applies criterion 5 to get the final 565 repositories, and assigns each one a `CADENCEGROUP`: **Rapid+**, **Rapid**, **Modern** or **Slow**. | RQ2 |

### 3. Persistent Entities and configuration management (tables)

| Script | What it does | Output | RQ |
|---|---|---|---|
| `obj_in_repo_percent.py` | Builds the **Repo%** column of the PE usage table (Table V in the manuscript). Filters `repo_summary.csv` to the 565-repo cohort, then counts how many repositories contain each of the 19 PEs. | — | RQ1 |
| `obj_per_category_for_heatmap.py` | Computes the proportion of each PE per category (Equation 1 in the manuscript), used for the heatmap. | `object_usage_heatmap.csv` | RQ1 |
| `config_mangement_percent.py` | Builds the configuration management adoption table (Table VII in the manuscript). For each tool (Flux, ArgoCD, Ansible, Terraform, Helm), it finds the matching `repo_summary.csv` column, counts the repositories using it, and compares that rate with the survey "Yes" rate using **Cohen's h**. Each tool is labeled *Alignment*, *Partial Alignment* or *Divergence*. | `config_method_percent.csv` | RQ2 |
| `config_cadence.py` | Joins the 565-repo cohort with `repo_summary.csv` to build the config management vs. cadence group contingency file. Includes a manual IaC reclassification for `manusa/yakc` and `manusa/yakd`. | `config_cadence.csv` | RQ2 |
| `avg_median_for_configTable.py` | Builds the configuration method by cadence group table (Table IX in the manuscript). Detects five tools in the cloned files (Helm via `Chart.yaml`, Terraform via `.tf`, Ansible via `roles/`, `ansible.cfg` or playbooks, ArgoCD via `argoproj.io`, Flux via `fluxcd.io`), groups them into three methods (GitOps, IaC, Package Manager), and reports the mean and median per cadence group. | `table_ix_config_method.csv` | RQ2 |

### 4. Monthly activity over time

| Script | What it does | Output | RQ |
|---|---|---|---|
| `monthly_object_release.py` | For each post-K8s cadence repository, walks the git history for newly added YAML files (`--diff-filter=A`), reads their `kind:` fields, counts the 17 object types per month, and joins the monthly release counts. | `monthly_object_release_cadence.csv` | RQ2 |
| `monthly_scheduling_release_v2.py` | Counts 3 scheduling features per month: Node Affinity and Pod Anti-Affinity (under an `affinity:` block) and list-valued taints, together with release counts. | `monthly_scheduling_release_cadence.csv` | RQ2 |
| `compute_pe_per_month.py` | Reads the two monthly files above and computes the monthly percentage of each PE (Formula 2 in the manuscript). | `pe_per_month.csv`, `pe_per_month_wide.csv` | RQ2 |

### 5. Statistics and figures

| Script | What it does | RQ |
|---|---|---|
| `chisquare.py` | Runs a Chi-Square test of independence between two categorical columns of a CSV. | RQ2 |
| `wavelet.py` | Computes wavelet coherence between two monthly time series (for example, object count vs. release count), and draws scale-averaged line plots and/or time-frequency contour plots. | RQ2 |
| `time-plot.py` | Plots time-series line charts of object and release counts per month, optionally grouped and smoothed with a rolling mean. | RQ2 |
| `plot_figure2.py` | Plots the monthly PE percentages from `pe_per_month.csv` (Figure 2 in the manuscript). | RQ2 |

## Generated data (`csv_files_generated_by_codes/`)

All `.csv` files produced by the scripts above. The raw scan results (hits and matrices for READMEs, YAML files, SDKs, workloads and scheduling features) are in `scan_output/`.

## Survey and Interview Data

The survey and interview materials used for RQ1 are **not included in this repository**:

- **Interview guide:** the semi-structured interview questions
- **Raw transcripts:** all interview transcripts
- **Codebook:** the thematic analysis codes
- **Online survey questions:** the questions asked in the survey
- **Online survey data:** the responses collected from the survey

## Requirements

Python 3, plus the packages the scripts import (for example `pandas`, `scipy`, `matplotlib` and `pyyaml`). Repository cloning and history scanning also need `git` installed.
