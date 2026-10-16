# GameWell aggregate viewer

This Streamlit app reads only CSV, JSON, SVG, and Markdown files directly inside the repository's `results/` folder. It does not load participant-level data, accept uploads, fit models, or re-estimate reported values.

From the repository root, create and activate a Python 3.11+ environment, install the root `requirements.txt`, then run:

```sh
python -m streamlit run viewer/app.py
```

On Windows, `run_viewer.bat` uses `.venv` when it exists. The generic chart builder is available in the app's Explore any table page and from the command line with `python -m viewer.plot_cli --help`. To create presentation charts, run `python -m viewer.export_slide_charts`.

Missing numeric values stay missing and are excluded from plotted values. Downloads contain only the selected aggregate result table.
