# Diagramas — Engineering Modernization Hub

Fuente de verdad: el artifact de arquitectura (ver `CLAUDE.md`). Este archivo
solo refleja el funcionamiento real sobre AWS, tal como está construido hoy en
el repo — no incluye piezas en estado "Diseñado" (AgentCore Gateway + Cedar,
red `private`, segunda estrategia) salvo cuando se marcan explícitamente.

## 1. Flujo de datos de un run: request → LLM → guardrails → aprobación → reporte

```mermaid
sequenceDiagram
    autonumber
    actor Dev as Desarrollador
    participant BS as Backstage / CLI
    participant APIGW as API Gateway<br/>(Cognito JWT authorizer)
    participant API as λ api
    participant BR_R as Bedrock<br/>(resolver, solo lectura)
    participant SFN as Step Functions<br/>(núcleo determinístico)
    participant FR as λ fetch_repo
    participant SB as Fargate sandbox<br/>(sin credenciales)
    participant AGENT as λ agent_phase<br/>(Strands)
    participant GATE as Policy gate<br/>(WritableScopeGate)
    participant BR_C as Bedrock<br/>(Haiku / Sonnet)
    participant FD as λ fetch_doc
    participant CORE as λ core_ops<br/>(sin Bedrock)
    participant DB as DynamoDB + S3

    Dev->>BS: login Cognito (OIDC / PKCE)
    Dev->>BS: repo, SHA, objetivo libre,<br/>restricciones, límites
    BS->>APIGW: POST /modhub/v1/runs (JWT)
    APIGW->>API: valida JWT, reenvía request
    API->>BR_R: objetivo (texto libre) + catálogo de estrategias
    BR_R-->>API: strategy_id o null
    alt sin match
        API-->>BS: 422 NO_STRATEGY_MATCH (no crea run, no gasta presupuesto)
    else con match
        API->>API: resolve_limits (plataforma ≥ estrategia ≥ solicitud)
        API->>API: resolve_scope (writable_paths ∩ exclusiones)
        API->>DB: crea run (status PENDING, requested_by = sub)
        API->>SFN: StartExecution
        SFN->>FR: FetchRepo(run_id, repo, commit)
        FR->>DB: descarga tarball @SHA, sanea, guarda ws/v0 en S3
        SFN->>SB: Baseline: corre unit_tests sobre ws/v0 (sin cambios)
        SB-->>SFN: JUnit baseline
        alt baseline falla
            SFN->>CORE: compute_verdict(baseline_failed=true)
            CORE->>DB: persiste BLOQUEADO
        else baseline pasa
            SFN->>AGENT: DiscoveryPlan(run_id, strategy_id, objetivo)
            AGENT->>BR_C: invoca modelo (Haiku, temperatura 0)
            Note over AGENT,BR_C: contenido del repo entra al prompt<br/>envuelto en &lt;untrusted&gt; — Capa 1
            AGENT->>FD: consulta fuentes oficiales (allowlist)
            FD-->>AGENT: contenido marcado como &lt;untrusted&gt;
            AGENT-->>SFN: plan estructurado, viabilidad, fuentes
            SFN->>CORE: record_spend + record_plan
            CORE->>CORE: calcula plan_hash (nunca el modelo)
            alt agente concluye inviable
                CORE->>DB: persiste BLOQUEADO (con evidencia)
            else viable
                CORE->>DB: run.status = AWAITING_APPROVAL
                SFN->>DB: SQS ApprovalRequired (notificación best-effort)
                DB-->>BS: campana / modhub watch
                Note over SFN: ejecución PAUSADA con task token<br/>(waitForTaskToken)
                Dev->>BS: revisa plan + plan_hash
                Dev->>BS: aprueba o rechaza
                BS->>APIGW: POST /runs/{id}/approval (JWT)
                APIGW->>API: valida JWT (login reciente)
                API->>DB: update condicional:<br/>sub = requested_by AND status = AWAITING_APPROVAL<br/>AND plan_hash igual
                alt condición falla
                    API-->>BS: 401 / 403 / 409 (evento de auditoría)
                else condición cumple
                    API->>SFN: SendTaskSuccess(task_token)
                    SFN->>AGENT: Implement(plan) — solo writable_paths
                    AGENT->>GATE: cada write_file pasa por el gate — Capa 2
                    GATE-->>AGENT: allow (dentro de scope) / deny + evento
                    AGENT->>BR_C: invoca modelo (Sonnet, temperatura 0)
                    AGENT-->>SFN: workspace ws/vN
                    SFN->>SB: Verify: corre install, unit_tests, lint
                    SB-->>SFN: JUnit real — Capa 3 (sandbox sin credenciales)
                    loop hasta max_iterations
                        alt Verify falla
                            SFN->>AGENT: Fix(junit_key, iteration)
                            AGENT->>BR_C: propone corrección
                            AGENT-->>SFN: ws/vN+1
                            SFN->>SB: Verify de nuevo
                        end
                    end
                    SFN->>CORE: compute_verdict(JUnit final vs. baseline)
                    CORE->>CORE: check_suite_integrity<br/>(tests nunca bajan, skipped+xfailed nunca suben,<br/>passed nunca baja)
                    CORE->>DB: persiste veredicto + diff + reporte
                end
            end
        end
    end
    Dev->>BS: GET /runs/{id}/report
    BS->>APIGW: (JWT)
    APIGW->>API: valida JWT
    API->>DB: lee veredicto (core_ops) + narrativa (agent_phase)
    API-->>BS: reporte final (Markdown / JSON)
    BS-->>Dev: muestra veredicto, diff, fuentes, costo
```

