# Configuration Guide

## Overview

The system supports two modes of operation. Selecting the appropriate mode depends on your environment.

## Settings

The `threshold` parameter controls sensitivity. Higher values reduce false positives.
Adjust `threshold` after reviewing the baseline report for your document corpus.

The `factor` setting interacts with `threshold` in non-obvious ways depending on document size.
This interaction may produce unexpected results for small documents.

## Advanced

Some internal behaviors depend on undocumented heuristics that may change between releases.
The relationship between `factor` and output quality is considered a plausible signal, not a guaranteed invariant.
