workspace "Engineering Modernization Hub" "Un agente de IA propone la modernización de un repositorio; un núcleo determinístico decide permisos, presupuesto, alcance y veredicto." {

    !identifiers hierarchical

    model {
        dev = person "Desarrollador" "Pide una modernización, sigue la ejecución y aprueba el plan." "Persona"

        backstage = softwareSystem "Backstage" "Portal Interno de desarrollado." "Externo"
        identity = softwareSystem "Identidad" "AWS Cognito." "Externo"
        github = softwareSystem "GitHub" "Repositorio de origen y pull request de salida." "Externo"
        docs = softwareSystem "Fuentes oficiales" "Documentación oficial de librerías, consultada desde una lista blanca." "Externo"
        bedrock = softwareSystem "Amazon Bedrock" "Modelos de IA y Guardrails." "Externo"

        hub = softwareSystem "Engineering Modernization Hub" "Orquesta, ejecuta y juzga modernizaciones de código con un agente de IA bajo control determinístico." {

            group "Zona determinística — decide" {
                gateway = container "API Gateway" "Valida el JWT y enruta /modhub/v1." "AWS API Gateway" "Decide"
                api = container "λ api" "11 rutas; crea el run, registra la aprobación en una escritura condicionada y resuelve el objetivo contra el catálogo de estrategias." "Python, AWS Lambda" "Decide"
                sfn = container "Orquestador" "Fija el orden de las fases, la espera de aprobación, los límites y los cortes." "AWS Step Functions" "Decide"
                core = container "λ core_ops" "Veredicto desde el JUnit real, libro de gasto, alcance y traspaso al sandbox. Nunca llama al modelo." "Python, AWS Lambda" "Decide" {
                    dispatch = component "Despachador" "Enruta cada acción del orquestador a su servicio." "Python"
                    ledger = component "Libro de gasto" "Suma el gasto real sin condiciones y devuelve si el dinero o el tiempo se agotaron." "Python"
                    verdict = component "Veredicto" "Tabla de cinco estados evaluada en orden fijo; sin acceso al modelo." "Python"
                    suite = component "Guardia de la suite" "Compara el JUnit final con la línea base: la suite solo puede crecer." "Python"
                    scope = component "Guardia de alcance" "Revalida que el diff quede en rutas aprobadas; falla cerrado." "Python"
                    checks = component "Evidencia de checks" "Traduce la evidencia del sandbox en checks con nombre, según la estrategia." "Python"
                    handoff = component "Traspaso al sandbox" "Snapshot del workspace y URLs prefirmadas." "Python"
                }
                fetchRepo = container "λ fetch_repo" "Descarga el tarball en un SHA exacto, lo sanea y escribe ws/v0." "Python, AWS Lambda" "Decide"
                fetchDoc = container "λ fetch_doc" "Trae documentos de dominios permitidos; sin permisos AWS." "Python, AWS Lambda" "Decide"
                openPr = container "λ open_pr" "Abre el pull request con el diff aprobado." "Python, AWS Lambda" "Decide"
                runs = container "Runs y eventos" "Estado de cada run, libro de gasto y eventos de auditoría." "Amazon DynamoDB" "Decide,Base de datos"
                workspaces = container "Workspaces" "ws/<run>/: v0, v1, JUnit, rastro de cada fase y diff." "Amazon S3" "Decide,Base de datos"
                secrets = container "Secretos" "Token de GitHub." "AWS Secrets Manager" "Decide,Base de datos"
            }

            group "Zona de IA — propone" {
                agent = container "λ agent_phase" "Una invocación por fase (análisis, implementación, corrección). Política de herramientas y guard de presupuesto con CountTokens." "Python, Strands, AWS Lambda" "Propone"
            }

            group "Zona aislada — ejecuta" {
                sandbox = container "Sandbox" "Corre solo las verificaciones con nombre. Sin rol, secretos ni variables de entorno; no root." "AWS Fargate, imagen por perfil" "Ejecuta"
            }
        }

        dev -> backstage "Lanza, sigue y aprueba"
        backstage -> hub.gateway "Llama a la API con JWT" "HTTPS"
        identity -> hub.gateway "Emite y valida el token"
        hub.gateway -> hub.api "Reenvía la solicitud"
        hub.api -> hub.runs "Crea el run; registra la aprobación (escritura condicionada)"
        hub.api -> hub.sfn "Inicia la ejecución y envía la aprobación"
        hub.api -> bedrock "Resuelve el objetivo (solo lectura)"

        hub.sfn -> hub.fetchRepo "Descarga el repositorio"
        hub.sfn -> hub.agent "Invoca cada fase"
        hub.sfn -> hub.core "Registra gasto, plan y veredicto"
        hub.sfn -> hub.sandbox "Lanza las verificaciones"
        hub.sfn -> hub.openPr "Abre el PR"

        hub.fetchRepo -> github "Descarga el tarball @SHA"
        hub.fetchRepo -> hub.secrets "Lee el token"
        hub.fetchRepo -> hub.workspaces "Escribe ws/v0"
        hub.agent -> bedrock "Razona, cuenta tokens"
        hub.agent -> hub.workspaces "Lee v0; escribe v1 y su rastro"
        hub.agent -> hub.fetchDoc "Pide fuentes oficiales"
        hub.fetchDoc -> docs "Descarga documentos permitidos"
        hub.core -> hub.runs "Libro de gasto y estado"
        hub.core -> hub.workspaces "Lee JUnit y diff"
        hub.sandbox -> hub.workspaces "Lee y escribe con URLs prefirmadas"
        hub.openPr -> github "Abre el pull request"
        hub.openPr -> hub.workspaces "Lee el diff"

        hub.sfn -> hub.core.dispatch "Invoca una acción"
        hub.core.dispatch -> hub.core.ledger "record_spend"
        hub.core.dispatch -> hub.core.verdict "compute_verdict"
        hub.core.dispatch -> hub.core.handoff "snapshot y prepare_sandbox"
        hub.core.verdict -> hub.core.suite "¿La suite se mantuvo?"
        hub.core.verdict -> hub.core.scope "¿El diff está dentro de lo aprobado?"
        hub.core.verdict -> hub.core.checks "¿Qué checks pasaron?"
        hub.core.ledger -> hub.runs "Suma atómica del gasto"
        hub.core.verdict -> hub.runs "Persiste estado y motivo"
        hub.core.suite -> hub.workspaces "Lee JUnit"
        hub.core.scope -> hub.workspaces "Lee el diff"
        hub.core.handoff -> hub.workspaces "Copia v0 → v1 y firma URLs"
    }

    views {
        systemContext hub "Contexto" "Quién usa la plataforma y con qué sistemas habla." {
            include *
            autolayout lr
        }

        container hub "Contenedores" "Piezas desplegables, agrupadas por zona de confianza." {
            include *
            autolayout lr
        }

        component hub.core "Componentes_core_ops" "Cómo decide el núcleo, sin pedirle nada al modelo." {
            include *
            autolayout lr
        }

        dynamic hub "Flujo" "Un run de punta a punta." {
            dev -> backstage "1. Pide la modernización"
            backstage -> hub.gateway "2. POST /runs con JWT"
            hub.gateway -> hub.api "3. Reenvía"
            hub.api -> hub.sfn "4. Inicia la ejecución"
            hub.sfn -> hub.fetchRepo "5. Descarga el repositorio"
            hub.sfn -> hub.agent "6. Análisis y plan"
            hub.sfn -> hub.core "7. Registra gasto y plan"
            hub.api -> hub.sfn "8. El dueño aprueba: SendTaskSuccess"
            hub.sfn -> hub.agent "9. Implementa"
            hub.sfn -> hub.sandbox "10. Verifica"
            hub.sfn -> hub.core "11. Calcula el veredicto"
            autolayout lr
        }

        styles {
            element "Persona" {
                shape Person
                background #1565c0
                color #ffffff
            }
            element "Externo" {
                background #eceff1
                color #263238
                stroke #455a64
            }
            element "Decide" {
                background #e8f5e9
                color #1b1b1b
                stroke #2e7d32
            }
            element "Propone" {
                background #f3e5f5
                color #1b1b1b
                stroke #6a1b9a
            }
            element "Ejecuta" {
                background #fff3e0
                color #1b1b1b
                stroke #e65100
            }
            element "Base de datos" {
                shape Cylinder
            }
            element "Software System" {
                background #37474f
                color #ffffff
            }
            element "Container" {
                strokeWidth 3
            }
        }
    }
}
