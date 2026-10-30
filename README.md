# GameWell analysis

A simple Python project: one analysis-ready dataset, one program, and the
outputs it creates. It uses pandas to prepare the data, scikit-learn to compare
predictive models, and matplotlib to make charts.

## Run

Install Python 3.11 or newer, then from this folder run:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python analyze.py
```

On macOS/Linux, activate with `source .venv/bin/activate`.

The program reads `data/gamewell_daily_intervals.csv.gz` and writes aggregate
tables, charts, and a plain-language report to `outputs/`. It does not change
the dataset or write participant identifiers to the outputs.

## Project files

- `analyze.py` — full analysis program
- `data/gamewell_daily_intervals.csv.gz` — analysis-ready dataset
- `data/data_dictionary.csv` — column definitions
- `data/DATASET_NOTES.md` — dataset construction and limitations
- `outputs/` — generated report, tables, and figures
- `requirements.txt` — Python packages

The analysis compares a mean baseline, linear regression, and random forest
using a participant-level train/test split. These are exploratory predictive
models; they do not establish that gaming causes changes in mood. Recorded
linked-console play does not represent all gaming, and zero recorded minutes
does not prove that no gaming occurred.