**Quién decide qué en cada paso:**
- **Determinístico** (`λ api`, Step Functions, `λ core_ops`, DynamoDB, IAM): valida el request, resuelve límites y alcance por intersección de tres niveles, congela `plan_hash`, aprueba con un único update condicional, calcula el veredicto desde el JUnit real. Nunca consulta a Bedrock para nada de esto.
- **LLM propone** (`λ agent_phase` con Strands + Bedrock): explora el repo, arma el plan, escribe código y pruebas, propone correcciones. Cada tool call pasa por el policy gate antes de ejecutarse.
- **Sandbox ejecuta** (Fargate ARM64, sin task role, sin variables, no root): corre únicamente los checks con nombre que la estrategia declaró (`install`, `unit_tests`, `lint`).
- **Única excepción documentada**: `λ api` invoca Bedrock una vez, de solo lectura, para resolver `objetivo` (texto libre) contra el catálogo de estrategias — decide a qué estrategia atiende la solicitud, nunca qué se le permite hacer una vez resuelta.

## 2. Las tres capas de defensa contra contenido no confiable

```mermaid
flowchart LR
    subgraph L1["Capa 1 · Entrada"]
        direction TB
        A1["Contenido del repo o de fetch_doc"] --> A2["Envuelto en<br/>&lt;untrusted source=...&gt;<br/>(agent_phase/untrusted.py)"]
        A2 --> A3["System prompt: es DATO,<br/>nunca instrucción"]
    end
    subgraph L2["Capa 2 · Autorización"]
        direction TB
        B1["Cada tool call del agente"] --> B2["WritableScopeGate<br/>(hook de Strands)"]
        B2 --> B3{"¿Ruta dentro de<br/>writable_paths?"}
        B3 -->|no| B4["deny + evento<br/>(fail closed)"]
        B3 -->|sí| B5["allow"]
    end
    subgraph L3["Capa 3 · Consecuencia"]
        direction TB
        C1["Sandbox Fargate"] --> C2["Sin task role,<br/>sin variables, no root"]
        C3["core_ops"] --> C4["Calcula veredicto del<br/>JUnit real, sin Bedrock"]
        C5["check_suite_integrity"] --> C6["Tests nunca bajan,<br/>skipped+xfailed nunca suben"]
    end
    L1 --> L2 --> L3
```

## 3. Componentes AWS reales por zona de confianza

