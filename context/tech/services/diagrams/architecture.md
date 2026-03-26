# Architecture Diagrams

## System Architecture

```mermaid
graph TB
    subgraph "External Layer"
        WS_CLIENT[WebSocket Clients]
        HTTP_CLIENT[HTTP API Clients]
        CHANNEL_CLIENT[Channel Clients<br/>Feishu/Slack/Discord]
    end

    subgraph "Gateway Layer"
        GW[GatewayServer]
        WS[WebSocketServer]
        HTTP[HTTPServer]
        SM[SessionManager]
        HM[HealthMonitor]
    end

    subgraph "Agent Runtime Layer"
        AR[AgentRuntime]
        CTX[ContextManager]
        TOOLS[ToolRegistry]
        EXEC[ToolExecutor]
    end

    subgraph "Provider Layer"
        OAI[OpenAI]
        ANT[Anthropic]
        MMX[MiniMax]
        OR[OpenRouter]
        CUST[Custom]
    end

    subgraph "Extension Layer"
        MEM[Memory]
        SKL[Skills]
        PLG[Plugins]
        SEC[Secrets]
    end

    subgraph "Infrastructure Layer"
        CRON[CronService]
        DMN[DaemonService]
        BRW[BrowserService]
        CFG[Config]
    end

    WS_CLIENT --> WS
    HTTP_CLIENT --> HTTP
    CHANNEL_CLIENT --> GW

    WS --> GW
    HTTP --> GW
    SM --> GW
    HM --> GW

    GW --> AR
    AR --> CTX
    AR --> TOOLS
    AR --> EXEC

    AR --> OAI
    AR --> ANT
    AR --> MMX
    AR --> OR
    AR --> CUST

    AR --> MEM
    AR --> SKL
    AR --> PLG
    AR --> SEC

    CFG --> GW
    CRON --> GW
    DMN --> GW
    BRW --> AR
```

## Request Flow

```mermaid
sequenceDiagram
    participant Client
    participant Gateway
    participant Session
    participant Agent
    participant Provider
    participant Tools

    Client->>Gateway: HTTP/WebSocket Request
    Gateway->>Session: Create/Get Session
    Session-->>Gateway: Session Info
    Gateway->>Agent: Run Agent
    Agent->>Provider: LLM Request
    Provider-->>Agent: LLM Response
    
    alt Tool Call Required
        Agent->>Tools: Execute Tool
        Tools-->>Agent: Tool Result
        Agent->>Provider: Continue LLM
        Provider-->>Agent: Final Response
    end
    
    Agent-->>Gateway: Agent Response
    Gateway-->>Client: Response
```

## Provider Selection Flow

```mermaid
flowchart TD
    A[Request] --> B{Model ID?}
    B -->|anthropic/*| C[Anthropic Provider]
    B -->|openai/*| D[OpenAI Provider]
    B -->|minimax/*| E[MiniMax Provider]
    B -->|openrouter/*| F[OpenRouter Provider]
    B -->|custom/*| G[Custom Provider]
    
    C --> H[API Call]
    D --> H
    E --> H
    F --> H
    G --> H
    
    H --> I{Stream?}
    I -->|Yes| J[Stream Response]
    I -->|No| K[Complete Response]
    
    J --> L[Return]
    K --> L
```

## Session Lifecycle

```mermaid
stateDiagram-v2
    [*] --> Created: create_session()
    Created --> Idle: initialized
    Idle --> Active: first_message
    Active --> Idle: response_complete
    Active --> Active: continue_conversation
    Idle --> Archived: idle_timeout
    Archived --> Closed: retention_expired
    Active --> Closed: explicit_close
    Idle --> Closed: explicit_close
    Closed --> [*]
```

## Plugin Lifecycle

```mermaid
stateDiagram-v2
    [*] --> Unloaded: plugin_created
    Unloaded --> Loaded: load()
    Loaded --> Activated: activate()
    Activated --> Deactivated: deactivate()
    Deactivated --> Unloaded: unload()
    Activated --> Error: error
    Error --> Deactivated: recovery
    Deactivated --> [*]
    Loaded --> [*]
```

