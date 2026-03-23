# Data Flow Diagram

The following diagram shows the full data flow between all system components.

```mermaid
graph TD
    A[CLI Input] --> B[Parser]
    A --> C[Config Loader]
    B --> D[DocumentStructure]
    B --> E[Telemetry]
    D --> F[ConceptGraph]
    D --> G[MermaidEngine]
    D --> H[Ergonomist]
    D --> I[SpatialMapper]
    F --> J[Metrics]
    G --> J
    H --> J
    I --> J
    C --> J
    J --> K[Report Composer]
    J --> L[SummaryWriter]
    K --> M[cognition_report.json]
    L --> N[cognition_summary.md]
    M --> O[Validator]
    O --> P[RefactorEngine]
    P --> Q[refactor_log.json]
```

This diagram intentionally shows a high degree of interconnection to demonstrate the visual load scoring.
