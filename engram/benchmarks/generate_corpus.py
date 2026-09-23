"""Generate large-scale synthetic coding experiences for PExM testing.

Creates realistic (state, outcome) pairs across many domains by
combining templates with domain-specific details. Produces 500+
unique experiences with no duplicates.
"""

import random
import json
import os

random.seed(741983)

DOMAINS = {
    "auth": {
        "states": [
            "reading the {component} authentication code",
            "debugging the {component} login flow",
            "reviewing the {component} token validation",
            "investigating {component} session timeout",
            "checking {component} RBAC permissions",
        ],
        "components": ["JWT", "OAuth2", "SAML", "API key", "mTLS", "OIDC", "session cookie", "SSO"],
        "outcomes": [
            "{component} uses {detail1}. Tokens expire after {ttl}. Keys stored in {store}.",
            "Auth failure in {component}: {error}. Root cause: {cause}. Fix in {file} line {line}.",
            "{component} validates using {detail1}. Rate limit: {rate} per {window}. Config in {file}.",
            "Session handling for {component}: {detail1}. Concurrent limit: {limit}. TTL: {ttl}.",
        ],
        "fills": {
            "detail1": ["RS256 signing", "HS256 HMAC", "EdDSA keys", "PKCE flow", "authorization code grant", "client credentials", "device flow"],
            "ttl": ["3600s", "1800s", "7200s", "86400s", "300s", "900s"],
            "store": ["Redis", "PostgreSQL", "DynamoDB", "Vault", "AWS Secrets Manager", "etcd"],
            "error": ["token expired mid-request", "signature mismatch", "missing scope", "CORS rejection", "rate limit exceeded", "invalid redirect URI"],
            "cause": ["clock skew between services", "wrong signing key", "misconfigured scope", "origin not whitelisted", "counter overflow", "URL encoding"],
            "file": ["auth.py", "middleware/auth.go", "src/auth/validator.ts", "lib/session.rb", "auth_handler.rs"],
            "line": ["42", "89", "156", "203", "17", "331", "78"],
            "rate": ["100", "50", "200", "1000", "10"],
            "window": ["minute", "second", "hour"],
            "limit": ["3", "5", "10", "1"],
        },
    },
    "database": {
        "states": [
            "investigating {issue} in the {db} database",
            "reviewing the {db} migration for {table}",
            "debugging {db} connection issues",
            "checking {db} query performance for {table}",
            "reading the {db} replication setup",
        ],
        "components": ["PostgreSQL", "MySQL", "CockroachDB", "MongoDB", "Redis", "DynamoDB", "SQLite"],
        "outcomes": [
            "{db} {table} table: {detail}. Index on {column}. Row count: {rows}.",
            "Connection pool: size {pool_size}, max {max_conn}. Timeout: {timeout}ms. Driver: {driver}.",
            "Migration {migration}: {detail}. Applied at {time}. Rollback: {rollback}.",
            "Query on {table}: {detail}. Execution time: {exec_time}ms. Rows scanned: {scanned}.",
            "Replication lag: {lag}ms. Mode: {mode}. Replicas: {replicas}. Failover: {failover}.",
        ],
        "fills": {
            "issue": ["slow queries", "connection timeout", "deadlock", "replication lag", "disk usage spike", "lock contention"],
            "table": ["users", "orders", "products", "sessions", "audit_log", "events", "payments", "notifications"],
            "db": ["PostgreSQL", "MySQL", "CockroachDB", "MongoDB"],
            "detail": ["added composite index", "changed column type to jsonb", "added foreign key constraint", "partitioned by date", "added GIN index for full-text"],
            "column": ["user_id", "created_at", "email", "status", "order_id", "product_id"],
            "rows": ["1.2M", "50K", "10M", "500K", "2.5M", "100K"],
            "pool_size": ["10", "20", "50", "5"],
            "max_conn": ["100", "200", "50", "500"],
            "timeout": ["5000", "10000", "3000", "30000"],
            "driver": ["psycopg2", "asyncpg", "sqlalchemy", "prisma", "diesel"],
            "migration": ["0042", "0078", "0015", "0103", "0091"],
            "time": ["2024-01-15", "2024-03-22", "2024-06-01", "2024-08-10"],
            "rollback": ["safe", "destructive", "manual required"],
            "exec_time": ["45", "230", "1200", "8", "560"],
            "scanned": ["50000", "1200", "500000", "89", "12000"],
            "lag": ["50", "200", "1500", "15", "800"],
            "mode": ["async", "sync", "semi-sync"],
            "replicas": ["2", "3", "1", "4"],
            "failover": ["automatic", "manual", "DNS-based"],
        },
    },
    "infrastructure": {
        "states": [
            "reading the {platform} deployment config",
            "debugging {platform} scaling issues",
            "reviewing the {platform} networking setup",
            "checking {platform} resource limits",
            "investigating {platform} pod failures",
        ],
        "components": ["Kubernetes", "ECS", "Lambda", "EC2", "GKE", "AKS"],
        "outcomes": [
            "{platform} deployment: {replicas} replicas. HPA: {min}-{max} based on {metric}. Strategy: {strategy}.",
            "Resource limits: CPU {cpu}, memory {mem}. Requests: CPU {cpu_req}, memory {mem_req}. QoS: {qos}.",
            "Networking: {detail}. Ingress: {ingress}. TLS: {tls}. DNS: {dns}.",
            "Pod failure: {reason}. OOMKilled: {oom}. Restart count: {restarts}. Last event: {event}.",
            "Scaling event: {detail}. Current replicas: {replicas}. Target: {target}. Cooldown: {cooldown}s.",
        ],
        "fills": {
            "platform": ["Kubernetes", "ECS", "GKE"],
            "replicas": ["3", "5", "2", "10", "1"],
            "min": ["2", "1", "3"],
            "max": ["10", "20", "50", "5"],
            "metric": ["CPU", "memory", "RPS", "custom metric"],
            "strategy": ["RollingUpdate", "Recreate", "Blue-Green", "Canary"],
            "cpu": ["500m", "1000m", "2000m", "250m"],
            "mem": ["512Mi", "1Gi", "2Gi", "256Mi", "4Gi"],
            "cpu_req": ["200m", "500m", "100m"],
            "mem_req": ["256Mi", "512Mi", "128Mi", "1Gi"],
            "qos": ["Guaranteed", "Burstable", "BestEffort"],
            "detail": ["service mesh enabled", "network policy applied", "pod disruption budget set", "affinity rules configured"],
            "ingress": ["nginx", "traefik", "istio", "ALB"],
            "tls": ["cert-manager", "ACM", "manual", "Let's Encrypt"],
            "dns": ["CoreDNS", "Route53", "CloudDNS"],
            "reason": ["OOMKilled", "CrashLoopBackOff", "ImagePullBackOff", "Evicted", "Preempted"],
            "oom": ["yes", "no"],
            "restarts": ["0", "3", "7", "15"],
            "event": ["Liveness probe failed", "Readiness probe failed", "Container killed", "Node pressure"],
            "target": ["8", "15", "3", "20"],
            "cooldown": ["60", "120", "300", "30"],
        },
    },
    "api": {
        "states": [
            "reviewing the {protocol} {endpoint} endpoint",
            "debugging {protocol} {issue} in {service}",
            "checking {protocol} rate limits for {service}",
            "reading the {protocol} schema for {service}",
            "investigating {protocol} latency in {service}",
        ],
        "components": ["REST", "GraphQL", "gRPC", "WebSocket"],
        "outcomes": [
            "{protocol} {endpoint}: {method} returns {response}. Auth: {auth}. Rate limit: {rate}/min.",
            "Latency issue in {service}: p99={p99}ms. Root cause: {cause}. Fix: {fix}.",
            "Schema update for {service}: {detail}. Breaking change: {breaking}. Version: {version}.",
            "Rate limit config: {rate} req/{window} per {scope}. Backend: {backend}. Burst: {burst}.",
        ],
        "fills": {
            "protocol": ["REST", "GraphQL", "gRPC"],
            "endpoint": ["/users", "/orders", "/products", "/search", "/auth/token", "/webhooks", "/events"],
            "service": ["user-service", "order-service", "payment-service", "search-service", "notification-service"],
            "method": ["GET", "POST", "PUT", "PATCH", "DELETE"],
            "response": ["200 JSON", "201 Created", "paginated list", "cursor-based stream"],
            "auth": ["Bearer JWT", "API key", "OAuth2 scope", "mTLS"],
            "rate": ["100", "500", "50", "1000", "25"],
            "p99": ["45", "230", "1200", "500", "2500"],
            "cause": ["N+1 query", "missing index", "serialization overhead", "upstream timeout", "cache miss storm"],
            "fix": ["add dataloader", "create composite index", "switch to protobuf", "increase timeout", "add circuit breaker"],
            "detail": ["added pagination", "deprecated field removed", "new required field", "enum values extended"],
            "breaking": ["yes", "no"],
            "version": ["v2", "v3", "v1.1", "v2.1"],
            "window": ["minute", "second", "hour"],
            "scope": ["API key", "user", "IP", "organization"],
            "backend": ["Redis sliding window", "token bucket", "leaky bucket", "fixed window"],
            "burst": ["10", "50", "100", "0"],
            "issue": ["timeout", "500 errors", "slow response", "malformed response"],
        },
    },
    "security": {
        "states": [
            "investigating the {vuln_type} vulnerability in {component}",
            "reviewing {component} security configuration",
            "checking {component} for {vuln_type} exposure",
            "reading the security audit for {component}",
            "debugging {component} access control",
        ],
        "components": ["auth module", "payment handler", "file upload", "search endpoint", "admin panel", "API gateway", "webhook receiver"],
        "outcomes": [
            "{vuln_type} found in {component}: {detail}. Severity: {severity}. CVSS: {cvss}. Fix: {fix}.",
            "Security config for {component}: {detail}. Encryption: {encryption}. Audit: {audit}.",
            "Access control: {detail}. Roles: {roles}. Default: {default}. Logging: {logging}.",
            "Dependency scan: {count} findings. Critical: {critical}. High: {high}. Tool: {tool}.",
        ],
        "fills": {
            "vuln_type": ["XSS", "SQL injection", "SSRF", "IDOR", "CSRF", "path traversal", "RCE", "open redirect"],
            "component": ["search endpoint", "user profile", "file upload", "admin API", "webhook handler"],
            "detail": ["user input unescaped in HTML", "parameter passed to shell", "URL not validated", "missing auth check", "CORS too permissive"],
            "severity": ["Critical", "High", "Medium", "Low"],
            "cvss": ["9.8", "7.5", "5.3", "3.1", "8.2"],
            "fix": ["input sanitization", "parameterized queries", "URL allowlist", "add authentication", "restrict origins"],
            "encryption": ["AES-256-GCM", "TLS 1.3", "at-rest with KMS", "none"],
            "audit": ["enabled", "disabled", "partial"],
            "roles": ["admin, editor, viewer", "superadmin, admin, user", "owner, member, guest"],
            "default": ["deny", "allow", "viewer"],
            "logging": ["structured JSON", "syslog", "CloudWatch", "none"],
            "count": ["3", "12", "7", "1", "23"],
            "critical": ["0", "1", "2", "3"],
            "high": ["1", "3", "5", "0"],
            "tool": ["Snyk", "Dependabot", "Trivy", "Grype", "OWASP ZAP"],
        },
    },
    "monitoring": {
        "states": [
            "checking the {tool} alerting rules",
            "investigating {metric} anomaly in {service}",
            "reviewing the {tool} dashboard for {service}",
            "reading the on-call runbook for {alert}",
            "debugging {tool} data gaps",
        ],
        "components": ["Prometheus", "Grafana", "Datadog", "PagerDuty", "Sentry", "Jaeger"],
        "outcomes": [
            "{tool} alert: {alert}. Threshold: {threshold}. Window: {window}. Severity: {severity}.",
            "{metric} in {service}: current={current}, baseline={baseline}. Anomaly score: {score}.",
            "Dashboard {service}: {panels} panels. Refresh: {refresh}s. Data source: {source}.",
            "Runbook for {alert}: {steps}. Escalation: {escalation}. MTTR target: {mttr}min.",
        ],
        "fills": {
            "tool": ["Prometheus", "Grafana", "Datadog", "PagerDuty"],
            "metric": ["error rate", "p99 latency", "CPU usage", "memory usage", "request rate", "queue depth"],
            "service": ["api-gateway", "auth-service", "payment-service", "worker-pool"],
            "alert": ["HighErrorRate", "LatencySpike", "PodCrashLoop", "DiskFull", "CertExpiry"],
            "threshold": ["1%", "2s", "90%", "85%", "5"],
            "window": ["5min", "15min", "1h", "30s"],
            "severity": ["P1", "P2", "P3", "P4"],
            "current": ["2.3%", "4500ms", "92%", "78%"],
            "baseline": ["0.1%", "200ms", "60%", "40%"],
            "score": ["0.95", "0.78", "0.62", "0.99"],
            "panels": ["8", "12", "5", "20"],
            "refresh": ["10", "30", "60", "5"],
            "source": ["Prometheus", "InfluxDB", "CloudWatch", "Loki"],
            "steps": ["check logs, verify deployment, rollback if needed", "scale up, check dependencies, page SRE"],
            "escalation": ["team lead -> SRE -> VP Eng", "on-call -> secondary -> manager"],
            "mttr": ["15", "30", "60", "5"],
        },
    },
}


