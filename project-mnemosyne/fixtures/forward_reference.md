# System Overview

The system relies on the **CognitionBridge** protocol to transfer analysis results between subsystems.
Before understanding CognitionBridge, you must understand how the **MetricAggregator** works.

MetricAggregator depends on the **ScoringEngine**, which is covered in the next section.

## ScoringEngine

The ScoringEngine is the core computation unit. It accepts a DocumentStructure and returns a normalized score vector.

## MetricAggregator

The MetricAggregator collects scores from multiple ScoringEngine instances and computes a weighted average.

## CognitionBridge

CognitionBridge is the IPC layer that connects TypeScript commands to Python scoring modules.
It serializes MetricAggregator output into the cognition_report.json schema.