```mermaid
flowchart TB
    subgraph DEV["Desarrollador"]
        BSF["Backstage<br/>Scaffolder / Modernizaciones"]
        CLI["modhub CLI"]
    end

    subgraph DET["Zona determinística — decide"]
        COG["Cognito<br/>user pool, 2 app clients"]
        AGW["API Gateway<br/>JWT authorizer"]
        LAPI["λ api<br/>11 rutas /modhub/v1"]
        SFNX["Step Functions<br/>orquesta fase a fase"]
        LCORE["λ core_ops<br/>sin Bedrock: veredicto,<br/>presupuesto, alcance"]
        DDB["DynamoDB<br/>runs · eventos · budget · task token"]
        S3X["S3<br/>ws/v0…vN · JUnit · diff · reportes"]
        SQSX["SQS + DLQ<br/>notificaciones"]
    end

    subgraph LLM["Zona LLM — propone"]
        LAGENT["λ agent_phase<br/>Strands Agents"]
        BEDROCK["Amazon Bedrock<br/>Haiku → análisis<br/>Sonnet → código"]
        LFD["λ fetch_doc<br/>allowlist, cero permisos AWS"]
        LFR["λ fetch_repo<br/>tarball @SHA, ws/v0"]
    end

    subgraph SANDBOX["Sandbox — ejecuta código no confiable"]
        FARGATE["ECS Fargate ARM64 + Spot<br/>sin task role, sin variables, no root<br/>checks: install · unit_tests · lint"]
    end

    subgraph EXT["Internet — fuentes externas"]
        GH["GitHub<br/>fork @SHA"]
        PYPI["PyPI"]
        DOCS["Docs oficiales<br/>pydantic, osv.dev"]
    end

    BSF -- OIDC --> COG
    CLI -- PKCE --> COG
    BSF -- JWT --> AGW
    CLI -- JWT --> AGW
    AGW --> LAPI
    LAPI -- resolver, solo lectura --> BEDROCK
    LAPI --> SFNX
    SFNX --> LFR --> GH
    SFNX --> FARGATE
    SFNX --> LAGENT
    LAGENT --> BEDROCK
    LAGENT --> LFD --> DOCS
    FARGATE -. pip modo public .-> PYPI
    SFNX --> LCORE
    LCORE --> DDB
    LCORE --> S3X
    SFNX -- ApprovalRequired --> SQSX
    SQSX --> BSF
    LFR --> S3X
    LAGENT -- URLs prefirmadas --> S3X
    FARGATE -- URLs prefirmadas --> S3X

    style DET fill:#E1F0EE,stroke:#0D6A66
    style LLM fill:#FAEEDC,stroke:#A35F12
    style SANDBOX fill:#FAE7E4,stroke:#AE3A31
    style DEV fill:#E5ECF7,stroke:#3E5B8A
    style EXT fill:#E6EAED,stroke:#66727C
```

## 4. Los cinco estados finales (evaluados en orden, primero que aplica gana)

```mermaid
flowchart TD
    Start["core_ops.evaluate_verdict"] --> Q1{"¿Presupuesto o tiempo<br/>agotado antes de veredicto?"}
    Q1 -->|sí| S1["PRESUPUESTO_AGOTADO"]
    Q1 -->|no| Q2{"¿Baseline ya falla, o<br/>agente concluye inviable?"}
    Q2 -->|sí| S2["BLOQUEADO"]
    Q2 -->|no| Q3{"¿Fix agotado sin pasar,<br/>error irrecuperable, o<br/>suite debilitada?"}
    Q3 -->|sí| S3["FALLIDO_CONTROLADO"]
    Q3 -->|no| Q4{"¿install + unit_tests pasan<br/>pero lint falla?"}
    Q4 -->|sí| S4["COMPLETADO_PARCIALMENTE"]
    Q4 -->|no| S5["LISTO_PARA_REVISION<br/>(todos los checks pasan,<br/>suite intacta, diff en scope)"]

    style S1 fill:#FAE7E4,stroke:#AE3A31
    style S2 fill:#FAE7E4,stroke:#AE3A31
    style S3 fill:#FAE7E4,stroke:#AE3A31
    style S4 fill:#FAEEDC,stroke:#A35F12
    style S5 fill:#E1F0EE,stroke:#0D6A66
```

`CANCELADO` es aparte: una decisión humana vía `POST /runs/{id}/cancellation`, no un resultado de la modernización.