def fill_template(template: str, fills: dict, extra: dict = None) -> str:
    result = template
    all_fills = dict(fills)
    if extra:
        all_fills.update(extra)
    for key, values in all_fills.items():
        placeholder = "{" + key + "}"
        if placeholder in result:
            result = result.replace(placeholder, random.choice(values), 1)
    return result


def generate_experiences(target_count: int = 500) -> list:
    experiences = []
    seen = set()

    while len(experiences) < target_count:
        domain_name = random.choice(list(DOMAINS.keys()))
        domain = DOMAINS[domain_name]

        state_template = random.choice(domain["states"])
        outcome_template = random.choice(domain["outcomes"])

        extra = {}
        if "components" in domain:
            comp = random.choice(domain["components"])
            extra["component"] = comp
            extra["db"] = comp
            extra["platform"] = comp

        state = fill_template(state_template, domain["fills"], extra)
        outcome = fill_template(outcome_template, domain["fills"], extra)

        key = (state, outcome)
        if key not in seen:
            seen.add(key)
            experiences.append({
                "state": state,
                "outcome": outcome,
                "domain": domain_name,
            })

    return experiences


def generate_novel(count: int = 50) -> list:
    """Generate experiences from domains NOT in the training set."""
    novel_domains = [
        ("reviewing the Kubernetes operator for {app}",
         "{app} operator manages {resource}. Reconciliation interval: {interval}s. CRD version: {version}.",
         {"app": ["Redis", "Kafka", "Elasticsearch", "PostgreSQL", "MongoDB"],
          "resource": ["StatefulSets", "PVCs", "ConfigMaps", "Secrets"],
          "interval": ["30", "60", "120", "10"],
          "version": ["v1alpha1", "v1beta1", "v1"]}),
        ("investigating the Terraform state drift for {provider}",
         "State drift in {provider}: {count} resources changed outside Terraform. {resource} modified. Lock: {lock}.",
         {"provider": ["AWS", "GCP", "Azure"],
          "count": ["3", "7", "1", "12"],
          "resource": ["security group", "IAM role", "VPC", "S3 bucket"],
          "lock": ["DynamoDB", "GCS", "Consul", "none"]}),
        ("checking the Spark job performance for {pipeline}",
         "{pipeline} job: {stages} stages, {tasks} tasks. Shuffle: {shuffle}GB. Duration: {duration}min. Skew: {skew}.",
         {"pipeline": ["ETL-daily", "ML-features", "log-aggregate", "user-analytics"],
          "stages": ["5", "12", "3", "8"],
          "tasks": ["200", "1000", "50", "500"],
          "shuffle": ["2.5", "15", "0.5", "50"],
          "duration": ["45", "120", "15", "300"],
          "skew": ["low", "high", "moderate"]}),
        ("reading the mobile push notification config for {platform}",
         "{platform} push: provider={provider}. TTL: {ttl}h. Priority: {priority}. Badge: {badge}.",
         {"platform": ["iOS", "Android", "cross-platform"],
          "provider": ["APNs", "FCM", "OneSignal", "Pusher"],
          "ttl": ["24", "48", "1", "72"],
          "priority": ["high", "normal", "low"],
          "badge": ["enabled", "disabled"]}),
        ("debugging the WebAssembly module loading in {browser}",
         "WASM module for {browser}: size={size}KB. Compile time: {compile}ms. Memory: {memory} pages. Streaming: {streaming}.",
         {"browser": ["Chrome", "Firefox", "Safari", "Edge"],
          "size": ["500", "1200", "250", "3000"],
          "compile": ["45", "120", "200", "15"],
          "memory": ["16", "64", "256", "4"],
          "streaming": ["enabled", "disabled"]}),
    ]

    novels = []
    seen = set()
    while len(novels) < count:
        tpl = random.choice(novel_domains)
        state = fill_template(tpl[0], tpl[2])
        outcome = fill_template(tpl[1], tpl[2])
        key = (state, outcome)
        if key not in seen:
            seen.add(key)
            novels.append({"state": state, "outcome": outcome})

    return novels


if __name__ == "__main__":
    exps = generate_experiences(500)
    novels = generate_novel(50)

    out_dir = os.path.join(os.path.dirname(__file__), "..", "data")
    os.makedirs(out_dir, exist_ok=True)

    with open(os.path.join(out_dir, "experiences_500.jsonl"), "w") as f:
        for e in exps:
            f.write(json.dumps(e) + "\n")

    with open(os.path.join(out_dir, "novel_50.jsonl"), "w") as f:
        for n in novels:
            f.write(json.dumps(n) + "\n")

    domains = {}
    for e in exps:
        d = e["domain"]
        domains[d] = domains.get(d, 0) + 1

    print(f"Generated {len(exps)} experiences across {len(domains)} domains:")
    for d, c in sorted(domains.items()):
        print(f"  {d}: {c}")
    print(f"Generated {len(novels)} novel experiences")
