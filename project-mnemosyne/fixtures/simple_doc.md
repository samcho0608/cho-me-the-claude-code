# Introduction

This document provides a brief overview of the system architecture.

## Components

The system consists of three main components: the parser, the scorer, and the reporter.

Each component is responsible for a well-defined task. The parser reads raw documents. The scorer computes metrics. The reporter formats results.

## Summary

All components communicate through a shared JSON schema. No external services are required in fast mode.
