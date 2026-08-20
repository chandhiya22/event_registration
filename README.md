# Confer — Event Registration & Check-in Platform

A small SaaS-shaped platform: attendees register + upload a document, the platform validates async, and both an email notifier and an organizer dashboard react independently via Service Bus pub/sub. Built on Azure Container Apps + Dapr.

## Repo structure

```
confer/
├── registration-api/        # public-facing, accepts registrations, writes to Blob
├── processing-service/      # validates, writes state, publishes event
├── notifier-service/        # subscriber: "sends" confirmation email, KEDA-scaled
├── admin-dashboard-service/ # subscriber: live registration list for organizer
├── frontend/                # static HTML: registration form + dashboard view
└── infra/                   # (add Bicep/Terraform here later)
```

## Local dev with Dapr (before touching Azure)

Install the Dapr CLI, then run each service locally with its own sidecar:

```bash
dapr run --app-id registration-api --app-port 8000 --dapr-http-port 3500 -- uvicorn app.main:app --port 8000
dapr run --app-id processing-service --app-port 8001 --dapr-http-port 3501 -- uvicorn app.main:app --port 8001
```

Dapr components for local dev go in `~/.dapr/components/` — see `dapr-components/` in each service for the Azure-backed versions to swap in later.

## Build order (matches the 30-day plan's Week 4 capstone slot)

1. `registration-api` — get it running locally, storing files to local disk first, then swap to Blob Storage SDK.
2. `processing-service` — add Key Vault-backed validation rule, Dapr state write.
3. Wire Dapr invoke between the two, confirm locally with `dapr run`.
4. `notifier-service` + `admin-dashboard-service` — add Service Bus pub/sub component, confirm fan-out locally against a real Azure Service Bus namespace (Dapr pub/sub still needs a real backing resource, even for local dev).
5. Containerize all 4, push to ACR, deploy to ACA with `--enable-dapr`.
6. Add KEDA scale rule to `notifier-service`.

## Deploy checklist (Azure)

- [ ] Resource group `rg-confer`
- [ ] Storage account + `documents` container
- [ ] Key Vault with `PaymentValidationKey` secret
- [ ] ACR, all 4 images pushed
- [ ] Service Bus namespace, topic `registration-events`, subscriptions `notifier-sub` + `dashboard-sub`
- [ ] ACA environment, 4 container apps deployed with `--enable-dapr`
- [ ] Dapr components registered on the ACA environment: `statestore` (Blob-backed), `pubsub` (Service Bus-backed)
- [ ] Managed identities assigned + RBAC granted (Key Vault Secrets User, Storage Blob Data Contributor)
- [ ] KEDA scale rule on `notifier-service`
