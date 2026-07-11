from data.records import SAMPLE
from metrics.stats import summarize
from pipeline.validate import ok_summary


def build_summary():
    summary = summarize(SAMPLE)
    if not ok_summary(summary):
        raise ValueError("bad summary")
    return summary
