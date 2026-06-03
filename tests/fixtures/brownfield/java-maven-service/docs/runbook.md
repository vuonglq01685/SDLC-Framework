# On-call Runbook

## Incident Response

1. Check application logs: `kubectl logs -l app=my-service`
2. Check database connectivity
3. Escalation: page the on-call engineer if SLA is breached

## Oncall Procedures

- Alert threshold: latency P99 > 500ms
- Escalation path: L1 → L2 → Engineering manager