## Memory System

```mermaid
flowchart LR
    subgraph Input
        DOC[Document]
        TEXT[Text]
    end
    
    subgraph Processing
        CHUNK[Chunking]
        EMBED[Embedding]
    end
    
    subgraph Storage
        VEC[Vector Store]
        META[Metadata Store]
    end
    
    subgraph Query
        Q[Query]
        QEMBED[Query Embed]
        SEARCH[Vector Search]
        RESULT[Results]
    end
    
    DOC --> CHUNK
    TEXT --> CHUNK
    CHUNK --> EMBED
    EMBED --> VEC
    EMBED --> META
    
    Q --> QEMBED
    QEMBED --> SEARCH
    VEC --> SEARCH
    META --> SEARCH
    SEARCH --> RESULT
```

## Channel Integration

```mermaid
flowchart TB
    subgraph External
        FEISHU[Feishu]
        SLACK[Slack]
        DISCORD[Discord]
    end
    
    subgraph Channel Layer
        FC[FeishuChannel]
        SC[SlackChannel]
        DC[DiscordChannel]
    end
    
    subgraph Core
        CM[ChannelManager]
        MSG[Message Handler]
        EVT[Event Handler]
    end
    
    subgraph Agent
        AR[AgentRuntime]
    end
    
    FEISHU <--> FC
    SLACK <--> SC
    DISCORD <--> DC
    
    FC --> CM
    SC --> CM
    DC --> CM
    
    CM --> MSG
    CM --> EVT
    
    MSG --> AR
    EVT --> AR
```

## Cron Job Execution

```mermaid
sequenceDiagram
    participant Scheduler
    participant Store
    participant Job
    participant Handler
    participant History

    loop Every Minute
        Scheduler->>Store: Get Due Jobs
        Store-->>Scheduler: Job List
    end
    
    Scheduler->>Job: Execute
    Job->>Handler: Run Handler
    Handler-->>Job: Result
    Job->>History: Record Result
    Job->>Store: Update Next Run
```

## Daemon Service Management

```mermaid
flowchart TB
    subgraph Platform Detection
        DET{Platform?}
    end
    
    subgraph Windows
        WIN_SVC[Windows Service Manager]
        WIN_TASK[Task Scheduler]
    end
    
    subgraph Linux
        SYSTEMD[Systemd Manager]
    end
    
    subgraph macOS
        LAUNCHD[Launchd Manager]
    end
    
    DET -->|Windows| WIN_SVC
    DET -->|Windows| WIN_TASK
    DET -->|Linux| SYSTEMD
    DET -->|macOS| LAUNCHD
    
    WIN_SVC --> OPS[Install/Start/Stop/Status]
    WIN_TASK --> OPS
    SYSTEMD --> OPS
    LAUNCHD --> OPS
```

## Browser Automation Flow

```mermaid
sequenceDiagram
    participant Agent
    participant BrowserService
    participant Playwright
    participant Browser

    Agent->>BrowserService: navigate(url)
    BrowserService->>Playwright: goto(url)
    Playwright->>Browser: Navigate
    Browser-->>Playwright: Page Loaded
    Playwright-->>BrowserService: Success
    BrowserService-->>Agent: ActionResult

    Agent->>BrowserService: screenshot()
    BrowserService->>Playwright: screenshot()
    Playwright->>Browser: Capture
    Browser-->>Playwright: Image Data
    Playwright-->>BrowserService: Buffer
    BrowserService-->>Agent: ActionResult
```

## Secrets Management

```mermaid
flowchart TB
    subgraph API
        STORE[store]
        GET[get]
        DELETE[delete]
        ROTATE[rotate]
    end
    
    subgraph Core
        SM[SecretsManager]
        AUDIT[AuditLog]
    end
    
    subgraph Storage
        MEM[InMemoryStore]
        FILE[FileStore]
    end
    
    subgraph Crypto
        FERNET[FernetCrypto]
    end
    
    STORE --> SM
    GET --> SM
    DELETE --> SM
    ROTATE --> SM
    
    SM --> AUDIT
    SM --> MEM
    SM --> FILE
    SM --> FERNET
```
