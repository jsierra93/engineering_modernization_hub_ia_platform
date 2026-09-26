# Diagramas — Engineering Modernization Hub

## Arquitectura de Componentes

```mermaid
graph TB
    subgraph "apps/" ["🎨 Frontend & CLI"]
        BS["Backstage<br/>apps/backstage/<br/>Full Backstage instance<br/>+ modhub plugins"]
        CLI["CLI<br/>apps/cli/<br/>modhub CLI<br/>Local negotiation"]
    end

    subgraph "services/" ["⚙️ Platform Core (Python Lambdas)"]
        API["λ api<br/>services/api/<br/>11 routes /modhub/v1<br/>JWT auth + resolver"]
        RESOLVER["resolver/<br/>services/api/resolver/<br/>ONLY Bedrock call<br/>objetivo → strategy"]
        CORE["λ core_ops<br/>services/core_ops/<br/>Verdict, budget<br/>scope, policy gate"]
        AGENT["λ agent_phase<br/>services/agent_phase/<br/>Strands + Bedrock<br/>Plan & code gen"]
        FETCH_R["λ fetch_repo<br/>services/fetch_repo/<br/>Tarball @SHA<br/>sanitize, ws/v0"]
        FETCH_D["λ fetch_doc<br/>services/fetch_doc/<br/>Official sources<br/>zero AWS perms"]
        ORCH["Step Functions<br/>services/orchestration/<br/>State machine ASL<br/>Run orchestration"]
    end

    subgraph "sandbox/" ["🔒 Sandbox"]
        FARGATE["Fargate ARM64<br/>sandbox/<br/>Named checks only<br/>Non-root, no creds"]
    end

    subgraph "strategies/" ["📋 Strategy Registry"]
        SDK["_sdk/<br/>strategies/_sdk/<br/>Protocol, manifest<br/>limit validation"]
        PYDANTIC["python-pydantic-v2/<br/>strategies/python_pydantic_v2/<br/>Strategy impl<br/>manifest + checks"]
    end

    subgraph "packages/" ["📦 Shared Libraries"]
        CONTRACTS["contracts/<br/>packages/contracts/<br/>openapi.yaml<br/>API surface spec"]
        POLICY["policy/<br/>packages/policy/<br/>Policy gate (Strands)<br/>Cedar policies"]
        CORE_PY["core_py/<br/>packages/core_py/<br/>Pydantic models<br/>DynamoDB, pricing"]
    end

    subgraph "infrastructure/" ["🏗️ IaC (Terraform)"]
        MODULES["modules/<br/>infrastructure/modules/<br/>cognito, api-gw<br/>step-functions<br/>sandbox-network"]
        ENVS["envs/{personal,prod}<br/>infrastructure/envs/<br/>Environment configs<br/>local/personal/prod"]
    end

    subgraph "AWS Services" ["☁️ AWS (Floci/Real)"]
        COGNITO["Cognito<br/>Auth + JWT<br/>user pool"]
        APIGW["API Gateway v2<br/>Routes + JWT auth"]
        SFN["Step Functions<br/>Orchestration"]
        LAMBDA["Lambda<br/>Compute"]
        FARGATE_AWS["Fargate<br/>Strategy checks"]
        DYNAMODB["DynamoDB<br/>runs, events<br/>tables"]
        S3["S3<br/>workspace<br/>artifacts"]
        SQS["SQS<br/>Notifications"]
        ECR["ECR<br/>Sandbox image"]
    end

    subgraph "tests/" ["🧪 Testing"]
        E2E["e2e/<br/>tests/e2e/<br/>4 mandatory<br/>scenarios"]
        UNIT["unit/<br/>tests/unit/<br/>Platform suite<br/>pytest"]
    end

    %% Connections
    BS -->|POST /runs| API
    BS -->|GET /runs| API
    CLI -->|CLI commands| API

    API -->|resolve| RESOLVER
    RESOLVER -->|→ strategy| CORE
    API -->|→ SF| ORCH
    ORCH -->|invoke| CORE
    ORCH -->|invoke| AGENT
    ORCH -->|invoke| FETCH_R
    AGENT -->|write plan| S3
    CORE -->|read JUnit| FARGATE_AWS
    CORE -->|update verdict| DYNAMODB
    FETCH_R -->|fetch @SHA| S3
    FETCH_D -->|fetch docs| S3
    AGENT -->|fetch docs| FETCH_D

    PYDANTIC -->|manifest| SDK
    API -->|validate| CONTRACTS
    CORE -->|policy gate| POLICY
    API -->|↔| CORE_PY
    AGENT -->|↔| CORE_PY
    FARGATE -->|run checks| FARGATE_AWS
    FARGATE -->|read scope| S3

    MODULES -->|provision| COGNITO
    MODULES -->|provision| APIGW
    MODULES -->|provision| SFN
    MODULES -->|provision| LAMBDA
    MODULES -->|provision| DYNAMODB
    MODULES -->|provision| S3
    MODULES -->|provision| SQS
    MODULES -->|provision| ECR
    ENVS -->|←config| MODULES

    COGNITO -->|JWT verify| APIGW
    APIGW -->|route| LAMBDA
    SFN -->|orchestrate| LAMBDA
    LAMBDA -->|DynamoDB| DYNAMODB
    LAMBDA -->|S3| S3
    SQS -->|notify| API
    ECR -->|image| FARGATE_AWS

    E2E -->|test| API
    UNIT -->|test| CORE_PY

    style API fill:#4CAF50,stroke:#333,stroke-width:2px,color:#fff
    style CORE fill:#2196F3,stroke:#333,stroke-width:2px,color:#fff
    style RESOLVER fill:#FF9800,stroke:#333,stroke-width:2px,color:#fff
    style AGENT fill:#9C27B0,stroke:#333,stroke-width:2px,color:#fff
    style FARGATE fill:#F44336,stroke:#333,stroke-width:2px,color:#fff
