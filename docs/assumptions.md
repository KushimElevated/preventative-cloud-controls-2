# Supplied context, assumptions and unresolved decisions

## Supplied context (not independently verified enterprise architecture)

- Native AWS SCPs and Azure Policy already exist.
- Cloud Engineering owns underlying provisioning/policy delivery infrastructure.
- Wiz Cloud is being purchased/adopted; runtime sensors and unspecified licensed API capabilities are not assumed.
- IAM and remediation have other owners. Secure provisioning may already be under development elsewhere.

## Conservative design assumptions

- A small team must be able to understand and maintain the product.
- Cloud Security proposes security intent and governs risk; Cloud Engineering retains deployment execution.
- Application teams supply readiness evidence and perform application remediation.
- Integration happens through reviewable artifacts, not organization-admin credentials held by this application.
- The MVP uses only synthetic data and loopback-bound demo identities. The persona names and resource IDs are fictional.

## Decisions requiring owner agreement

1. Product charter and source of truth for existing control definitions.
2. Delegated exception/risk-acceptance authority and maximum duration by risk class.
3. Pilot accounts/subscriptions and criteria for application readiness.
4. GitOps artifact shape, repository ownership and authoritative deployment receipts.
5. OIDC scopes, audit retention, production access controls and emergency recovery responsibilities.
6. Wiz API entitlement, inventory quality, application ownership source and permitted data handling.

None of these decisions are silently treated as an approved enterprise operating model.
